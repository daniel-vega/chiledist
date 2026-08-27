"""
inference.sensitivity
========================
Posicionamiento del plan vigente en el espacio de métricas del ensemble
(H1/H2), frecuencia de comunas partidas, y tests de sensibilidad
metodológica / concordancia de ranking (H5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..evaluation.scoring import METRICAS_STD

# ──────────────────────────────────────────────────────────────────────────────
# split_frequency_table
# ──────────────────────────────────────────────────────────────────────────────

def split_frequency_table(
    results_dir: str,
    scenario_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Tabla de frecuencia de comunas partidas consolidada por escenario.

    Lee comunas_partidas.csv (mejor plan) de cada subdirectorio de escenario.
    Devuelve una fila por CUT con cuántos escenarios la parten y cuáles.

    Parameters
    ----------
    results_dir : str
        Directorio con subcarpetas por escenario
        (ej. datos/<REGION>/redistritaje/).
    scenario_names : list[str], opcional
        Si None, lee todos los subdirectorios existentes.

    Returns
    -------
    DataFrame: CUT, nombre, n_escenarios_partida, escenarios_donde_parte,
               pop_total, split_severity_max.
    """
    base = Path(results_dir)
    if scenario_names is None:
        scenario_names = [d.name for d in base.iterdir() if d.is_dir()]

    frames: List[pd.DataFrame] = []
    for sc_name in scenario_names:
        csv_path = base / sc_name / "comunas_partidas.csv"
        if csv_path.exists():
            try:
                df_sc = pd.read_csv(csv_path)
                df_sc["escenario"] = sc_name
                frames.append(df_sc)
            except Exception:
                pass

    if not frames:
        return pd.DataFrame()

    df_all = pd.concat(frames, ignore_index=True)

    cut_col = "CUT"      if "CUT"      in df_all.columns else df_all.columns[0]
    nom_col = "nombre"   if "nombre"   in df_all.columns else None
    pop_col = "pop_total" if "pop_total" in df_all.columns else None
    sev_col = "split_severity" if "split_severity" in df_all.columns else None

    agg: Dict = {"escenario": list}
    if pop_col:
        agg[pop_col] = "max"
    if sev_col:
        agg[sev_col] = "max"
    if nom_col:
        agg[nom_col] = "first"

    grp = df_all.groupby(cut_col).agg(agg).reset_index()
    grp["n_escenarios_partida"]  = grp["escenario"].apply(len)
    grp["escenarios_donde_parte"] = grp["escenario"].apply(
        lambda x: "; ".join(sorted(set(x)))
    )
    grp = grp.drop(columns=["escenario"])
    if sev_col:
        grp = grp.rename(columns={sev_col: "split_severity_max"})
    grp = grp.sort_values("n_escenarios_partida", ascending=False)

    return grp.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# H1/H2/H5 — posición del plan vigente y sensibilidad metodológica
# ──────────────────────────────────────────────────────────────────────────────

