"""
engines.samplers.updaters
============================
Updaters de gerrychain para la cadena ReCom — capa 2 (Engines).

Mecánica de motor: qué estadísticas se recalculan en cada estado de la
cadena (población, aristas cortadas y, en modo "soft", severidad de
partición). No decide qué es legal — solo instrumenta la cadena para que
``engines.samplers.accept`` pueda penalizar en la aceptación.
"""

from __future__ import annotations
from typing import Callable, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Updater de severidad de partición (para aceptación soft en la cadena principal)
# ──────────────────────────────────────────────────────────────────────────────

def make_split_severity_updater(unit_cols: list[str], pop_col: str) -> Callable:
    """
    Construye un updater de gerrychain que calcula, en cada estado de la
    cadena, el mismo índice que engines.metrics.split_severity_index, una
    vez por columna de preservación:

        severity_col = Σ_unidades [ (n_fragmentos - 1) × share_pob_unidad ]

    Devuelve un dict {columna: severity_col} en vez de un escalar sumado
    entre columnas — necesario para que engines.samplers.accept
    (make_split_penalty_accept / score_with_split_penalty) pueda aplicar un
    peso (split_penalty) distinto por columna vía
    ScenarioConfig.resolved_split_penalty(), en vez de un único peso global
    aplicado a la severidad total. Para preservación de un solo nivel
    (unit_cols de un elemento — el caso histórico, ej. ["CUT"]), sumar el
    dict resultante reproduce exactamente el escalar que se devolvía antes.

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
    Callable(partition) → dict[str, float]
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

    def _split_severity(partition) -> dict[str, float]:
        graph      = partition.graph
        assignment = partition.assignment
        return {
            col: _severity_for_col(graph, assignment, col) for col in unit_cols
        }

    return _split_severity


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

    resolved         = scenario.resolved_preserve_mode()
    resolved_penalty = scenario.resolved_split_penalty()

    # Intentar agregar CountSplits para columnas hard-preservadas
    # (disponible en algunas versiones de gerrychain)
    hard_cols = [c for c in scenario.preserve_units
                 if resolved.get(c) == "hard" and c in gdf.columns]
    if hard_cols:
        try:
            for col in hard_cols:
                updaters[f"splits_{col}"] = gc.updaters.CountSplits(col)
        except AttributeError:
            # CountSplits no disponible en esta versión — usar constraint custom
            pass

    # Columnas soft con penalización > 0: registrar severidad de partición
    # (por columna, ver make_split_severity_updater) para que
    # engines.samplers.accept.make_split_penalty_accept pueda penalizarla
    # en la aceptación de la cadena principal (ver run_recom_chain).
    soft_cols = [
        c for c in scenario.preserve_units
        if resolved.get(c) == "soft"
        and resolved_penalty.get(c, 0) > 0
        and c in gdf.columns
    ]
    if soft_cols:
        updaters["split_severity"] = make_split_severity_updater(soft_cols, pc)

    return updaters
