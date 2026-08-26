"""
rules.split_rules
===================
Definición de "partición" (split) bajo la Ley 18.700 — capa 1 (Legal-as-Code).

La ley exige que la comuna (u otra unidad administrativa protegida) sea
indivisible: si sus fragmentos caen en más de un distrito, la unidad
está "partida" y el plan viola la restricción. Esta es la única regla
que ``engines.metrics`` necesita para calcular las métricas de partición
— el resto de ese módulo es cómputo geoespacial (pandas/geopandas), no
una definición legal.
"""

from __future__ import annotations


def is_split(n_districts: int) -> bool:
    """
    True si una unidad administrativa está partida: sus fragmentos caen
    en más de un distrito (viola la indivisibilidad de la Ley 18.700).
    """
    return n_districts > 1


#: Umbral bajo el cual un fragmento comunal se considera "pequeño"
#: (potencialmente artificial o políticamente manipulado) — ver
#: engines.metrics.small_fragment_count.
SMALL_FRAGMENT_MIN_POP_SHARE = 0.10
