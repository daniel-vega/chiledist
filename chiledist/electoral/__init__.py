"""
electoral
==========
Constantes legales del sistema electoral chileno (Cámara de Diputados) y
normalización de nombres de partido/pacto.

Nota — refactor arquitectural (capas)
--------------------------------------
Este paquete contenía antes también la asignación de escaños (D'Hondt,
magnitudes) y los índices de proporcionalidad/malapportionment. Esos
módulos se movieron a sus capas correspondientes:

    D'Hondt, magnitudes, plan_electoral_metrics
        → chiledist.engines.allocation
    Proporcionalidad (Gallagher, Loosemore-Hanby, Rae, ENP, seat_bonus),
    malapportionment distrital (personas_por_escano, peso_relativo_del_voto,
    umbral_efectivo, margen_ultimo_escano)
        → chiledist.evaluation

``electoral.constants`` permanece aquí porque mezcla parámetros técnicos
(``normalize_party_name``) con constantes legales (``MAGNITUDES_LEGALES_LEY20840``)
y aún no se ha separado — ver plan de migración, etapa posterior.
"""

from .constants import (
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
    MAGNITUDES_LEGALES_LEY20840,
    MAGNITUDES_LEGALES_2021,
    MAGNITUDES_CENSO2024_2026,
    normalize_party_name,
)

__all__ = [
    "TOTAL_ESCANOS_CAMARA",
    "MIN_ESCANOS_DISTRITO",
    "MAX_ESCANOS_DISTRITO",
    "MAGNITUDES_LEGALES_LEY20840",
    "MAGNITUDES_LEGALES_2021",
    "MAGNITUDES_CENSO2024_2026",
    "normalize_party_name",
]
