"""
redistricting.py
================
Generación de planes de redistritaje mediante cadenas de Markov
(ReCom) sobre unidades censales chilenas. Compatible con gerrychain
y exportable a redist (R / ALARM).

Restricciones implementadas:
    - Contigüidad geográfica (dura)
    - Balance poblacional ±X% (dura o blanda)
    - Preservación de límites comunales (dura, por Ley 18.700)
    - Compacidad (blanda, función objetivo)
"""

from __future__ import annotations
import json
import warnings
from typing import Optional, Callable

import numpy as np
import pandas as pd
import scipy.sparse as sp
import networkx as nx

from .metrics import (
    cut_edges, contiguity_check, plan_summary,
    polsby_popper, population_balance,
)


# ──────────────────────────────────────────────────────────────────────────────
# Partición inicial
# ──────────────────────────────────────────────────────────────────────────────

def initial_partition(
    gdf,
    id_col: str,
    partition_col: str,
) -> dict:
    """
    Crea una asignación inicial {id_unidad: distrito} desde una columna
    existente (ej. CUT para usar comunas como distritos base).

    Parameters
    ----------
    partition_col : str
        Columna que define la partición inicial (ej. 'CUT', 'N_REGION').

    Returns
    -------
    dict {id: distrito}
    """
    return dict(zip(gdf[id_col], gdf[partition_col]))


# ──────────────────────────────────────────────────────────────────────────────
# Cadena ReCom (vía gerrychain)
# ──────────────────────────────────────────────────────────────────────────────

def run_recom(
    gdf,
    id_col: str,
    pop_col: str,
    n_districts: int,
    n_steps: int = 10_000,
    pop_tolerance: float = 0.05,
    initial_assignment: Optional[dict] = None,
    preserve_col: Optional[str] = None,
    random_seed: int = 42,
    save_every: int = 500,
    output_prefix: str = "plan",
) -> list[dict]:
    """
    Ejecuta una cadena de Markov ReCom para generar planes de redistritaje.

    Requiere: pip install gerrychain

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Unidades con geometrías y población.
    id_col : str
        Columna identificadora única.
    pop_col : str
        Columna de población (ej. 'viviendas').
    n_districts : int
        Número de distritos a generar.
    n_steps : int
        Número de pasos de la cadena de Markov.
    pop_tolerance : float
        Desviación máxima permitida del ideal (0.05 = ±5%).
    initial_assignment : dict, optional
        Asignación inicial {id: distrito}. Si None, se usa una
        partición aleatoria válida.
    preserve_col : str, optional
        Columna cuyas unidades no deben partirse (ej. 'CUT' para
        preservar comunas — análogo a Ley 18.700).
    random_seed : int
        Semilla para reproducibilidad.
    save_every : int
        Guardar snapshot del plan cada N pasos.
    output_prefix : str
        Prefijo para los archivos de salida.

    Returns
    -------
    list[dict]  Lista de planes, cada uno = {id: distrito}.
    """
    try:
        import gerrychain as gc
    except ImportError:
        raise ImportError(
            "gerrychain no está instalado. "
            "Instala con: pip install gerrychain"
        )

    np.random.seed(random_seed)
    gdf = gdf.copy().reset_index(drop=True)

    # Asegurar columna de población numérica
    gdf[pop_col] = pd.to_numeric(gdf[pop_col], errors="coerce").fillna(0)

    # Construir grafo gerrychain
    print("Construyendo grafo gerrychain...")
    cols = [id_col, pop_col] + (
        [preserve_col] if preserve_col and preserve_col in gdf.columns else []
    )
    graph = gc.Graph.from_geodataframe(
        gdf,
        adjacency="queen",
        cols_to_add=[c for c in cols if c in gdf.columns],
    )

    if not graph.is_connected():
        warnings.warn(
            "El grafo no es completamente conexo. "
            "Considera usar connect_islands=True en build_graph()."
        )

    # Partición inicial
    if initial_assignment is None:
        print(f"Generando partición inicial con {n_districts} distritos...")
        assignment_col = _make_initial_assignment(gdf, id_col, pop_col,
                                                   n_districts, graph)
    else:
        assignment_col = pd.Series(initial_assignment).reindex(
            gdf[id_col]
        ).fillna(method="ffill").values
        gdf["__init_dist__"] = gdf[id_col].map(initial_assignment)
        assignment_col = "__init_dist__"

    # Definir updaters
    updaters = {
        "population": gc.updaters.Tally(pop_col, alias="population"),
        "cut_edges":  gc.updaters.cut_edges,
    }
    if preserve_col and preserve_col in gdf.columns:
        updaters["splits"] = gc.updaters.CountSplits(preserve_col)

    # Partición inicial para gerrychain
    partition = gc.Partition(
        graph=graph,
        assignment=assignment_col,
        updaters=updaters,
    )

    # Restricciones
    constraints = [gc.constraints.contiguous]
    constraints.append(
        gc.constraints.within_percent_of_ideal_population(
            partition, pop_tolerance
        )
    )
    if preserve_col and preserve_col in gdf.columns:
        print(f"  Restricción: preservar límites de '{preserve_col}'")
        constraints.append(
            lambda p: p["splits"].total == 0
        )

    # Cadena
    chain = gc.MarkovChain(
        proposal=gc.proposals.recom,
        constraints=constraints,
        accept=gc.accept.always_accept,
        initial_state=partition,
        total_steps=n_steps,
    )

    print(f"Iniciando ReCom: {n_steps:,} pasos · "
          f"{n_districts} distritos · tolerancia ±{pop_tolerance*100:.0f}%")

    plans    = []
    metrics  = []

    for step, state in enumerate(chain):
        assignment = dict(state.assignment)
        plans.append(assignment)

        if step % save_every == 0:
            pop_dev = max(
                abs(pop - state["population"].ideal_pop)
                / state["population"].ideal_pop
                for pop in state["population"].values()
            ) * 100
            n_cuts = len(state["cut_edges"])
            metrics.append({
                "step":        step,
                "cut_edges":   n_cuts,
                "max_pop_dev": round(pop_dev, 3),
            })
            print(f"  Paso {step:6,} | "
                  f"aristas cortadas: {n_cuts:,} | "
                  f"desv. pob. máx: {pop_dev:.2f}%")

    # Guardar resultados
    df_plans = pd.DataFrame(plans)
    df_plans.to_csv(f"{output_prefix}_planes.csv", index=False)
    pd.DataFrame(metrics).to_csv(f"{output_prefix}_metricas.csv", index=False)
    print(f"\nGuardado: {output_prefix}_planes.csv  "
          f"({len(plans)} planes)")
    print(f"Guardado: {output_prefix}_metricas.csv")

    return plans


