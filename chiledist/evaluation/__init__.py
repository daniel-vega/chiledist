"""
chiledist.evaluation
======================
Capa 4 — Political Evaluation.

Índices de proporcionalidad y malapportionment usados para evaluar
planes/mapas frente a criterios normativos (Gallagher, Loosemore-Hanby,
Rae, ENP, seat bonus, personas por escaño, peso relativo del voto,
umbral efectivo, margen del último escaño) y comparación internacional
de malapportionment (``malapportionment``).
"""

from .proportionality import (
    gallagher_index,
    loosemore_hanby,
    rae_index,
    effective_number_of_parties,
    proportionality_summary,
    seat_bonus,
)
from .district_malapportionment import (
    personas_por_escano,
    peso_relativo_del_voto,
    weighted_population_balance,
    umbral_efectivo,
    margen_ultimo_escano,
)

__all__ = [
    "gallagher_index",
    "loosemore_hanby",
    "rae_index",
    "effective_number_of_parties",
    "proportionality_summary",
    "seat_bonus",
    "personas_por_escano",
    "peso_relativo_del_voto",
    "weighted_population_balance",
    "umbral_efectivo",
    "margen_ultimo_escano",
]
