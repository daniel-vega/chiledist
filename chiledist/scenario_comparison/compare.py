"""
scenario_comparison.compare
==============================
Carga de ensembles desde disco, resumen con deltas respecto a un baseline,
ranking ponderado y frontera de Pareto N-dimensional.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .scoring import ScoringConfig, METRICAS_STD

_REGION_NOMBRES = {
    1: "R01_TARAPACA",    2: "R02_ANTOFAGASTA",
    3: "R03_ATACAMA",     4: "R04_COQUIMBO",
    5: "R05_VALPARAISO",  6: "R06_OHIGGINS",
    7: "R07_MAULE",       8: "R08_BIOBIO",
    9: "R09_ARAUCANIA",  10: "R10_LOS_LAGOS",
    11: "R11_AYSEN",     12: "R12_MAGALLANES",
    13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS",
    15: "R15_ARICA",     16: "R16_NUBLE",
}


# ──────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ──────────────────────────────────────────────────────────────────────────────

def load_ensembles_from_disk(
    output_base: str,
    region_code: Union[int, str],
    scenario_names: List[str],
    run_id: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Lee ensemble_stats.csv para cada escenario desde disco.

    Parameters
    ----------
    output_base : str
        Directorio base de salida (contiene datos/<REGION>/redistritaje/…).
    region_code : int | str
        Código de región (int) o nombre de subcarpeta (str).
    scenario_names : list[str]
        Nombres de escenarios (subcarpetas en redistritaje/).
    run_id : str, opcional
        Si se indica, carga solo el run cuyo directorio contiene ese run_id
        (busca subdirectorios run_*_{run_id[:8]} o run_id completo).
        Si es None (default), lee ensemble_stats.csv de la raíz del escenario
        (comportamiento retrocompatible).

    Returns
    -------
    dict {scenario_name: DataFrame} — solo los encontrados en disco.
    """
    if isinstance(region_code, int):
        region_name = _REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    else:
        region_name = str(region_code)

    ensembles: Dict[str, pd.DataFrame] = {}
    for sc_name in scenario_names:
        sc_dir = Path(output_base) / region_name / "redistritaje" / sc_name

        if run_id is not None:
            # Buscar el subdirectorio run_* que corresponde al run_id
            path = _find_run_ensemble(sc_dir, run_id)
        else:
            # Comportamiento retrocompatible: leer de la raíz del escenario
            path = sc_dir / "ensemble_stats.csv"

        if path is not None and path.exists():
            try:
                ensembles[sc_name] = pd.read_csv(path)
            except Exception as e:
                print(f"  ⚠ No se pudo leer {path}: {e}")
        else:
            if run_id is not None:
                print(f"  ⚠ No encontrado run_id={run_id[:8]}… en {sc_dir}")
            else:
                print(f"  ⚠ No encontrado: {sc_dir / 'ensemble_stats.csv'}")
    return ensembles