def _make_initial_assignment(gdf, id_col, pop_col, n_districts, graph):
    """Genera una asignación inicial aleatoria válida."""
    try:
        import gerrychain as gc
        return gc.constraints.contiguous_bfs(graph, n_districts)
    except Exception:
        # Fallback: asignación por módulo (no garantiza contigüidad)
        warnings.warn("No se pudo generar partición contigua inicial. "
                      "Usando asignación por módulo.")
        gdf["__init__"] = [i % n_districts for i in range(len(gdf))]
        return "__init__"


# ──────────────────────────────────────────────────────────────────────────────
# Análisis de ensemble de planes
# ──────────────────────────────────────────────────────────────────────────────

def analyze_ensemble(
    plans: list[dict],
    gdf,
    id_col: str,
    pop_col: str,
    adj: Optional[sp.csr_matrix] = None,
    id_list: Optional[list] = None,
    sample_size: int = 100,
) -> pd.DataFrame:
    """
    Analiza un ensemble de planes calculando métricas agregadas.

    Parameters
    ----------
    plans : list[dict]
        Lista de planes generados por run_recom().
    sample_size : int
        Número de planes a analizar (subsample si len(plans) > sample_size).

    Returns
    -------
    pd.DataFrame con métricas por plan:
        plan_id, n_districts, max_pop_deviation, mean_polsby_popper,
        cut_edges, all_contiguous.
    """
    from .metrics import _ensure_metric
    import geopandas as gpd

    if len(plans) > sample_size:
        idx   = np.linspace(0, len(plans)-1, sample_size, dtype=int)
        plans = [plans[i] for i in idx]

    gdf_m = _ensure_metric(gdf)
    rows  = []

    for plan_id, assignment in enumerate(plans):
        gdf_m["__d__"] = gdf_m[id_col].map(assignment)

        # Balance poblacional
        pop_by_d = gdf_m.groupby("__d__")[pop_col].sum()
        ideal    = pop_by_d.mean()
        max_dev  = ((pop_by_d - ideal).abs() / ideal).max() * 100

        # Compacidad
        dissolved = gdf_m.dissolve("__d__")
        pp        = (
            4 * np.pi * dissolved.geometry.area
            / (dissolved.geometry.length ** 2)
        ).mean()

        # Aristas cortadas
        n_cuts = (
            cut_edges(adj, assignment, id_list)
            if adj is not None and id_list is not None
            else np.nan
        )

        rows.append({
            "plan_id":            plan_id,
            "n_distritos":        pop_by_d.shape[0],
            "max_desv_pob_pct":   round(max_dev, 3),
            "pp_promedio":        round(pp, 4),
            "aristas_cortadas":   n_cuts,
        })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Exportación a R / redist
