"""
engines.samplers.accept
=========================
Aceptación Metropolis penalizada por severidad de partición — capa 2 (Engines).

Mecánica de motor para el modo "soft": en vez de rechazar duro (como la
regla legal de ``rules.constraints``), un paso que aumenta la severidad
de partición ponderada se acepta con probabilidad exp(-Δseveridad_ponderada)
(criterio de Metropolis), igual que gerrychain.accept.cut_edge_accept
pero sobre severidad de partición en lugar de aristas cortadas. Cada
columna soft puede tener su propio peso (ScenarioConfig.
resolved_split_penalty()) — para preservación de un solo nivel con un
peso uniforme (el caso histórico) esto equivale a
exp(-split_penalty × Δseveridad).

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


def make_split_penalty_accept(resolved_split_penalty: dict) -> Callable:
    """
    Construye la función accept() para gerrychain.MarkovChain que hace que
    preserve_mode="soft" tenga un efecto real sobre qué planes entran al
    ensemble: un paso que no aumenta la severidad de partición ponderada
    (updater "split_severity") se acepta siempre; un paso que la aumenta
    se acepta con probabilidad exp(-Δseveridad_ponderada) (criterio de
    Metropolis), igual que gerrychain.accept.cut_edge_accept pero sobre
    severidad de partición en lugar de aristas cortadas.

    Preservación multinivel: el updater "split_severity" (ver
    engines.samplers.updaters.make_split_severity_updater) expone un dict
    {columna: severidad}, no un escalar — permite que cada columna soft
    tenga su propio peso vía ScenarioConfig.resolved_split_penalty(), en
    vez de un único split_penalty aplicado a la severidad total. Para
    preservación de un solo nivel (el caso histórico, ej. solo "CUT" con
    un split_penalty uniforme), esto reproduce exactamente el criterio
    anterior: severidad_ponderada = peso × severidad, así que
    Δ_ponderada = peso × Δseveridad — misma decisión de aceptación, misma
    probabilidad.

    Requiere que el updater "split_severity" esté registrado en la
    partición.

    Parameters
    ----------
    resolved_split_penalty : dict[str, float]
        Peso de penalización por columna soft — salida de
        ScenarioConfig.resolved_split_penalty(). Columnas ausentes del
        dict (ej. hard/none, o soft con peso 0) no aportan penalización.

    Returns
    -------
    Callable(partition) → bool
    """
    def _accept(partition) -> bool:
        if partition.parent is None:
            return True
        severity_old = partition.parent["split_severity"]  # dict {col: float}
        severity_new = partition["split_severity"]

        weighted_old = sum(
            resolved_split_penalty.get(col, 0.0) * val
            for col, val in severity_old.items()
        )
        weighted_new = sum(
            resolved_split_penalty.get(col, 0.0) * val
            for col, val in severity_new.items()
        )

        if weighted_new <= weighted_old:
            return True
        return random.random() < np.exp(-(weighted_new - weighted_old))

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
    resolved_modes   = scenario.resolved_preserve_mode()
    resolved_penalty = scenario.resolved_split_penalty()
    soft_cols        = [col for col, mode in resolved_modes.items() if mode == "soft"]

    if not soft_cols:
        return base_score

    try:
        from ..metrics import split_severity_index
    except ImportError:
        return base_score

    penalty = 0.0
    for col in soft_cols:
        if col in gdf.columns:
            severity = split_severity_index(
                plan_assignment, gdf,
                unit_col=col,
                id_col=scenario.decision_unit,
                pop_col=scenario.pop_col,
            )
            penalty += resolved_penalty.get(col, 0.0) * severity

    return base_score - penalty
