"""
config.py
=========
ScenarioConfig: objeto de configuración para escenarios de redistritaje.

Escenarios predefinidos
-----------------------
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
import warnings
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Dataclass principal
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ScenarioConfig:
    """
    Configuración de un escenario de redistritaje.

    Separa cuatro conceptos:
        observation_unit  → nivel donde están los datos censales
        decision_unit     → unidad que el algoritmo puede mover
        preserve_units    → unidades que no se deben partir (o se penalizan)
        preserve_mode     → hard | soft | none

    Uso rápido
    ----------
    >>> from chiledist.config import SCENARIO_LEGAL, SCENARIO_APC_FREE
    >>> legal = SCENARIO_LEGAL
    >>> # o desde YAML:
    >>> cfg = load_scenario("scenarios/legal_comunas.yml")
    """

    name: str = "default"
    description: str = ""

    # Clasificación del escenario para framing legislativo
    # "vigente"               → marco legal actual
    # "contrafactual_fuerte"  → reforma sin restricción comunal
    # "contrafactual_intermedio" → reforma con penalización
    # "control_metodologico"  → apc_strict; para descomponer mecanismo
    tipo_reforma: str = "vigente"

    # Unidades geográficas
    observation_unit: str = "ID_DIST"   # unidad de los datos de entrada
    decision_unit: str = "CUT"          # unidad mínima que ReCom puede mover

    # Preservación de límites administrativos
    preserve_units: list[str] = field(default_factory=list)
    preserve_mode: str = "hard"         # "hard" | "soft" | "none"
    split_penalty: float = 0.0          # peso de la penalización en modo soft
    min_fragment_pop_share: float = 0.0 # umbral mínimo de fragmento comunal

    # Parámetros demográficos
    pop_col: str = "viviendas"
    pop_tolerance: float = 0.05
    pop_source: Optional[str] = None   # fuente efectiva de población (ej. "manzana", "padron")

    # Parámetros del sampler
    sampler: str = "recom"
    n_districts: int = 8
    n_steps: int = 10_000
    n_steps_warmup: int = 500
    seed: int = 42

    # Conectividad e islas
    contiguity: str = "queen"
    island_policy: str = "nearest"
    island_threshold_km: float = 50.0   # solo relevante con island_policy="threshold"

    # CRS métrico (None = auto-detectar desde los datos)
    crs_metric: Optional[str] = None

    def validate(self) -> None:
        """Verifica la coherencia interna de la configuración."""
        valid_units = {"CUT", "ID_DIST", "MANZENT"}
        if self.decision_unit not in valid_units:
            raise ValueError(
                f"decision_unit '{self.decision_unit}' no reconocida. "
                f"Opciones: {sorted(valid_units)}"
            )

        valid_tipos = {"vigente", "contrafactual_fuerte",
                       "contrafactual_intermedio", "control_metodologico"}
        if self.tipo_reforma not in valid_tipos:
            raise ValueError(
                f"tipo_reforma '{self.tipo_reforma}' no reconocido. "
                f"Opciones: {sorted(valid_tipos)}"
            )

        valid_modes = {"hard", "soft", "none"}
        if self.preserve_mode not in valid_modes:
            raise ValueError(
                f"preserve_mode '{self.preserve_mode}' no reconocido. "
                f"Opciones: {sorted(valid_modes)}"
            )

        if self.preserve_mode == "hard" and not self.preserve_units:
            raise ValueError(
                "preserve_mode='hard' requiere al menos un elemento en "
                "preserve_units."
            )

        if self.preserve_mode == "soft" and self.split_penalty == 0.0:
            warnings.warn(
                "preserve_mode='soft' con split_penalty=0.0 no tiene efecto. "
                "Considera usar preserve_mode='none' o establecer split_penalty > 0.",
                stacklevel=2,
            )

        valid_island = {"nearest", "threshold", "none"}
        if self.island_policy not in valid_island:
            raise ValueError(
                f"island_policy '{self.island_policy}' no reconocida. "
                f"Opciones: {sorted(valid_island)}"
            )

        if self.island_policy == "threshold" and self.island_threshold_km <= 0:
            raise ValueError("island_threshold_km debe ser > 0.")

        if self.n_districts < 2:
            raise ValueError("n_districts debe ser >= 2.")

        if not 0 < self.pop_tolerance < 1:
            raise ValueError("pop_tolerance debe estar en (0, 1).")

        if self.pop_col == "viviendas" and self.preserve_mode != "none":
            warnings.warn(
                "pop_col='viviendas' usa unidades de vivienda como proxy de población. "
                "La relación viviendas/personas varía por densidad y región (~2.1 en RM, "
                "~2.8 en zonas rurales), lo que puede alterar qué planes pasan el criterio "
                "de balance. Para resultados publicables usa el Censo 2024 "
                "(pop_col='personas') o el padrón SERVEL (pop_col='inscritos').",
                UserWarning,
                stacklevel=2,
            )

    def __str__(self) -> str:
        return (
            f"ScenarioConfig("
            f"name={self.name!r}, "
            f"decision_unit={self.decision_unit!r}, "
            f"preserve_mode={self.preserve_mode!r}, "
            f"preserve_units={self.preserve_units})"
        )

    def reforma_context(self) -> str:
        """
        Texto de encuadre para uso en discusiones legislativas y reportes.
        Describe qué tipo de régimen representa el escenario y qué no puede
        concluirse directamente de él.
        """
        _framing = {
            "vigente": (
                f"'{self.name}' representa el régimen legal vigente "
                "(Ley 18.700): la comuna es la unidad mínima indivisible "
                "de redistritaje. Sirve como baseline de comparación."
            ),
            "contrafactual_fuerte": (
                f"'{self.name}' es un escenario contrafactual de reforma fuerte: "
                "las APCs son la unidad mínima y no existe restricción de "
                "partición comunal. No es legal bajo la norma actual. "
                "La comparación con el escenario vigente estima el efecto "
                "conjunto de mayor resolución geográfica y eliminación de la "
                "restricción comunal; no aísla estos componentes por separado."
            ),
            "contrafactual_intermedio": (
                f"'{self.name}' es un escenario contrafactual de reforma intermedia: "
                "las APCs son la unidad mínima y la partición comunal está "
                f"permitida pero penalizada (split_penalty={self.split_penalty}). "
                "No es legal bajo la norma actual."
            ),
            "control_metodologico": (
                f"'{self.name}' es un control metodológico: las APCs son la "
                "unidad mínima pero las comunas permanecen indivisibles. "
                "Permite aislar el efecto de la resolución geográfica del "
                "efecto de eliminar la restricción comunal. No es directamente "
                "un escenario de reforma legislativa."
            ),
        }
        return _framing[self.tipo_reforma]

    def summary(self) -> str:
        """Texto descriptivo del escenario para logs."""
        lines = [
            f"Escenario: {self.name}",
            f"  Descripción    : {self.description or '—'}",
            f"  Unidad decisión: {self.decision_unit}",
            f"  Modo preserv.  : {self.preserve_mode}",
        ]
        if self.preserve_units:
            lines.append(f"  Preservar      : {', '.join(self.preserve_units)}")
        if self.preserve_mode == "soft":
            lines.append(f"  Split penalty  : {self.split_penalty}")
        island_str = self.island_policy
        if self.island_policy == "threshold":
            island_str += f" ({self.island_threshold_km} km)"
        crs_str = self.crs_metric or "auto"
        lines += [
            f"  Pop col        : {self.pop_col}",
            f"  Pop tolerancia : ±{self.pop_tolerance*100:.0f}%",
            f"  Sampler        : {self.sampler}",
            f"  Steps          : {self.n_steps:,}",
            f"  Seed           : {self.seed}",
            f"  Islas          : {island_str}",
            f"  CRS métrico    : {crs_str}",
        ]
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Escenarios predefinidos
# ──────────────────────────────────────────────────────────────────────────────

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
)

SCENARIOS: dict[str, ScenarioConfig] = {
    "legal":       SCENARIO_LEGAL,
    "apc_strict":  SCENARIO_APC_STRICT,
    "apc_soft":    SCENARIO_APC_SOFT,
    "apc_free":    SCENARIO_APC_FREE,
}


# ──────────────────────────────────────────────────────────────────────────────
# I/O de escenarios
# ──────────────────────────────────────────────────────────────────────────────

def load_scenario(path: str) -> ScenarioConfig:
    """
    Carga un ScenarioConfig desde un archivo YAML.

    Requiere: pip install pyyaml

    Parameters
    ----------
    path : str
        Ruta al archivo .yml o .yaml.

    Returns
    -------
    ScenarioConfig validado.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML no está instalado. Instala con: pip install pyyaml"
        )

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Mapear estructura YAML anidada a campos planos
    preserve    = data.pop("preserve", {}) or {}
    population  = data.pop("population", {}) or {}
    sampler_cfg = data.pop("sampler", {}) or {}
    districts   = data.pop("districts", {}) or {}

    flat = {k: v for k, v in data.items()}

    flat.setdefault("preserve_units",          preserve.get("units", []))
    flat.setdefault("preserve_mode",           preserve.get("mode", "none"))
    flat.setdefault("split_penalty",           preserve.get("split_penalty", 0.0))
    flat.setdefault("min_fragment_pop_share",  preserve.get("min_fragment_pop_share", 0.0))

    flat.setdefault("pop_col",       population.get("column", "viviendas"))
    flat.setdefault("pop_tolerance", population.get("tolerance", 0.05))
    flat.setdefault("pop_source",    population.get("source", None))

    flat.setdefault("sampler",         sampler_cfg.get("method", "recom"))
    flat.setdefault("n_steps",         sampler_cfg.get("n_steps", 10_000))
    flat.setdefault("n_steps_warmup",  sampler_cfg.get("n_steps_warmup", 500))
    flat.setdefault("seed",            sampler_cfg.get("seed", 42))

    flat.setdefault("n_districts", districts.get("n_districts", flat.pop("n_districts", 8)))

    connectivity = data.pop("connectivity", {}) or {}
    flat.setdefault("contiguity",          connectivity.get("contiguity",
                                           flat.get("contiguity", "queen")))
    flat.setdefault("island_policy",       connectivity.get("island_policy",
                                           flat.get("island_policy", "nearest")))
    flat.setdefault("island_threshold_km", connectivity.get("island_threshold_km",
                                           flat.get("island_threshold_km", 50.0)))
    flat.setdefault("crs_metric",          connectivity.get("crs_metric",
                                           flat.get("crs_metric", None)))

    # Filtrar solo campos reconocidos
    valid_fields = {
        "name", "description", "tipo_reforma",
        "observation_unit", "decision_unit",
        "preserve_units", "preserve_mode", "split_penalty",
        "min_fragment_pop_share", "pop_col", "pop_tolerance", "pop_source",
        "sampler", "n_districts", "n_steps", "n_steps_warmup", "seed",
        "contiguity", "island_policy", "island_threshold_km", "crs_metric",
    }
    flat = {k: v for k, v in flat.items() if k in valid_fields}

    cfg = ScenarioConfig(**flat)
    cfg.validate()
    return cfg


def save_scenario(config: ScenarioConfig, path: str) -> None:
    """
    Exporta un ScenarioConfig a YAML.

    Requiere: pip install pyyaml
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML no está instalado.")

    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    data = {
        "name":             config.name,
        "description":      config.description,
        "tipo_reforma":     config.tipo_reforma,
        "observation_unit": config.observation_unit,
        "decision_unit":    config.decision_unit,
        "preserve": {
            "units":        config.preserve_units,
            "mode":         config.preserve_mode,
            "split_penalty": config.split_penalty,
            "min_fragment_pop_share": config.min_fragment_pop_share,
        },
        "population": {
            "column":    config.pop_col,
            "tolerance": config.pop_tolerance,
            "source":    config.pop_source,
        },
        "districts": {
            "n_districts": config.n_districts,
        },
        "sampler": {
            "method":         config.sampler,
            "n_steps":        config.n_steps,
            "n_steps_warmup": config.n_steps_warmup,
            "seed":           config.seed,
        },
        "connectivity": {
            "contiguity":          config.contiguity,
            "island_policy":       config.island_policy,
            "island_threshold_km": config.island_threshold_km,
            "crs_metric":          config.crs_metric,
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)

    print(f"Escenario guardado: {path}")
