"""
electoral
==========
Asignación de escaños por D'Hondt e índices de proporcionalidad.

Para análisis de redistritaje: dado un plan (asignación de distritos APC
a circunscripciones electorales) y datos de votos por partido a nivel
comunal, calcula resultados electorales e índices de proporcionalidad.

Flujo típico
------------
    import chiledist.electoral as elec
    import chiledist.data.servel as sv

    # 1. Cargar votos comunales (salida de sv.votos_por_comuna)
    votos = sv.votos_por_comuna(resultados_df)          # CUT, partido, votos

    # 2. Asignar magnitudes de escaño según población del plan
    magnitudes = elec.assign_seat_magnitudes(
        pop_by_district, total_seats=155, min_seats=3, max_seats=8
    )

    # 3. Agregar votos al nivel de circunscripción electoral
    votos_dist = elec.aggregate_votes(
        votos, assignment=plan_assignment, unit_col="CUT"
    )

    # 4. Correr D'Hondt por circunscripción
    resultados = elec.run_electoral_plan(votos_dist, magnitudes)

    # 5. Índices nacionales de proporcionalidad
    summary = elec.proportionality_summary(
        *elec.national_shares(resultados)
    )

Sistema electoral chileno
-------------------------
Diputados (155 escaños, 28 circunscripciones, M∈[3,8]).
Método: D'Hondt por lista/pacto; sin umbral legal explícito.
Fuente legal: Ley N°18.700 art. 109 bis (texto post reforma 2015).
"""

from .constants import (
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
    MAGNITUDES_LEGALES_LEY20840,
    MAGNITUDES_LEGALES_2021,
    normalize_party_name,
)
from .dhondt import (
    dhondt,
    dhondt_binivel,
    aggregate_votes,
    run_electoral_plan,
    run_electoral_plan_binivel,
    national_shares,
)
from .magnitudes import assign_seat_magnitudes, comparar_magnitudes
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
    umbral_efectivo,
    margen_ultimo_escano,
)
from .plan_metrics import plan_electoral_metrics

__all__ = [
    "dhondt",
    "dhondt_binivel",
    "assign_seat_magnitudes",
    "aggregate_votes",
    "run_electoral_plan",
    "run_electoral_plan_binivel",
    "national_shares",
    "gallagher_index",
    "loosemore_hanby",
    "rae_index",
    "effective_number_of_parties",
    "proportionality_summary",
    "plan_electoral_metrics",
    # malapportionment distrital
    "personas_por_escano",
    "peso_relativo_del_voto",
    "comparar_magnitudes",
    "umbral_efectivo",
    "margen_ultimo_escano",
    "seat_bonus",
    "TOTAL_ESCANOS_CAMARA",
    "MIN_ESCANOS_DISTRITO",
    "MAX_ESCANOS_DISTRITO",
    "MAGNITUDES_LEGALES_LEY20840",
    "MAGNITUDES_LEGALES_2021",
    "normalize_party_name",
]