def position_plan_vigente(
    assignment: dict,
    gdf,
    id_col: str,
    pop_col: str,
    adj=None,
    unit_col: str = "CUT",
    scenario_name: str = "vigente",
) -> dict:
    """
    Calcula las métricas estándar del plan vigente en el mismo espacio
    vectorial que ``ensemble_stats`` para posicionarlo en la frontera de Pareto.

    Permite responder H1 y H2: ¿en qué punto del espacio de Pareto se ubica
    el plan legislativo actualmente vigente frente al ensemble de alternativos?

    Parameters
    ----------
    assignment : dict {node_id: district_id}
        Asignación del plan vigente (``MAGNITUDES_LEGALES_LEY20840`` o similar).
    gdf : gpd.GeoDataFrame
        Capa geográfica con columnas id_col, pop_col, unit_col y geometría.
    id_col : str
        Columna de identificador único de unidad (ej. "ID_DIST").
    pop_col : str
        Columna de población (ej. "viviendas" o "personas").
    adj : networkx.Graph, optional
        Grafo de adyacencia; si se provee, se calcula cut_edges.
    unit_col : str
        Columna de unidad administrativa a preservar (ej. "CUT").
    scenario_name : str
        Etiqueta del plan en el DataFrame de salida (default "vigente").

    Returns
    -------
    dict con las mismas claves que una fila de compare_ensembles():
        scenario, max_dev_pob_pct, pp_promedio, cut_edges (si adj),
        n_comunas_partidas, split_severity, pop_afectada_pct,
        n_districts, total_pop.
    """
    import warnings
    import geopandas as gpd
    from ..engines.metrics import (
        cut_edges as _cut_edges,
        polsby_popper,
        plan_split_metrics,
    )

    districts = sorted(set(assignment.values()))
    n_districts = len(districts)

    # Población por circunscripción
    pop_map = dict(zip(gdf[id_col], gdf[pop_col]))
    pop_by_d: dict[int, float] = {}
    for node, dist in assignment.items():
        pop_by_d[dist] = pop_by_d.get(dist, 0) + pop_map.get(node, 0)

    pop_series = pd.Series(pop_by_d)
    total_pop  = float(pop_series.sum())
    ideal      = total_pop / n_districts if n_districts > 0 else 0.0
    max_dev    = float((pop_series - ideal).abs().max() / ideal * 100) if ideal > 0 else float("nan")

    # Compacidad promedio (Polsby-Popper)
    pp_vals = []
    if gdf.crs is not None and gdf.crs.is_geographic:
        warnings.warn(
            "position_plan_vigente: CRS geográfico detectado. "
            "Polsby-Popper requiere CRS métrico (ej. EPSG:32719). "
            "Reproyectar con gdf.to_crs() antes de llamar esta función. "
            "pp_promedio se devolverá como NaN.",
            UserWarning,
            stacklevel=2,
        )
    else:
        # Pre-calcular inverso del assignment para evitar O(n×k) por distrito
        dist_to_nodes: dict = {}
        for node, dist in assignment.items():
            dist_to_nodes.setdefault(dist, []).append(node)

        for dist in districts:
            nodes   = dist_to_nodes.get(dist, [])
            sub_gdf = gdf[gdf[id_col].isin(nodes)]
            if sub_gdf.empty:
                continue
            try:
                union_geom = (
                    sub_gdf.geometry.union_all()
                    if hasattr(sub_gdf.geometry, "union_all")
                    else sub_gdf.geometry.unary_union
                )
                tmp = gpd.GeoDataFrame(geometry=[union_geom], crs=gdf.crs)
                pp_vals.append(polsby_popper(tmp).iloc[0])
            except Exception as exc:
                warnings.warn(
                    f"position_plan_vigente: Polsby-Popper falló para distrito {dist}: {exc}",
                    UserWarning,
                    stacklevel=2,
                )

    pp_promedio = float(np.mean(pp_vals)) if pp_vals else float("nan")

    # Aristas cortadas
    ce = int(_cut_edges(gdf, assignment, id_col=id_col, adj=adj)) if adj is not None else float("nan")

    # Comunas partidas
    sm = plan_split_metrics(assignment, gdf, unit_col=unit_col, id_col=id_col, pop_col=pop_col)

    return {
        "scenario":            scenario_name,
        "max_dev_pob_pct":     round(max_dev, 4),
        "pp_promedio":         round(pp_promedio, 4) if not np.isnan(pp_promedio) else float("nan"),
        "cut_edges":           ce,
        "n_comunas_partidas":  sm["n_comunas_partidas"],
        "split_severity":      sm["split_severity"],
        "pop_afectada_pct":    sm["pop_afectada_pct"],
        "n_districts":         n_districts,
        "total_pop":           round(total_pop, 0),
    }


