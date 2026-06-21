"""
split_metrics.py
================
Métricas para cuantificar el impacto de partir unidades administrativas
(comunas, provincias, regiones) en un plan de redistritaje.

Estas métricas son centrales para comparar el modo legal (CUT indivisible)
con el modo experimental (APC libre): permiten medir cuántas comunas se
parten, con qué severidad, y qué proporción de la población queda en
comunas divididas.

Funciones principales:
    count_split_units     → nº de unidades partidas
    split_severity_index  → índice ponderado por población
    split_unit_summary    → DataFrame detallado por unidad partida
    small_fragment_count  → fragmentos por debajo de umbral poblacional
    plan_split_metrics    → todas las métricas en un dict
"""

from __future__ import annotations
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────

def count_split_units(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str,
    id_col: str,
) -> int:
    """
    Cuenta cuántas unidades de unit_col aparecen en más de un distrito.

    Parameters
    ----------
    assignment : dict
        {id_col_value: district_id} — IDs de cadena, post-reconstrucción.
    gdf : gpd.GeoDataFrame
        Con columnas id_col y unit_col.
    unit_col : str
        Columna cuya integridad se evalúa (ej. "CUT").
    id_col : str
        Columna de la unidad de decisión (ej. "ID_DIST").

    Returns
    -------
    int  Número de unidades partidas.
    """
    df = _build_assignment_df(assignment, gdf, unit_col, id_col)
    if df.empty:
        return 0
    n_districts_per_unit = df.groupby(unit_col)["district"].nunique()
    return int((n_districts_per_unit > 1).sum())


def split_severity_index(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str,
    id_col: str,
    pop_col: Optional[str] = "viviendas",
) -> float:
    """
    Índice de severidad de partición ponderado por población.

    Fórmula:
        severity = Σ_comunas [ (n_fragmentos - 1) × share_pob_comunal ]

    Rango: [0, ∞). 0 = ninguna partición. Valores más altos indican
    más comunas partidas o comunas más pobladas divididas.

    Parameters
    ----------
    assignment : dict
    gdf : gpd.GeoDataFrame
    unit_col : str
    id_col : str
    pop_col : str, optional
        Columna de población para ponderar. Si None, usa conteo uniforme.

    Returns
    -------
    float
    """
    df = _build_assignment_df(assignment, gdf, unit_col, id_col)
    if df.empty:
        return 0.0

    if pop_col and pop_col in gdf.columns:
        pop_map   = dict(zip(gdf[id_col], gdf[pop_col]))
        df["pop"] = df[id_col].map(pop_map).fillna(0)
        total_pop = df["pop"].sum()
        if total_pop == 0:
            return 0.0
        unit_pop        = df.groupby(unit_col)["pop"].sum()
        df["pop_share"] = df[unit_col].map(unit_pop) / total_pop
    else:
        n = max(df[unit_col].nunique(), 1)
        df["pop_share"] = 1.0 / n

    n_frags          = df.groupby(unit_col)["district"].nunique()
    pop_share_first  = df.groupby(unit_col)["pop_share"].first()
    severity_per_unit = (n_frags - 1) * pop_share_first
    return float(severity_per_unit.sum())


