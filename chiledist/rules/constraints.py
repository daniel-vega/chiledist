"""
rules.constraints
===================
Restricción legal de preservación (Ley 18.700) — capa 1 (Legal-as-Code).

``make_preserve_constraint`` rechaza de forma dura cualquier plan que
parta la unidad protegida; ``build_constraints_for_scenario`` ensambla
la lista completa de restricciones de gerrychain para un
``ScenarioConfig``, incluida esa restricción legal cuando
``preserve_mode == "hard"``.

La mecánica de aceptación probabilística para el modo "soft" (que no
rechaza planes sino que los penaliza en el score) es maquinaria de motor,
no una regla legal — ver ``engines.samplers.updaters`` y
``engines.samplers.accept``.
"""

from __future__ import annotations
from typing import Callable


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

    # Modo soft: la penalización va al score (ver engines.samplers.accept)
    # Modo none: sin restricción de preservación

    return constraints