def compare_sensitivity(
    ensembles: "dict[str, pd.DataFrame]",
    metric_cols: "Optional[List[str]]" = None,
) -> pd.DataFrame:
    """
    Compara pares de ensembles con KS test y diferencia de medianas.

    Permite responder H5: ¿cuán sensibles son los resultados a la elección
    metodológica (viviendas vs. personas, ReCom vs. SMC, CUT vs. APC)?

    Un KS estadístico alto y p < 0.05 indica que los ensembles producen
    distribuciones realmente distintas para esa métrica.

    Parameters
    ----------
    ensembles : dict {nombre_escenario: DataFrame_ensemble_stats}
        Cada DataFrame tiene una fila por plan muestreado del ensemble.
        Las columnas son las métricas de interés.
    metric_cols : list[str], optional
        Métricas a comparar. None → usa METRICAS_STD disponibles.

    Returns
    -------
    pd.DataFrame con columnas:
        par_a, par_b, metrica,
        ks_stat, ks_pvalue,
        mediana_a, mediana_b, delta_medianas,
        p_significativo (bool, p < 0.05),
        efecto (str: "negligible" | "pequeño" | "moderado" | "grande").

    Sorted by ks_stat descendente (los cambios más grandes primero).

    Nota sobre interpretación
    -------------------------
    ``p_significativo`` es sensible al tamaño muestral: con N ≥ 500, diferencias
    de ks_stat ≈ 0.04 resultan en p < 0.05.  Usar ``efecto`` como medida
    principal de relevancia práctica:
        ks_stat < 0.05  → negligible  (distribuciones prácticamente idénticas)
        0.05–0.10       → pequeño
        0.10–0.20       → moderado    (metodología introduce variación apreciable)
        ≥ 0.20          → grande      (metodología cambia sustancialmente el resultado)
    """
    from scipy import stats as sp_stats
    import itertools

    def _efecto(ks: float) -> str:
        if ks < 0.05:
            return "negligible"
        if ks < 0.10:
            return "pequeño"
        if ks < 0.20:
            return "moderado"
        return "grande"

    if metric_cols is None:
        metric_cols = [col for col, _, _ in METRICAS_STD]

    names = list(ensembles.keys())
    rows  = []

    for a, b in itertools.combinations(names, 2):
        df_a = ensembles[a]
        df_b = ensembles[b]

        for col in metric_cols:
            if col not in df_a.columns or col not in df_b.columns:
                continue

            va = pd.to_numeric(df_a[col], errors="coerce").dropna().values
            vb = pd.to_numeric(df_b[col], errors="coerce").dropna().values

            if len(va) < 2 or len(vb) < 2:
                continue

            ks_stat, ks_pval = sp_stats.ks_2samp(va, vb)
            med_a = float(np.median(va))
            med_b = float(np.median(vb))

            rows.append({
                "par_a":            a,
                "par_b":            b,
                "metrica":          col,
                "ks_stat":          round(ks_stat, 4),
                "ks_pvalue":        round(ks_pval, 6),
                "mediana_a":        round(med_a, 4),
                "mediana_b":        round(med_b, 4),
                "delta_medianas":   round(med_b - med_a, 4),
                "p_significativo":  bool(ks_pval < 0.05),
                "efecto":           _efecto(ks_stat),
            })

    if not rows:
        return pd.DataFrame(columns=[
            "par_a", "par_b", "metrica", "ks_stat", "ks_pvalue",
            "mediana_a", "mediana_b", "delta_medianas", "p_significativo", "efecto",
        ])

    return (
        pd.DataFrame(rows)
        .sort_values("ks_stat", ascending=False)
        .reset_index(drop=True)
    )


def ranking_concordance(
    scores_a: "dict[str, float]",
    scores_b: "dict[str, float]",
) -> dict:
    """
    Concordancia de ranking entre dos conjuntos de puntuaciones de escenarios.

    Permite responder H5: ¿qué tan estable es el ranking de escenarios frente
    a cambios metodológicos (ej. ponderación diferente, población diferente)?

    Si τ y ρ son altos (≥ 0.8), los rankings son robustos al cambio metodológico.

    Parameters
    ----------
    scores_a, scores_b : dict {nombre_escenario: puntaje_compuesto}
        Salida típica de rank_scenarios()[["scenario", "composite_score"]].

    Returns
    -------
    dict con:
        kendall_tau  : coeficiente de concordancia de Kendall (−1 a 1)
        kendall_pval : p-valor asociado
        spearman_rho : coeficiente de Spearman (−1 a 1)
        spearman_pval: p-valor asociado
        n_comunes    : número de escenarios comunes entre ambos conjuntos
        discordantes : lista de pares (esc_i, esc_j) donde el orden se invierte
    """
    import warnings
    from scipy import stats as sp_stats

    comunes = sorted(set(scores_a) & set(scores_b))
    n = len(comunes)

    if n < 2:
        return {
            "kendall_tau":              float("nan"),
            "kendall_pval":             float("nan"),
            "spearman_rho":             float("nan"),
            "spearman_pval":            float("nan"),
            "n_comunes":                n,
            "discordantes":             [],
            "bajo_potencia_estadistica": True,
        }

    if n < 5:
        warnings.warn(
            f"ranking_concordance: solo {n} escenarios comunes. "
            "Con n < 5 los p-valores de Kendall/Spearman no tienen potencia estadística "
            "(ej. con n=3 el p-valor mínimo posible es 0.333). "
            "Usar τ y ρ como medidas descriptivas, no inferenciales.",
            UserWarning,
            stacklevel=2,
        )

    va = np.array([scores_a[s] for s in comunes])
    vb = np.array([scores_b[s] for s in comunes])

    tau,  pval_tau  = sp_stats.kendalltau(va, vb)
    rho,  pval_rho  = sp_stats.spearmanr(va, vb)

    # Pares con inversión de orden
    discordantes = []
    for i in range(n):
        for j in range(i + 1, n):
            si, sj = comunes[i], comunes[j]
            if (scores_a[si] > scores_a[sj]) != (scores_b[si] > scores_b[sj]):
                discordantes.append((si, sj))

    return {
        "kendall_tau":               round(float(tau), 4),
        "kendall_pval":              round(float(pval_tau), 6),
        "spearman_rho":              round(float(rho), 4),
        "spearman_pval":             round(float(pval_rho), 6),
        "n_comunes":                 n,
        "discordantes":              discordantes,
        "bajo_potencia_estadistica": n < 5,
    }
