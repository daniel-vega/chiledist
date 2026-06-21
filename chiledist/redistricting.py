"""
chiledist.redistricting
=======================
Módulo de compatibilidad — re-exporta desde chiledist.samplers.recom y smc.

La lógica de redistritaje se encuentra en:
    chiledist.samplers.recom  — cadenas ReCom
    chiledist.samplers.smc    — exportación R/redist
"""

from .samplers.recom import (
    initial_partition,
    run_recom,
    analyze_ensemble,
    chile_constraints,
)
from .samplers.smc import export_to_redist

__all__ = [
    "initial_partition",
    "run_recom",
    "analyze_ensemble",
    "chile_constraints",
    "export_to_redist",
]
