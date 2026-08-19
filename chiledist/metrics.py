"""
metrics.py
==========
Métricas de compacidad, balance poblacional y análisis espacial
para unidades censales chilenas. Compatible con los estándares
de ALARM/redist de Harvard.
"""

from __future__ import annotations
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

from .equivalence import CRS_METRIC


# ──────────────────────────────────────────────────────────────────────────────
# Métricas de compacidad
# ──────────────────────────────────────────────────────────────────────────────

def polsby_popper(gdf: gpd.GeoDataFrame) -> pd.Series:
    """
    Índice de Polsby-Popper: 4π·área / perímetro²

    Rango: [0, 1]. 1 = círculo perfecto. Valores bajos indican
    forma muy irregular o elongada (gerrymandering clásico).

    Usado por: ALARM, redist, Census Bureau.
    """
    gdf_m = _ensure_metric(gdf)
    return (
        4 * np.pi * gdf_m.geometry.area
        / (gdf_m.geometry.length ** 2)
    ).rename("polsby_popper")


def reock(gdf: gpd.GeoDataFrame) -> pd.Series:
    """
    Índice de Reock: área / área del círculo mínimo circunscrito.

    Rango: [0, 1]. 1 = círculo perfecto. Sensible a elongaciones.
    """
    gdf_m  = _ensure_metric(gdf)
    areas  = gdf_m.geometry.area
    mbc_areas = gdf_m.geometry.apply(
        lambda g: _minimum_bounding_circle_area(g)
    )
    return (areas / mbc_areas).rename("reock")


def convex_hull_ratio(gdf: gpd.GeoDataFrame) -> pd.Series:
    """
    Razón área / área del casco convexo.

    Rango: [0, 1]. Detecta formas cóncavas o con protuberancias.
    """
    gdf_m = _ensure_metric(gdf)
    return (
        gdf_m.geometry.area / gdf_m.geometry.convex_hull.area
    ).rename("convex_hull_ratio")


def schwartzberg(gdf: gpd.GeoDataFrame) -> pd.Series:
    """
    Índice de Schwartzberg: 1 / (perímetro / (2π·√(área/π)))
    = razón entre el perímetro del círculo isoperimétrico y el real.

    Rango: (0, 1]. 1 = círculo perfecto.
    """
    gdf_m = _ensure_metric(gdf)
    area  = gdf_m.geometry.area
    perim = gdf_m.geometry.length
    return (
        (2 * np.pi * np.sqrt(area / np.pi)) / perim
    ).rename("schwartzberg")


def all_compactness(gdf: gpd.GeoDataFrame, id_col: str) -> pd.DataFrame:
    """
    Calcula todas las métricas de compacidad para cada unidad.

    Returns
    -------
    pd.DataFrame con columnas: id, polsby_popper, reock,
                                convex_hull_ratio, schwartzberg.
    """
    result = pd.DataFrame({id_col: gdf[id_col]})
    result["polsby_popper"]    = polsby_popper(gdf).values
    result["reock"]            = reock(gdf).values
    result["convex_hull_ratio"] = convex_hull_ratio(gdf).values
    result["schwartzberg"]     = schwartzberg(gdf).values
    result["compactness_mean"] = result[[
        "polsby_popper", "reock", "convex_hull_ratio", "schwartzberg"
    ]].mean(axis=1)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Balance poblacional
# ──────────────────────────────────────────────────────────────────────────────

