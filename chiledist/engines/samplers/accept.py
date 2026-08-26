"""
engines.samplers.accept
=========================
Aceptación Metropolis penalizada por severidad de partición — capa 2 (Engines).

Mecánica de motor para el modo "soft": en vez de rechazar duro (como la
regla legal de ``rules.constraints``), un paso que aumenta la severidad
de partición se acepta con probabilidad exp(-split_penalty × Δseveridad)
(criterio de Metropolis), igual que gerrychain.accept.cut_edge_accept
pero sobre severidad de partición en lugar de aristas cortadas.

Nota: al momento de este refactor ninguna de las dos funciones de este
módulo está conectada por ``engines.samplers.recom.run_recom_chain``
(que usa ``gc.accept.always_accept`` incondicionalmente) — se relocalizan
tal cual, sin cambiar su comportamiento ni conectarlas, para no agregar
funcionalidad nueva ni alterar resultados numéricos.
"""

from __future__ import annotations
from typing import Callable

import random
import numpy as np


def make_split_penalty_accept(split_penalty: float) -> Callable:
    """
    Construye la función accept() para gerrychain.MarkovChain que hace que
    preserve_mode="soft" tenga un efecto real sobre qué planes entran al
    ensemble: un paso que no aumenta la severidad de partición (updater
    "split_severity") se acepta siempre; un paso que la aumenta se acepta
    con probabilidad exp(-split_penalty × Δseveridad) (criterio de
    Metropolis), igual que gerrychain.accept.cut_edge_accept pero sobre
    severidad de partición en lugar de aristas cortadas.

    Requiere que el updater "split_severity" (ver
    engines.samplers.updaters.make_split_severity_updater) esté
    registrado en la partición.

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
        from ..metrics import split_severity_index
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
