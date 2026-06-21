"""
constraints.py
==============
Constructores de restricciones duras y blandas para redistritaje
con gerrychain 0.3.2.

Modos de preservación:
    hard  → rechazo inmediato de planes que parten la unidad (Ley 18.700)
    soft  → sin restricción dura; penalización en score (ver split_metrics)
    none  → sin restricción de preservación

Uso con ScenarioConfig:
    updaters   = build_updaters_for_scenario(scenario, gdf)
    partition  = gc.Partition(graph, assignment, updaters)
    constraints = build_constraints_for_scenario(scenario, partition, gdf, epsilon)
"""

from __future__ import annotations
from typing import Optional, Callable

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Restricción de preservación (hard)
# ──────────────────────────────────────────────────────────────────────────────

def make_preserve_constraint(preserve_col: str) -> Callable:
    """
    Construye una restricción que rechaza planes que parten preserve_col.

    La restricción itera sobre los nodos del grafo y verifica que cada
    valor de preserve_col esté asignado a exactamente un distrito.
    Compatible con gerrychain 0.3.2 (no requiere CountSplits).

    Parameters
    ----------
    preserve_col : str
        Atributo de nodo del grafo gerrychain (ej. "CUT").

    Returns
    -------
    Callable(partition) → bool
    """
    def _no_split(partition) -> bool:
        unit_to_district: dict = {}
        for node, district in partition.assignment.items():
            unit = partition.graph.nodes[node].get(preserve_col)
            if unit is None:
                continue
            if unit in unit_to_district:
                if unit_to_district[unit] != district:
                    return False
            else:
                unit_to_district[unit] = district
        return True

    _no_split.__name__ = f"preserve_{preserve_col}"
    return _no_split


# ──────────────────────────────────────────────────────────────────────────────
# Updaters para gerrychain
# ──────────────────────────────────────────────────────────────────────────────

def build_updaters_for_scenario(
    scenario,
    gdf,
    pop_col: Optional[str] = None,
) -> dict:
    """
    Construye el diccionario de updaters de gerrychain según el escenario.

    Parameters
    ----------
    scenario : ScenarioConfig
    gdf : gpd.GeoDataFrame
        Con la columna pop_col (u 'viviendas' por defecto).
    pop_col : str, optional
        Override de la columna de población.

    Returns
    -------
    dict {nombre: updater} para gc.Partition(updaters=...).
    """
    try:
        import gerrychain as gc
    except ImportError:
        raise ImportError("gerrychain no está instalado.")

    pc = pop_col or scenario.pop_col

    updaters = {
        "population": gc.updaters.Tally(pc, alias="population"),
        "cut_edges":  gc.updaters.cut_edges,
    }

    # Intentar agregar CountSplits para columnas de preservación
    # (disponible en algunas versiones de gerrychain)
    if scenario.preserve_mode == "hard" and scenario.preserve_units:
        try:
            for col in scenario.preserve_units:
                if col in gdf.columns:
                    updaters[f"splits_{col}"] = gc.updaters.CountSplits(col)
        except AttributeError:
            # CountSplits no disponible en esta versión — usar constraint custom
            pass

    return updaters


# ──────────────────────────────────────────────────────────────────────────────
# Lista completa de restricciones para la cadena principal
# ──────────────────────────────────────────────────────────────────────────────

def build_constraints_for_scenario(
    scenario,
    partition,
    gdf,
    epsilon: float,
) -> list:
    """
    Construye la lista completa de restricciones para gerrychain según
    el ScenarioConfig.

    Parameters
    ----------
    scenario : ScenarioConfig
    partition : gc.Partition (post-warmup, para calibrar epsilon)
    gdf : gpd.GeoDataFrame
    epsilon : float
        Tolerancia de balance poblacional calibrada post-warmup.

    Returns
    -------
    list de callables.
    """
    try:
        from gerrychain.constraints import contiguous
        import gerrychain as gc
    except ImportError:
        raise ImportError("gerrychain no está instalado.")

    constraints = [contiguous]

    pop_constraint = gc.constraints.within_percent_of_ideal_population(
        partition, epsilon
    )
    constraints.append(pop_constraint)

    if scenario.preserve_mode == "hard":
        for col in scenario.preserve_units:
            if col in gdf.columns:
                constraints.append(make_preserve_constraint(col))
                print(f"  Restricción dura: preservar '{col}' (Ley 18.700)")

    # Modo soft: la penalización va al score (ver split_metrics.score_with_split_penalty)
    # Modo none: sin restricción de preservación

    return constraints


# ──────────────────────────────────────────────────────────────────────────────
# Score ajustado con penalización de splits (modo soft)
# ──────────────────────────────────────────────────────────────────────────────

def score_with_split_penalty(
    base_score: float,
    plan_assignment: dict,
    gdf,
    scenario,
) -> float:
    """
    Ajusta el score de un plan aplicando la penalización por comunas
    partidas en modo soft.

    Parameters
    ----------
    base_score : float
        Score base (antes de penalización).
    plan_assignment : dict
        {id_col_str: district_id} — asignación post-reconstrucción.
    gdf : gpd.GeoDataFrame
        Con scenario.decision_unit e scenario.preserve_units.
    scenario : ScenarioConfig

    Returns
    -------
    float
    """
    if scenario.preserve_mode != "soft" or scenario.split_penalty <= 0:
        return base_score

    try:
        from .split_metrics import split_severity_index
    except ImportError:
        return base_score

    penalty = 0.0
    for col in scenario.preserve_units:
        if col in gdf.columns:
            severity = split_severity_index(
                plan_assignment, gdf,
                unit_col=col,
                id_col=scenario.decision_unit,
                pop_col=scenario.pop_col,
            )
            penalty += severity

    return base_score - scenario.split_penalty * penalty
