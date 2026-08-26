"""
chiledist.engines.allocation
==============================
Motor de asignación de escaños electorales: D'Hondt (uni y binivel),
asignación de magnitudes por distrito y el agregador de métricas
electorales de un plan completo.
"""

from .dhondt import (
    dhondt,
    dhondt_binivel,
    aggregate_votes,
    run_electoral_plan,
    run_electoral_plan_binivel,
    national_shares,
)
from .magnitudes import (
    assign_seat_magnitudes,
    assign_seat_magnitudes_dhondt,
    comparar_magnitudes,
)
from .plan_metrics import plan_electoral_metrics

__all__ = [
    "dhondt",
    "dhondt_binivel",
    "aggregate_votes",
    "run_electoral_plan",
    "run_electoral_plan_binivel",
    "national_shares",
    "assign_seat_magnitudes",
    "assign_seat_magnitudes_dhondt",
    "comparar_magnitudes",
    "plan_electoral_metrics",
]
