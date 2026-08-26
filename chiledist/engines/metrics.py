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

from chiledist.domain.equivalence import CRS_METRIC
from chiledist.rules.split_rules import is_split, SMALL_FRAGMENT_MIN_POP_SHARE


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


# ──────────────────────────────────────────────────────────────────────────────
# Métricas de comunas partidas (cómputo geoespacial; la regla de qué
# cuenta como "partida" vive en chiledist.rules.split_rules)
# ──────────────────────────────────────────────────────────────────────────────
#
# Cuantifican el impacto de partir unidades administrativas (comunas,
# provincias, regiones) en un plan de redistritaje. Centrales para
# comparar el modo legal (CUT indivisible) con el modo experimental
# (APC libre): permiten medir cuántas comunas se parten, con qué
# severidad, y qué proporción de la población queda en comunas divididas.
#
# Funciones principales:
#     count_split_units     → nº de unidades partidas
#     split_severity_index  → índice ponderado por población
#     split_unit_summary    → DataFrame detallado por unidad partida
#     small_fragment_count  → fragmentos por debajo de umbral poblacional
#     plan_split_metrics    → todas las métricas en un dict

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
    return int(n_districts_per_unit.map(is_split).sum())


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
        if not is_split(n_frags):
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
    min_pop_share: float = SMALL_FRAGMENT_MIN_POP_SHARE,
) -> int:
    """
    Cuenta fragmentos comunales que representan menos del min_pop_share
    de la población total de su unidad de origen.

    Fragmentos "pequeños" son potencialmente artificiales o políticamente
    manipulados. Un umbral de 10% es razonable para el primer análisis.

    Parameters
    ----------
    min_pop_share : float
        Umbral. Default: rules.split_rules.SMALL_FRAGMENT_MIN_POP_SHARE (0.10).

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
        frag_pop["n_frags"].map(is_split) & (frag_pop["share"] < min_pop_share)
    ]
    return len(small)


def pop_afectada_pct(
    assignment: dict,
    gdf: gpd.GeoDataFrame,
    unit_col: str,
    id_col: str,
    pop_col: str = "viviendas",
) -> float:
    """
    Fracción de la población total que reside en unidades administrativas
    que están divididas entre dos o más distritos en el plan.

    Difiere de share_comunas_partidas (fracción de *comunas* partidas):
    una sola comuna muy poblada partida puede tener share_comunas ~ 0.003
    pero pop_afectada_pct ~ 0.20.  Este indicador es el más relevante para
    una discusión legislativa sobre igualdad del voto.

    Parameters
    ----------
    assignment : dict
        {id_col_value: district_id}
    gdf : gpd.GeoDataFrame
        Con columnas id_col, unit_col y pop_col.
    unit_col : str
        Unidad cuya integridad se evalúa (ej. "CUT").
    id_col : str
        Unidad de decisión (ej. "ID_DIST").
    pop_col : str
        Columna de población.

    Returns
    -------
    float en [0, 1].  0.0 = ninguna unidad partida; 1.0 = toda la población
    reside en unidades divididas.
    """
    df = _build_assignment_df(assignment, gdf, unit_col, id_col)
    if df.empty or pop_col not in gdf.columns:
        return 0.0

    pop_map   = dict(zip(gdf[id_col], gdf[pop_col]))
    df["pop"] = df[id_col].map(pop_map).fillna(0)
    total_pop = df["pop"].sum()
    if total_pop == 0:
        return 0.0

    n_districts_per_unit = df.groupby(unit_col)["district"].nunique()
    split_units = n_districts_per_unit[n_districts_per_unit.map(is_split)].index

    pop_in_split = df[df[unit_col].isin(split_units)]["pop"].sum()
    return round(float(pop_in_split / total_pop), 4)


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
        n_comunas_partidas, share_comunas_partidas, pop_afectada_pct,
        split_severity, small_fragments,
        comunas_mas_partidas (lista de CUT)
    """
    n_total = gdf[unit_col].nunique() if unit_col in gdf.columns else 0

    n_split    = count_split_units(assignment, gdf, unit_col, id_col)
    severity   = split_severity_index(assignment, gdf, unit_col, id_col, pop_col)
    small      = small_fragment_count(assignment, gdf, unit_col, id_col, pop_col)
    pop_affect = pop_afectada_pct(assignment, gdf, unit_col, id_col, pop_col)

    summary  = split_unit_summary(assignment, gdf, unit_col, id_col, pop_col)
    top_split = (
        summary[unit_col].tolist()[:5]
        if not summary.empty else []
    )

    return {
        "n_comunas_partidas":     int(n_split),
        "share_comunas_partidas": round(n_split / n_total, 4) if n_total else 0.0,
        "pop_afectada_pct":       pop_affect,
        "split_severity":         round(float(severity), 4),
        "small_fragments":        int(small),
        "comunas_mas_partidas":   top_split,
    }


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