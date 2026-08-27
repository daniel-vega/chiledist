"""
evaluation.framing
====================
Texto de encuadre legislativo — capa 4 (Political Evaluation).

Convierte la clasificación técnica de un escenario (``tipo_reforma``) en
prosa apta para discusiones legislativas y reportes: qué régimen
representa y qué NO puede concluirse directamente de él.
"""

from __future__ import annotations


def reforma_context(scenario) -> str:
    """
    Texto de encuadre para uso en discusiones legislativas y reportes.
    Describe qué tipo de régimen representa el escenario y qué no puede
    concluirse directamente de él.

    Parameters
    ----------
    scenario : chiledist.domain.scenario.ScenarioConfig
    """
    _framing = {
        "vigente": (
            f"'{scenario.name}' representa el régimen legal vigente "
            "(Ley 18.700): la comuna es la unidad mínima indivisible "
            "de redistritaje. Sirve como baseline de comparación."
        ),
        "contrafactual_fuerte": (
            f"'{scenario.name}' es un escenario contrafactual de reforma fuerte: "
            "las APCs son la unidad mínima y no existe restricción de "
            "partición comunal. No es legal bajo la norma actual. "
            "La comparación con el escenario vigente estima el efecto "
            "conjunto de mayor resolución geográfica y eliminación de la "
            "restricción comunal; no aísla estos componentes por separado."
        ),
        "contrafactual_intermedio": (
            f"'{scenario.name}' es un escenario contrafactual de reforma intermedia: "
            "las APCs son la unidad mínima y la partición comunal está "
            f"permitida pero penalizada (split_penalty={scenario.split_penalty}). "
            "No es legal bajo la norma actual."
        ),
        "control_metodologico": (
            f"'{scenario.name}' es un control metodológico: las APCs son la "
            "unidad mínima pero las comunas permanecen indivisibles. "
            "Permite aislar el efecto de la resolución geográfica del "
            "efecto de eliminar la restricción comunal. No es directamente "
            "un escenario de reforma legislativa."
        ),
    }
    return _framing[scenario.tipo_reforma]