def split_unit_summary(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str,
    id_col: str,
    pop_col: Optional[str] = "viviendas",
    name_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Resumen detallado de las unidades partidas en un plan.

    Parameters
    ----------
    assignment : dict
    gdf : gpd.GeoDataFrame
    unit_col : str
    id_col : str
    pop_col : str, optional
    name_col : str, optional
        Columna con nombre de la unidad. Si None, busca N_COMUNA,
        N_PROVINCIA o N_REGION.

    Returns
    -------
    pd.DataFrame con columnas:
        unit_col, nombre, n_fragmentos, distritos,
        pop_total, pop_share_total, split_severity
    Ordenado por pop_total descendente.
    """
    df = _build_assignment_df(assignment, gdf, unit_col, id_col)
    if df.empty:
        return _empty_summary_df(unit_col)

    if pop_col and pop_col in gdf.columns:
        pop_map   = dict(zip(gdf[id_col], gdf[pop_col]))
        df["pop"] = df[id_col].map(pop_map).fillna(0)
        total_pop = df["pop"].sum()
    else:
        df["pop"] = 1
        total_pop = len(df)

    if name_col is None:
        for cand in ("N_COMUNA", "N_PROVINCIA", "N_REGION"):
            if cand in gdf.columns:
                name_col = cand
                break

    if name_col and name_col in gdf.columns:
        name_map = gdf.groupby(unit_col)[name_col].first()
    else:
        name_map = None

    rows = []
    for unit_val, grp in df.groupby(unit_col):
        n_frags = grp["district"].nunique()
        if n_frags <= 1:
            continue
        pop_t     = grp["pop"].sum()
        pop_share = pop_t / total_pop if total_pop > 0 else 0
        severity  = (n_frags - 1) * pop_share
        rows.append({
            unit_col:           unit_val,
            "nombre":           (name_map[unit_val] if name_map is not None
                                 and unit_val in name_map.index else ""),
            "n_fragmentos":     int(n_frags),
            "distritos":        sorted(grp["district"].unique().tolist()),
            "pop_total":        int(pop_t),
            "pop_share_total":  round(float(pop_share), 4),
            "split_severity":   round(float(severity), 6),
        })

    if not rows:
        return _empty_summary_df(unit_col)

    return (
        pd.DataFrame(rows)
        .sort_values("pop_total", ascending=False)
        .reset_index(drop=True)
    )


def small_fragment_count(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str,
    id_col: str,
    pop_col: str = "viviendas",
    min_pop_share: float = 0.10,
) -> int:
    """
    Cuenta fragmentos comunales que representan menos del min_pop_share
    de la población total de su unidad de origen.

    Fragmentos "pequeños" son potencialmente artificiales o políticamente
    manipulados. Un umbral de 10% es razonable para el primer análisis.

    Parameters
    ----------
    min_pop_share : float
        Umbral. Default: 0.10 (fragmentos con <10% de la pop comunal).

    Returns
    -------
    int
    """
    df = _build_assignment_df(assignment, gdf, unit_col, id_col)
    if df.empty or pop_col not in gdf.columns:
        return 0

    pop_map   = dict(zip(gdf[id_col], gdf[pop_col]))
    df["pop"] = df[id_col].map(pop_map).fillna(0)

    # Población total por unidad
    unit_total = df.groupby(unit_col)["pop"].sum().rename("unit_total")

    # Población por fragmento (unidad × distrito)
    frag_pop = (
        df.groupby([unit_col, "district"])["pop"]
        .sum()
        .reset_index(name="frag_pop")
    )
    frag_pop = frag_pop.merge(
        unit_total.reset_index(), on=unit_col, how="left"
    )
    frag_pop["share"] = np.where(
        frag_pop["unit_total"] > 0,
        frag_pop["frag_pop"] / frag_pop["unit_total"],
        0.0,
    )

    # Solo fragmentos de unidades que SÍ están partidas
    n_frags_per_unit = (
        frag_pop.groupby(unit_col)["district"]
        .nunique()
        .rename("n_frags")
    )
    frag_pop = frag_pop.merge(
        n_frags_per_unit.reset_index(), on=unit_col, how="left"
    )

    small = frag_pop[
        (frag_pop["n_frags"] > 1) & (frag_pop["share"] < min_pop_share)
    ]
    return len(small)


def plan_split_metrics(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str = "CUT",
    id_col: str = "ID_DIST",
    pop_col: str = "viviendas",
) -> dict:
    """
    Calcula todas las métricas de partición para un plan.

    Parameters
    ----------
    assignment : dict
        {id_col_str: district_id}
    gdf : gpd.GeoDataFrame
    unit_col : str
        Columna de la unidad a preservar (ej. "CUT").
    id_col : str
        Columna de la unidad de decisión (ej. "ID_DIST").
    pop_col : str

    Returns
    -------
    dict con:
        n_comunas_partidas, share_comunas_partidas,
        split_severity, small_fragments,
        comunas_mas_partidas (lista de CUT)
    """
    n_total = gdf[unit_col].nunique() if unit_col in gdf.columns else 0

    n_split  = count_split_units(assignment, gdf, unit_col, id_col)
    severity = split_severity_index(assignment, gdf, unit_col, id_col, pop_col)
    small    = small_fragment_count(assignment, gdf, unit_col, id_col, pop_col)

    summary  = split_unit_summary(assignment, gdf, unit_col, id_col, pop_col)
    top_split = (
        summary[unit_col].tolist()[:5]
        if not summary.empty else []
    )

    return {
        "n_comunas_partidas":     int(n_split),
        "share_comunas_partidas": round(n_split / n_total, 4) if n_total else 0.0,
        "split_severity":         round(float(severity), 4),
        "small_fragments":        int(small),
        "comunas_mas_partidas":   top_split,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _build_assignment_df(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str,
    id_col: str,
) -> pd.DataFrame:
    """
    Construye DataFrame {id_col, unit_col, district} desde la asignación.

    Maneja dos formatos de claves en assignment:
    - Strings: ID_DIST → asignación post-reconstrucción (preferido)
    - Enteros: índices de nodo gerrychain (fallback con iloc)
    """
    if unit_col not in gdf.columns or id_col not in gdf.columns:
        return pd.DataFrame()

    id_to_unit = dict(zip(gdf[id_col], gdf[unit_col]))
    rows = []

    for node_id, district in assignment.items():
        unit_val = id_to_unit.get(node_id)
        if unit_val is None and isinstance(node_id, (int, np.integer)):
            idx = int(node_id)
            if idx < len(gdf):
                unit_val = gdf[unit_col].iloc[idx]
        if unit_val is not None:
            rows.append({id_col: node_id, unit_col: unit_val,
                         "district": district})

    return pd.DataFrame(rows)


def _empty_summary_df(unit_col: str) -> pd.DataFrame:
    return pd.DataFrame(columns=[
        unit_col, "nombre", "n_fragmentos", "distritos",
        "pop_total", "pop_share_total", "split_severity",
    ])