def population_balance(
    gdf: gpd.GeoDataFrame,
    pop_col: str,
    partition_col: str,
    id_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Calcula el balance poblacional de un conjunto de distritos.

    En redistritaje, el criterio «one person, one vote» exige que
    todos los distritos tengan población lo más similar posible.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Unidades con columna de población.
    pop_col : str
        Columna de población (ej. 'viviendas').
    partition_col : str
        Columna que define el distrito/agrupación.
    id_col : str, optional
        Columna de nombre o etiqueta del distrito.

    Returns
    -------
    pd.DataFrame con métricas por distrito:
        population, ideal, deviation_abs, deviation_pct, within_5pct.
    """
    grouped = gdf.groupby(partition_col)[pop_col].sum()
    ideal   = grouped.mean()
    total   = grouped.sum()

    result = pd.DataFrame({
        "distrito":        grouped.index,
        "population":      grouped.values,
        "ideal":           ideal,
        "deviation_abs":   grouped.values - ideal,
        "deviation_pct":   (grouped.values - ideal) / ideal * 100,
        "within_5pct":     np.abs((grouped.values - ideal) / ideal) <= 0.05,
    })

    result["max_deviation_pct"] = result["deviation_pct"].abs().max()

    if id_col and id_col in gdf.columns:
        labels = gdf.groupby(partition_col)[id_col].first()
        result = result.merge(
            labels.rename("label").reset_index(),
            on=partition_col, how="left"
        )

    print(f"\n── Balance poblacional ({'viviendas' if pop_col=='viviendas' else pop_col}) ──")
    print(f"  Total unidades  : {len(grouped):,}")
    print(f"  Población total : {int(total):,}")
    print(f"  Ideal por dist. : {ideal:,.1f}")
    print(f"  Desviación máx. : {result['deviation_pct'].abs().max():.2f}%")
    print(f"  Dentro ±5%      : {result['within_5pct'].sum()} / {len(result)}")

    return result


def ideal_population(
    gdf: gpd.GeoDataFrame,
    pop_col: str,
    n_districts: int,
) -> float:
    """Población ideal por distrito dado un número objetivo de distritos."""
    return gdf[pop_col].sum() / n_districts


# ──────────────────────────────────────────────────────────────────────────────
# Métricas espaciales por nivel
# ──────────────────────────────────────────────────────────────────────────────

def spatial_summary(
    gdf: gpd.GeoDataFrame,
    id_col: str,
    pop_col: Optional[str] = None,
    group_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Resumen espacial completo: área, perímetro, compacidad y población.

    Parameters
    ----------
    group_col : str, optional
        Si se especifica, agrega por este grupo (ej. 'N_REGION').
    """
    gdf_m  = _ensure_metric(gdf)
    result = gdf[[id_col]].copy()

    result["area_km2"]     = gdf_m.geometry.area / 1e6
    result["perimetro_km"] = gdf_m.geometry.length / 1e3
    result["polsby_popper"] = polsby_popper(gdf_m).values
    result["schwartzberg"]  = schwartzberg(gdf_m).values

    if pop_col and pop_col in gdf.columns:
        result["poblacion"] = gdf[pop_col].values
        result["densidad_viv_km2"] = (
            result["poblacion"] / result["area_km2"].replace(0, np.nan)
        )

    if group_col and group_col in gdf.columns:
        result[group_col] = gdf[group_col].values
        agg_dict = {
            "area_km2":      "sum",
            "polsby_popper": "mean",
            "schwartzberg":  "mean",
        }
        # "poblacion" es el nombre interno en result (no pop_col)
        if pop_col and pop_col in gdf.columns:
            agg_dict["poblacion"]      = "sum"
            agg_dict["densidad_viv_km2"] = "mean"
        summary = result.groupby(group_col).agg(agg_dict).round(3).reset_index()
        return summary

    return result.round(3)


# ──────────────────────────────────────────────────────────────────────────────
# Métricas de redistritaje (análogas a ALARM/redist)
# ──────────────────────────────────────────────────────────────────────────────

def cut_edges(
    adj: "sp.csr_matrix",
    assignment: dict | pd.Series,
    id_list: list,
) -> int:
    """
    Cuenta aristas cortadas en un plan de redistritaje.

    Una arista es 'cortada' si sus dos nodos pertenecen a distritos distintos.
    Minimizar aristas cortadas tiende a producir distritos más compactos.

    Compatible con la métrica cut_edges de gerrychain/redist.

    Parameters
    ----------
    assignment : dict | pd.Series
        {id_unidad: id_distrito}
    """
    if isinstance(assignment, pd.Series):
        assignment = assignment.to_dict()

    adj_coo = adj.tocoo()
    cuts    = 0
    for i, j in zip(adj_coo.row, adj_coo.col):
        if i >= j:
            continue
        id_i = id_list[i]
        id_j = id_list[j]
        if assignment.get(id_i) != assignment.get(id_j):
            cuts += 1
    return cuts


def contiguity_check(
    adj: "sp.csr_matrix",
    assignment: dict | pd.Series,
    id_list: list,
) -> dict[str, bool]:
    """
    Verifica que cada distrito en el plan sea geográficamente contiguo.

    Returns
    -------
    dict {distrito: es_contiguo}
    """
    import networkx as nx

    if isinstance(assignment, pd.Series):
        assignment = assignment.to_dict()

    # Agrupar nodos por distrito
    districts: dict[str, list[int]] = {}
    for i, id_ in enumerate(id_list):
        d = assignment.get(id_)
        if d is not None:
            districts.setdefault(d, []).append(i)

    adj_coo = adj.tocoo()
    result  = {}

    for district, nodes in districts.items():
        node_set = set(nodes)
        subg     = nx.Graph()
        subg.add_nodes_from(nodes)
        for i, j in zip(adj_coo.row, adj_coo.col):
            if i in node_set and j in node_set:
                subg.add_edge(i, j)
        result[district] = nx.is_connected(subg) if len(nodes) > 1 else True

    n_ok = sum(result.values())
    print(f"  Contiguidad: {n_ok}/{len(result)} distritos son contiguos")
    return result


def plan_summary(
    gdf: gpd.GeoDataFrame,
    assignment: dict | pd.Series,
    id_col: str,
    pop_col: str,
    adj: Optional["sp.csr_matrix"] = None,
    id_list: Optional[list] = None,
) -> pd.DataFrame:
    """
    Resumen completo de un plan de redistritaje: población,
    compacidad y aristas cortadas por distrito.
    """
    if isinstance(assignment, pd.Series):
        assignment = assignment.to_dict()

    gdf = gdf.copy()
    gdf["__distrito__"] = gdf[id_col].map(assignment)

    # Disolver por distrito
    gdf_m  = _ensure_metric(gdf)
    groups = gdf_m.groupby("__distrito__")

    rows = []
    for d, g in groups:
        geom  = unary_union(g.geometry)
        area  = geom.area / 1e6
        perim = geom.length / 1e3
        pp    = 4 * np.pi * geom.area / (geom.length ** 2)
        pop   = g[pop_col].sum() if pop_col in g.columns else np.nan

        rows.append({
            "distrito":       d,
            "n_unidades":     len(g),
            "poblacion":      pop,
            "area_km2":       round(area, 2),
            "polsby_popper":  round(pp, 4),
        })

    result = pd.DataFrame(rows)

    if result["poblacion"].notna().all():
        ideal = result["poblacion"].mean()
        result["desviacion_pct"] = (
            (result["poblacion"] - ideal) / ideal * 100
        ).round(2)
        result["dentro_5pct"] = result["desviacion_pct"].abs() <= 5.0

    if adj is not None and id_list is not None:
        result["cut_edges"] = cut_edges(adj, assignment, id_list)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades internas
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_metric(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reproyecta a CRS métrico si es necesario."""
    if gdf.crs is None or gdf.crs.is_geographic:
        return gdf.to_crs(CRS_METRIC)
    return gdf


def _minimum_bounding_circle_area(geom) -> float:
    """Área del círculo mínimo circunscrito de una geometría."""
    try:
        from shapely import minimum_bounding_circle  # shapely ≥ 2.0
    except ImportError:
        from shapely.ops import minimum_bounding_circle  # shapely < 2.0
    mbc = minimum_bounding_circle(geom)
    area = mbc.area
    return area if area > 0 else np.nan