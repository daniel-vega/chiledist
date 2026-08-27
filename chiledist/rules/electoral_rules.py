"""
rules.electoral_rules
=======================
Parámetros legales del sistema electoral chileno (Cámara de Diputados) —
capa 1 (Legal-as-Code).

Fuente legal: Ley N°18.700 art. 109 bis / Ley 20.840 (2015), 28
circunscripciones, M∈[3,8].
"""

TOTAL_ESCANOS_CAMARA = 155
MIN_ESCANOS_DISTRITO = 3
MAX_ESCANOS_DISTRITO = 8


# ──────────────────────────────────────────────────────────────────────────────
# Configuración legal actual (28 circunscripciones, post-reforma 2015)
# ──────────────────────────────────────────────────────────────────────────────

MAGNITUDES_LEGALES_LEY20840 = {
    # 28 distritos electorales según Art. 179 Ley 18.700 modificada por Ley 20.840.
    # Fuente: BCN, Ley 20.840 (05-MAY-2015). Sin cambios en elecciones 2017, 2021, 2025.
    # Art. 179 bis: SERVEL actualiza cada 10 años según último censo (próxima actualización
    # basada en Censo 2024; sin modificación para la elección de noviembre 2025).
     1: 3,   # Arica, Camarones, Putre, General Lagos
     2: 3,   # Iquique, Alto Hospicio, Huara, Camiña, Colchane, Pica, Pozo Almonte
     3: 5,   # Tocopilla, Calama, Antofagasta, Mejillones, Taltal y otras
     4: 5,   # Chañaral, Copiapó, Vallenar y otras (Atacama)
     5: 7,   # La Serena, Coquimbo, Ovalle, Illapel y otras (Coquimbo)
     6: 8,   # Quillota, Quilpué, Los Andes, San Felipe y otras (interior V región)
     7: 8,   # Valparaíso, Viña del Mar, San Antonio y otras (litoral V región)
     8: 8,   # Maipú, Pudahuel, Quilicura, Colina y otras (RM poniente-norte)
     9: 7,   # Conchalí, Renca, Recoleta, Independencia y otras (RM norte)
    10: 8,   # Providencia, Santiago, Ñuñoa, Macul y otras (RM centro)
    11: 6,   # Las Condes, Vitacura, Lo Barnechea, La Reina, Peñalolén (RM oriente)
    12: 7,   # La Florida, Puente Alto, La Pintana y otras (RM sur-oriente)
    13: 5,   # El Bosque, La Cisterna, San Miguel, Lo Espejo y otras (RM sur)
    14: 6,   # San Bernardo, Melipilla, Talagante, Buin y otras (RM sur-poniente)
    15: 5,   # Rancagua, Rengo, Machalí y otras (O'Higgins norte)
    16: 4,   # San Fernando, Pichilemu, Santa Cruz y otras (O'Higgins sur)
    17: 7,   # Curicó, Talca, Constitución y otras (Maule norte)
    18: 4,   # Linares, Parral, Cauquenes y otras (Maule sur)
    19: 5,   # Chillán, Yumbel, Bulnes y otras (Ñuble)
    20: 8,   # Concepción, Talcahuano, Coronel y otras (Biobío costa)
    21: 5,   # Lota, Arauco, Los Ángeles y otras (Biobío interior)
    22: 4,   # Angol, Traiguén, Victoria y otras (Araucanía norte)
    23: 7,   # Temuco, Villarrica, Pucón y otras (Araucanía sur)
    24: 5,   # Valdivia, La Unión, Panguipulli y otras (Los Ríos)
    25: 4,   # Osorno, Puerto Varas y otras (Los Lagos norte)
    26: 5,   # Puerto Montt, Castro, Ancud, Chiloé y otras (Los Lagos sur)
    27: 3,   # Coihaique y otras (Aysén)
    28: 3,   # Punta Arenas y otras (Magallanes)
}
assert sum(MAGNITUDES_LEGALES_LEY20840.values()) == 155

# Alias histórico: las magnitudes de Ley 20.840 no fueron modificadas en
# las elecciones de 2017, 2021 ni 2025. Son igualmente válidas para 2026.
# Art. 179 bis establece revisión cada 10 años con el último censo disponible;
# SERVEL aún no ha emitido modificación basada en el Censo 2024.
# Usar MAGNITUDES_LEGALES_LEY20840 en código nuevo; este alias existe solo
# para compatibilidad con scripts que lo referencian por año de elección.
MAGNITUDES_LEGALES_2021 = MAGNITUDES_LEGALES_LEY20840


# ──────────────────────────────────────────────────────────────────────────────
# Actualización Censo 2024 (post Resolución O 129/2026, SERVEL, 18-ABR-2026)
# ──────────────────────────────────────────────────────────────────────────────

MAGNITUDES_CENSO2024_2026 = {
    # 28 distritos electorales, magnitudes actualizadas según Art. 179 bis
    # Ley 18.700 con población Censo 2024.
    # Fuente: SERVEL, Resolución Exenta O N°129/2026 (18-ABR-2026).
     1: 3,   2: 3,   3: 6,   4: 3,   5: 8,   6: 8,   7: 8,
     8: 8,   9: 8,  10: 8,  11: 8,  12: 8,  13: 6,  14: 8,
    15: 5,  16: 3,  17: 7,  18: 3,  19: 4,  20: 8,  21: 6,
    22: 3,  23: 6,  24: 3,  25: 3,  26: 5,  27: 3,  28: 3,
}
assert sum(MAGNITUDES_CENSO2024_2026.values()) == 155