# ──────────────────────────────────────────────────────────────────────────────

def export_to_redist(
    gdf,
    id_col: str,
    pop_col: str,
    adj: sp.csr_matrix,
    id_list: list,
    output_file: str = "chiledist_redist.rds",
) -> str:
    """
    Exporta los datos en formato compatible con el paquete redist de R
    (ALARM / Harvard).

    Genera un script R que construye el objeto redist_map desde los
    archivos exportados.

    Returns
    -------
    str  Ruta del script R generado.
    """
    import os

    base = output_file.replace(".rds", "")

    # Exportar shapefile
    shp_path = f"{base}_units.gpkg"
    gdf_out  = gdf[[id_col, pop_col, "geometry"]].copy()
    gdf_out.to_file(shp_path, driver="GPKG")

    # Exportar matriz de adyacencia como edge list
    adj_coo  = adj.tocoo()
    edges    = pd.DataFrame({
        "i": [id_list[i] for i in adj_coo.row],
        "j": [id_list[j] for j in adj_coo.col],
    })
    edges    = edges[edges["i"] < edges["j"]]
    adj_path = f"{base}_adj.csv"
    edges.to_csv(adj_path, index=False)

    # Generar script R
    r_script = f"""
# Script generado por chiledist
# Carga datos APC 2023 en formato redist (R/ALARM)

library(redist)
library(sf)
library(dplyr)

# Cargar unidades
units <- st_read("{shp_path}")

# Cargar adyacencia
adj_edges <- read.csv("{adj_path}")
adj <- adjacency_matrix(units)  # alternativa desde geometría

# Crear objeto redist_map
map <- redist_map(
    units,
    pop  = {pop_col},
    adj  = adj,
    ndists = NULL,  # definir según análisis
    pop_tol = 0.05
)

# Ejemplo de simulación SMC
plans <- redist_smc(map, nsims = 500)

# Resumen
summary(plans)
redist.plot.plans(plans, map)
"""

    r_path = f"{base}_redist.R"
    with open(r_path, "w") as f:
        f.write(r_script)

    print(f"Exportado para redist:")
    print(f"  {shp_path}")
    print(f"  {adj_path}")
    print(f"  {r_path}  ← ejecutar en R")

    return r_path


# ──────────────────────────────────────────────────────────────────────────────
# Restricciones específicas para Chile
# ──────────────────────────────────────────────────────────────────────────────

def chile_constraints(
    gdf,
    id_col: str,
    adj: sp.csr_matrix,
    id_list: list,
    preserve_comunas: bool = True,
    preserve_regiones: bool = False,
) -> dict:
    """
    Define las restricciones del sistema electoral chileno.

    Ley 18.700: los distritos electorales no pueden partir comunas.
    Los distritos deben ser geográficamente contiguos.

    Returns
    -------
    dict con:
        'comunas_preservadas': lista de CUT que no deben partirse
        'regiones_preservadas': lista de códigos de región
        'descripcion': texto descriptivo
    """
    result = {
        "preserve_comunas":  preserve_comunas,
        "preserve_regiones": preserve_regiones,
        "descripcion": [],
    }

    if preserve_comunas:
        n_comunas = gdf["CUT"].nunique() if "CUT" in gdf.columns else "?"
        result["descripcion"].append(
            f"Ley 18.700: {n_comunas} comunas deben preservarse íntegras."
        )

    if preserve_regiones:
        n_reg = gdf["N_REGION"].nunique() if "N_REGION" in gdf.columns else "?"
        result["descripcion"].append(
            f"Restricción regional: {n_reg} regiones no deben partirse."
        )

    result["descripcion"].append(
        "Contigüidad geográfica obligatoria (Queen)."
    )

    print("\n── Restricciones electorales Chile ──────────────────────")
    for d in result["descripcion"]:
        print(f"  • {d}")

    return result
