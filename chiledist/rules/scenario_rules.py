"""
rules.scenario_rules
======================
Escenarios predefinidos — capa 1 (Legal-as-Code).

Cada preset encierra una interpretación legal concreta de qué restricción
aplica al redistritaje. ``SCENARIO_LEGAL`` es el único que respeta la
Ley 18.700 (comuna indivisible); el resto son contrafactuales de reforma,
explícitamente no vigentes bajo la norma actual.

    legal         → Régimen vigente: CUT indivisible (Ley 18.700).
    apc_strict    → Control metodológico: APC como unidad mínima,
                    pero comunas aún preservadas (hard). Aísla efecto
                    de resolución del efecto de restricción.
    apc_soft      → Reforma intermedia: APC como unidad mínima,
                    partición comunal permitida pero penalizada.
    apc_free      → Reforma fuerte: APC como unidad mínima,
                    sin restricción de partición comunal.

Los escenarios APC son instrumentos de análisis contrafactual:
representan lo que ocurriría bajo una reforma legislativa que
cambiara la unidad mínima legal de redistritaje desde la comuna
hacia unidades subcomunales (APC). Ninguno es legal bajo la
norma vigente. La comparación legal vs apc_* estima el efecto
conjunto de mayor resolución geográfica y menor restricción
comunal; no aísla estos dos componentes por separado.
"""

from __future__ import annotations

from ..domain.scenario import ScenarioConfig

SCENARIO_LEGAL = ScenarioConfig(
    name="legal_comunas",
    description=(
        "Régimen vigente (Ley 18.700): comunas indivisibles. "
        "Unidad de decisión = CUT. Baseline de comparación para H1."
    ),
    tipo_reforma="vigente",
    observation_unit="ID_DIST",
    decision_unit="CUT",
    preserve_units=["CUT"],
    preserve_mode="hard",
    # Alineado 2026-08-27 con el ensemble canónico de H1 (run cc037ac8, ver
    # SCIENTIFIC_HYPOTHESES.md). pop_source="censo2024" además requiere pasar
    # --census-path datos/poblacion_comunal_censo2024.csv por CLI.
    pop_col="personas",
    pop_tolerance=0.1,
    pop_source="censo2024",
    n_steps=50_000,
)

SCENARIO_APC_STRICT = ScenarioConfig(
    name="apc_comunas_preservadas",
    description=(
        "Control metodológico: APCs como unidad mínima, pero comunas "
        "aún preservadas con restricción hard. Permite aislar el efecto "
        "de resolución geográfica del efecto de eliminación de restricción. "
        "No es un escenario de reforma legislativa directo."
    ),
    tipo_reforma="control_metodologico",
    observation_unit="ID_DIST",
    decision_unit="ID_DIST",
    preserve_units=["CUT"],
    preserve_mode="hard",
)

SCENARIO_APC_SOFT = ScenarioConfig(
    name="contrafactual_apc_soft",
    description=(
        "Reforma intermedia: APCs como unidad mínima. Partir comunas está "
        "permitido pero penalizado. Escenario contrafactual: no es legal "
        "bajo la norma vigente."
    ),
    tipo_reforma="contrafactual_intermedio",
    observation_unit="ID_DIST",
    decision_unit="ID_DIST",
    preserve_units=["CUT"],
    preserve_mode="soft",
    split_penalty=0.25,
    # Alineado 2026-08-27 con el ensemble canónico de H1 (run 97cf1309, ver
    # SCIENTIFIC_HYPOTHESES.md). pop_source="censo2024" además requiere pasar
    # --census-path datos/poblacion_comunal_censo2024.csv por CLI.
    pop_col="personas",
    pop_tolerance=0.1,
    pop_source="censo2024",
    n_steps=50_000,
)

SCENARIO_APC_FREE = ScenarioConfig(
    name="contrafactual_apc_libre",
    description=(
        "Reforma fuerte: APCs como unidad mínima, sin restricción de "
        "partición comunal. Escenario contrafactual: no es legal bajo "
        "la norma vigente."
    ),
    tipo_reforma="contrafactual_fuerte",
    observation_unit="ID_DIST",
    decision_unit="ID_DIST",
    preserve_units=[],
    preserve_mode="none",
    # Alineado 2026-08-27 con el ensemble canónico de H1 (run 856910a5, ver
    # SCIENTIFIC_HYPOTHESES.md). pop_source="censo2024" además requiere pasar
    # --census-path datos/poblacion_comunal_censo2024.csv por CLI.
    pop_col="personas",
    pop_tolerance=0.1,
    pop_source="censo2024",
    n_steps=50_000,
)

SCENARIO_COMUNAS_HARD_REGION_SOFT = ScenarioConfig(
    name="comunas_hard_region_soft",
    decision_unit="CUT",
    preserve_units=["CUT", "COD_REGION"],
    preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
    split_penalty={"CUT": 0.0, "COD_REGION": 0.25},
    tipo_reforma="contrafactual_regional",
    description=(
        "Comunas indivisibles (hard) + penalización blanda "
        "por cruce de fronteras regionales. "
        "E2 en la tabla de escenarios de la propuesta metodológica."
    ),
)

SCENARIO_COMUNAS_HARD_REGION_HARD = ScenarioConfig(
    name="comunas_hard_region_hard",
    decision_unit="CUT",
    preserve_units=["CUT", "COD_REGION"],
    preserve_mode={"CUT": "hard", "COD_REGION": "hard"},
    tipo_reforma="contrafactual_regional",
    description=(
        "Comunas y regiones indivisibles (ambas hard). "
        "E3: preservación legal ampliada a nivel regional. "
        "⚠ Riesgo de warm-up infinito documentado en "
        "SCIENTIFIC_HYPOTHESES.md §apc_strict."
    ),
)

SCENARIO_REGION_SOFT_ONLY = ScenarioConfig(
    name="region_soft_only",
    decision_unit="CUT",
    preserve_units=["COD_REGION"],
    preserve_mode={"COD_REGION": "soft"},
    split_penalty={"COD_REGION": 0.25},
    tipo_reforma="contrafactual_regional",
    description=(
        "Solo penalización blanda por cruce regional, "
        "sin restricción comunal. "
        "E6: aísla el costo marginal de la restricción "
        "regional sin interacción con restricción comunal."
    ),
)

SCENARIOS: dict[str, ScenarioConfig] = {
    "legal":       SCENARIO_LEGAL,
    "apc_strict":  SCENARIO_APC_STRICT,
    "apc_soft":    SCENARIO_APC_SOFT,
    "apc_free":    SCENARIO_APC_FREE,
    "comunas_hard_region_soft": SCENARIO_COMUNAS_HARD_REGION_SOFT,
    "comunas_hard_region_hard": SCENARIO_COMUNAS_HARD_REGION_HARD,
    "region_soft_only":         SCENARIO_REGION_SOFT_ONLY,
}
