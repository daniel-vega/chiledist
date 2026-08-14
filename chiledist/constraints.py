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

import random
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
# Updater de severidad de partición (para aceptación soft en la cadena principal)
# ──────────────────────────────────────────────────────────────────────────────

def make_split_severity_updater(unit_cols: list[str], pop_col: str) -> Callable:
    """
    Construye un updater de gerrychain que calcula, en cada estado de la
    cadena, el mismo índice que split_metrics.split_severity_index (sumado
    sobre todas las columnas de scenario.preserve_units, igual que
    score_with_split_penalty):

        severity = Σ_cols Σ_unidades [ (n_fragmentos - 1) × share_pob_unidad ]

    Se apoya directamente en los atributos de nodo del grafo (unit_cols,
    pop_col), sin reconstruir el GeoDataFrame, para poder evaluarse en
    cada paso de una cadena de miles de pasos.

    Parameters
    ----------
    unit_cols : list[str]
        Atributos de nodo cuya integridad se penaliza (ej. ["CUT"]).
    pop_col : str
        Atributo de nodo con la población de la unidad de decisión.

    Returns
    -------
    Callable(partition) → float
    """
    def _severity_for_col(graph, assignment, unit_col: str) -> float:
        pop_by_unit: dict = {}
        districts_by_unit: dict = {}

        for node in graph.nodes:
            unit = graph.nodes[node].get(unit_col)
            if unit is None:
                continue
            pop = graph.nodes[node].get(pop_col, 0) or 0
            pop_by_unit[unit] = pop_by_unit.get(unit, 0) + pop
            districts_by_unit.setdefault(unit, set()).add(assignment[node])

        total_pop = sum(pop_by_unit.values())
        if total_pop == 0:
            return 0.0

        severity = 0.0
        for unit, districts in districts_by_unit.items():
            n_frags = len(districts)
            if n_frags <= 1:
                continue
            severity += (n_frags - 1) * (pop_by_unit[unit] / total_pop)
        return severity

    def _split_severity(partition) -> float:
        graph      = partition.graph
        assignment = partition.assignment
        return sum(
            _severity_for_col(graph, assignment, col) for col in unit_cols
        )

    return _split_severity


# ──────────────────────────────────────────────────────────────────────────────
# Aceptación Metropolis penalizada por severidad de partición (modo soft)
# ──────────────────────────────────────────────────────────────────────────────

def make_split_penalty_accept(split_penalty: float) -> Callable:
    """
    Construye la función accept() para gerrychain.MarkovChain que hace que
    preserve_mode="soft" tenga un efecto real sobre qué planes entran al
    ensemble: un paso que no aumenta la severidad de partición (updater
    "split_severity") se acepta siempre; un paso que la aumenta se acepta
    con probabilidad exp(-split_penalty × Δseveridad) (criterio de
    Metropolis), igual que gerrychain.accept.cut_edge_accept pero sobre
    severidad de partición en lugar de aristas cortadas.

    Requiere que el updater "split_severity" (ver make_split_severity_updater)
    esté registrado en la partición.

    Parameters
    ----------
    split_penalty : float
        Peso de la penalización (mismo valor que scenario.split_penalty).

    Returns
    -------
    Callable(partition) → bool
    """
    def _accept(partition) -> bool:
        if partition.parent is None:
            return True
        severity_old = partition.parent["split_severity"]
        severity_new = partition["split_severity"]
        if severity_new <= severity_old:
            return True
        return random.random() < np.exp(
            -split_penalty * (severity_new - severity_old)
        )

    return _accept


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

    # Modo soft: registrar severidad de partición para que make_split_penalty_accept
    # pueda penalizarla en la aceptación de la cadena principal (ver run_recom_chain).
    if (scenario.preserve_mode == "soft"
            and scenario.split_penalty > 0
            and scenario.preserve_units):
        cols_presentes = [c for c in scenario.preserve_units if c in gdf.columns]
        if cols_presentes:
            updaters["split_severity"] = make_split_severity_updater(cols_presentes, pc)

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