def _find_run_ensemble(sc_dir: Path, run_id: str) -> Optional[Path]:
    """
    Busca ensemble_stats.csv dentro del subdirectorio run_* que coincide
    con run_id (primeros 8 caracteres o UUID completo).
    """
    if not sc_dir.exists():
        return None

    run_id_short = run_id[:8]
    run_id_full  = run_id.replace("-", "")[:8]  # UUID sin guiones, primeros 8

    for entry in sorted(sc_dir.iterdir(), reverse=True):  # más reciente primero
        if not entry.is_dir() or not entry.name.startswith("run_"):
            continue
        name = entry.name
        # Acepta tanto run_id completo como prefijo de 8 chars
        if run_id in name or run_id_short in name or run_id_full in name:
            candidate = entry / "ensemble_stats.csv"
            if candidate.exists():
                return candidate

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Visibilidad de escenarios sin ensemble válido (infeasible_population,
# sin_particion, u otro status != "ok") y completitud de la comparación
# ──────────────────────────────────────────────────────────────────────────────

def load_scenario_statuses_from_disk(
    output_base: str,
    region_code: Union[int, str],
    scenario_names: List[str],
) -> Dict[str, dict]:
    """
    Lee scenario_status.json para escenarios que no produjeron un
    ensemble_stats.csv válido (ej. infeasible_population, sin_particion).

    scripts/compare_scenarios.py escribe este archivo con el dict de
    resultado completo de analizar_region() cada vez que status != "ok",
    preservando status, reason y el resto del diagnóstico (ej. los campos
    del preflight de factibilidad poblacional).

    Returns
    -------
    dict {scenario_name: status_dict} — solo los que tienen el archivo.
    """
    if isinstance(region_code, int):
        region_name = _REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    else:
        region_name = str(region_code)

    statuses: Dict[str, dict] = {}
    for sc_name in scenario_names:
        path = Path(output_base) / region_name / "redistritaje" / sc_name / "scenario_status.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    statuses[sc_name] = json.load(f)
            except Exception as e:
                print(f"  ⚠ No se pudo leer {path}: {e}")
    return statuses


def build_scenario_overview(
    scenario_names: List[str],
    ensembles: Dict[str, pd.DataFrame],
    statuses: Optional[Dict[str, dict]] = None,
) -> pd.DataFrame:
    """
    Tabla con una fila por cada escenario ESPERADO (`scenario_names`),
    visible tenga o no un ensemble válido.

    Columnas: escenario, status, reason, included_in_scoring, n_planes.

    Un escenario con ensemble válido tiene status="ok" e
    included_in_scoring=True. Uno sin ensemble válido conserva su status y
    reason reales (desde `statuses`, ver load_scenario_statuses_from_disk)
    y queda con included_in_scoring=False — nunca recibe score artificial,
    NaN relleno, ni entra al ranking de rank_scenarios().
    """
    statuses = statuses or {}
    rows = []
    for sc_name in scenario_names:
        if sc_name in ensembles:
            rows.append({
                "escenario":           sc_name,
                "status":              "ok",
                "reason":              None,
                "included_in_scoring": True,
                "n_planes":            len(ensembles[sc_name]),
            })
        else:
            st = statuses.get(sc_name, {})
            rows.append({
                "escenario":           sc_name,
                "status":              st.get("status", "sin_datos"),
                "reason":              st.get("reason"),
                "included_in_scoring": False,
                "n_planes":            0,
            })
    return pd.DataFrame(rows)


def assess_comparison_completeness(
    scenario_names: List[str],
    ensembles: Dict[str, pd.DataFrame],
    baseline: str = "legal_comunas",
) -> Dict[str, Any]:
    """
    Resume si la comparación entre `scenario_names` está completa.

    comparison_status="COMPLETE" solo si TODOS los escenarios esperados
    tienen ensemble válido; en cualquier otro caso "INCOMPLETE". El ranking
    entre los escenarios con ensemble válido puede calcularse igual
    (rank_scenarios sigue recibiendo solo esos), pero ranking_scope queda
    en "partial" — es descriptivo, no la comparación H1 completa — en vez
    de "full".

    Returns
    -------
    dict con comparison_status, expected_scenarios, valid_ensembles,
    missing_baseline (nombre del baseline si le falta ensemble válido, o
    None) y ranking_scope.
    """
    expected = len(scenario_names)
    valid    = sum(1 for s in scenario_names if s in ensembles)
    complete = valid == expected

    missing_baseline = (
        baseline if (baseline in scenario_names and baseline not in ensembles)
        else None
    )

    return {
        "comparison_status":  "COMPLETE" if complete else "INCOMPLETE",
        "expected_scenarios": expected,
        "valid_ensembles":    valid,
        "missing_baseline":   missing_baseline,
        "ranking_scope":      "full" if complete else "partial",
    }


# ──────────────────────────────────────────────────────────────────────────────
# compare_ensembles
# ──────────────────────────────────────────────────────────────────────────────

def compare_ensembles(
    ensembles: Dict[str, pd.DataFrame],
    baseline: str = "legal_comunas",
    percentiles: Tuple[float, float] = (0.25, 0.75),
) -> pd.DataFrame:
    """
    Resume y compara estadísticas de ensemble entre escenarios.

    Calcula mediana, p25 y p75 de cada métrica estándar, luego agrega
    columnas delta_* con la diferencia respecto al escenario baseline.

    Parameters
    ----------
    ensembles : dict {scenario_name: DataFrame}
        DataFrames de ensemble_stats.csv indexados por nombre de escenario.
    baseline : str
        Nombre del escenario de referencia para los deltas.
    percentiles : (float, float)
        Percentiles inferior y superior a reportar.

    Returns
    -------
    DataFrame con una fila por escenario y columnas:
        escenario, <col>_median, <col>_p25, <col>_p75, delta_<col>_median.
    """
    rows = []
    for sc_name, df in ensembles.items():
        row: Dict = {"escenario": sc_name}
        for col, _, _ in METRICAS_STD:
            if col in df.columns:
                vals = df[col].dropna()
                if len(vals):
                    row[f"{col}_median"] = round(float(vals.median()), 4)
                    row[f"{col}_p25"]    = round(float(vals.quantile(percentiles[0])), 4)
                    row[f"{col}_p75"]    = round(float(vals.quantile(percentiles[1])), 4)
                else:
                    row[f"{col}_median"] = None
                    row[f"{col}_p25"]    = None
                    row[f"{col}_p75"]    = None
            else:
                row[f"{col}_median"] = None
                row[f"{col}_p25"]    = None
                row[f"{col}_p75"]    = None
        rows.append(row)

    df_comp = pd.DataFrame(rows)
    if df_comp.empty:
        return df_comp

    return scenario_delta(df_comp, baseline=baseline)


# ──────────────────────────────────────────────────────────────────────────────
# scenario_delta
# ──────────────────────────────────────────────────────────────────────────────

def scenario_delta(
    df_comp: pd.DataFrame,
    baseline: str = "legal_comunas",
    metric_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Agrega columnas delta_<col> con diferencia respecto al escenario baseline.

    Delta = valor_escenario − valor_baseline.
    Para métricas donde "menor es mejor", delta negativo = mejora.

    Parameters
    ----------
    df_comp : DataFrame
        Salida de compare_ensembles() o tabla con columnas *_median.
    baseline : str
        Escenario de referencia (debe existir en df_comp["escenario"]).
    metric_cols : list[str], opcional
        Columnas a diferenciar. Por defecto: todas las columnas *_median.
    """
    if baseline not in df_comp["escenario"].values:
        return df_comp

    df_out = df_comp.copy()
    baseline_row = df_out[df_out["escenario"] == baseline].iloc[0]

    if metric_cols is None:
        metric_cols = [f"{col}_median" for col, _, _ in METRICAS_STD
                       if f"{col}_median" in df_out.columns]

    for col in metric_cols:
        if col not in df_out.columns:
            continue
        ref = baseline_row.get(col)
        if ref is None or pd.isna(ref):
            continue
        df_out[f"delta_{col}"] = (df_out[col].astype(float) - float(ref)).round(4)

    return df_out


# ──────────────────────────────────────────────────────────────────────────────
# rank_scenarios
# ──────────────────────────────────────────────────────────────────────────────

def rank_scenarios(
    df_comp: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> pd.DataFrame:
    """
    Ordena escenarios por score compuesto ponderado.

    Cada métrica se normaliza a [0, 1] según la estrategia de ScoringConfig;
    el score parcial es val_norm (max-better) o 1 − val_norm (min-better).
    La suma ponderada forma el composite_score (mayor = mejor).

    Parameters
    ----------
    weights : dict, opcional
        Pesos por columna base, ej. {"max_dev_pob_pct": 0.4}.
        Si None y scoring_config es None, usa PESOS_DEFAULT.
        Ignorado si scoring_config está presente.
    scoring_config : ScoringConfig, opcional
        Configuración completa (pesos + direcciones + normalización).
        Tiene precedencia sobre `weights`.

    Returns
    -------
    df_comp con columnas adicionales:
        composite_score  — puntaje total (mayor = mejor)
        rank             — posición ordinal (1 = mejor)
        score_<col>      — contribución parcial de cada métrica al score

    Examples
    --------
    >>> tabla = cd.compare_ensembles(ensembles)
    >>> cd.rank_scenarios(tabla)

    >>> # Priorizar compacidad
    >>> sc = cd.ScoringConfig.from_weights({"pp_promedio": 0.7,
    ...                                     "max_dev_pob_pct": 0.3})
    >>> cd.rank_scenarios(tabla, scoring_config=sc)
    """
    if scoring_config is None:
        if weights is not None:
            scoring_config = ScoringConfig.from_weights(weights)
        else:
            scoring_config = ScoringConfig.default()

    df_out = df_comp.copy()
    score  = pd.Series(np.zeros(len(df_out)), index=df_out.index)

    for col, w in scoring_config.weights.items():
        if w == 0.0:
            continue
        median_col = f"{col}_median"
        if median_col not in df_out.columns:
            continue
        vals = pd.to_numeric(df_out[median_col], errors="coerce")
        if vals.isna().all():
            continue

        direction = scoring_config.directions.get(col, "min")

        if scoring_config.normalization == "minmax":
            vmin, vmax = vals.min(), vals.max()
            if abs(vmax - vmin) < 1e-12:
                norm = pd.Series(0.5, index=vals.index)
            else:
                norm = (vals - vmin) / (vmax - vmin)

        elif scoring_config.normalization == "zscore":
            std = vals.std()
            if std < 1e-12:
                norm = pd.Series(0.5, index=vals.index)
            else:
                z = (vals - vals.mean()) / std
                zmin, zmax = z.min(), z.max()
                norm = (z - zmin) / (zmax - zmin + 1e-12)

        elif scoring_config.normalization == "rank":
            norm = vals.rank(pct=True, na_option="keep")

        partial = norm if direction == "max" else (1.0 - norm)
        partial = partial.fillna(0.0)
        score += w * partial
        df_out[f"score_{col}"] = (w * partial).round(4)

    df_out["composite_score"] = score.round(4)
    df_out["rank"] = df_out["composite_score"].rank(ascending=False).astype(int)
    return df_out.sort_values("rank").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Frontera de Pareto N-dimensional
# ──────────────────────────────────────────────────────────────────────────────

def pareto_frontier_nd(
    points: Union[np.ndarray, pd.DataFrame],
    minimize: Optional[Union[np.ndarray, List[bool], Dict[str, bool]]] = None,
) -> np.ndarray:
    """
    Índices de los puntos no-dominados en un espacio N-dimensional.

    Un punto i es dominado por j si j es igual-o-mejor en TODOS los objetivos
    y estrictamente mejor en AL MENOS UNO.

    Parameters
    ----------
    points : array-like shape (n_points, n_objectives) o DataFrame
        Matriz de valores; una fila por punto, una columna por objetivo.
    minimize : array-like de bool, dict {col: bool} o None
        True = minimizar ese objetivo, False = maximizar.
        None → minimizar todos.
        Si points es DataFrame y minimize es dict, usa nombres de columna.

    Returns
    -------
    np.ndarray de índices (int) de los puntos no-dominados.

    Examples
    --------
    >>> pts = np.array([[0.1, 5], [0.2, 3], [0.3, 2], [0.1, 6]])
    >>> pareto_frontier_nd(pts, minimize=[True, True])
    array([0, 1, 2])   # [0.3, 2] domina a [0.1, 6] en y pero no en x
    """
    if isinstance(points, pd.DataFrame):
        cols = points.columns.tolist()
        if isinstance(minimize, dict):
            minimize = np.array([minimize.get(c, True) for c in cols])
        pts = points.values.astype(float)
    else:
        pts = np.asarray(points, dtype=float)

    n, m = pts.shape

    if minimize is None:
        minimize = np.ones(m, dtype=bool)
    else:
        minimize = np.asarray(minimize, dtype=bool)

    # Convertir todo a minimización: voltear los ejes de maximización
    work = pts.copy()
    work[:, ~minimize] *= -1

    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        if not is_pareto[i]:
            continue
        # j domina a i si j <= i en todo y j < i en algo
        better_or_equal = np.all(work <= work[i], axis=1)   # (n,)
        strictly_better = np.any(work  < work[i], axis=1)   # (n,)
        dominated_by    = better_or_equal & strictly_better
        dominated_by[i] = False
        if dominated_by.any():
            is_pareto[i] = False

    return np.where(is_pareto)[0]


# ──────────────────────────────────────────────────────────────────────────────
# pareto_optimal_scenarios
# ──────────────────────────────────────────────────────────────────────────────

def pareto_optimal_scenarios(
    df_comp: pd.DataFrame,
    metric_cols: Optional[List[str]] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> pd.DataFrame:
    """
    Devuelve las filas de df_comp (salida de compare_ensembles) que son
    Pareto-óptimas entre los escenarios comparados.

    Un escenario es Pareto-óptimo si no existe otro que sea igual-o-mejor
    en todas las métricas y estrictamente mejor en al menos una.

    Parameters
    ----------
    df_comp : DataFrame
        Tabla de compare_ensembles() con columnas <col>_median.
    metric_cols : list[str], opcional
        Métricas base a considerar (sin sufijo _median).
        None → usa todas las de METRICAS_STD que estén disponibles.
    scoring_config : ScoringConfig, opcional
        Si se provee, sus `directions` sobreescriben las de METRICAS_STD.

    Returns
    -------
    DataFrame con las filas Pareto-óptimas (puede ser un subconjunto o todo).

    Examples
    --------
    >>> tabla = cd.compare_ensembles(ensembles)
    >>> cd.pareto_optimal_scenarios(tabla)
    """
    if metric_cols is None:
        metric_cols = [col for col, _, _ in METRICAS_STD]

    directions = {col: d for col, _, d in METRICAS_STD}
    if scoring_config is not None:
        directions.update(scoring_config.directions)

    avail   = [c for c in metric_cols if f"{c}_median" in df_comp.columns]
    med_cols = [f"{c}_median" for c in avail]

    if not avail:
        return df_comp.copy()

    pts = df_comp[med_cols].values.astype(float)
    minimize = np.array([directions.get(c, "min") == "min" for c in avail])

    idx = pareto_frontier_nd(pts, minimize=minimize)
    return df_comp.iloc[idx].copy().reset_index(drop=True)
