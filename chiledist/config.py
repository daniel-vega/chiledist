"""
config.py
=========
ScenarioConfig: objeto de configuración para escenarios de redistritaje.
Distingue entre modo legal (CUT indivisible), experimental (APC libre)
e híbrido (APC con penalización por comunas partidas).

Modos:
    legal         → decision_unit='CUT', preserve_mode='hard'
    apc_free      → decision_unit='ID_DIST', preserve_mode='none'
    apc_soft      → decision_unit='ID_DIST', preserve_mode='soft'
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
        "Modo legal vigente: comunas indivisibles (Ley 18.700). "
        "Unidad de decisión = CUT. Grafo operativo a nivel comunal."
    ),
    observation_unit="ID_DIST",
    decision_unit="CUT",
    preserve_units=["CUT"],
    preserve_mode="hard",
)

SCENARIO_APC_FREE = ScenarioConfig(
    name="experimental_apc_libre",
    description=(
        "Modo experimental contrafactual: APC como unidad mínima, "
        "comunas divisibles. No corresponde a ninguna norma vigente."
    ),
    observation_unit="ID_DIST",
    decision_unit="ID_DIST",
    preserve_units=[],
    preserve_mode="none",
)

SCENARIO_APC_SOFT = ScenarioConfig(
    name="experimental_apc_soft_cut",
    description=(
        "Modo híbrido: APC como unidad mínima. Partir comunas está "
        "permitido pero penalizado en el score del plan."
    ),
    observation_unit="ID_DIST",
    decision_unit="ID_DIST",
    preserve_units=["CUT"],
    preserve_mode="soft",
    split_penalty=0.25,
)

SCENARIOS: dict[str, ScenarioConfig] = {
    "legal":    SCENARIO_LEGAL,
    "apc_free": SCENARIO_APC_FREE,
    "apc_soft": SCENARIO_APC_SOFT,
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
        "name", "description", "observation_unit", "decision_unit",
        "preserve_units", "preserve_mode", "split_penalty",
        "min_fragment_pop_share", "pop_col", "pop_tolerance",
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
