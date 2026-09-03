"""
domain.scenario
=================
ScenarioConfig: objeto de configuración para escenarios de redistritaje.

Modelo de datos puro (capa 0 — domain): campos, validación estructural
interna, representación textual e I/O genérico (YAML). No contiene los
presets legales concretos (ver ``rules.scenario_rules``) ni el texto de
encuadre legislativo (ver ``evaluation.framing``).
"""

from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Jerarquía de unidades geográficas (más fino → más grueso)
# ──────────────────────────────────────────────────────────────────────────────

# Usada únicamente para advertir cuando decision_unit es más fino que una
# columna con preserve_mode="hard" (ver ScenarioConfig.validate()) — el caso
# que ya causó warm-up infinito con apc_strict (decision_unit="ID_DIST",
# preserve_units=["CUT"], hard; ver SCIENTIFIC_HYPOTHESES.md § "Estado de
# apc_strict"). Un nivel ausente de este dict simplemente no se compara (no
# se asume ninguna relación de fineza para columnas no reconocidas, ej.
# columnas ad-hoc de un YAML personalizado).
_UNIT_HIERARCHY: dict[str, int] = {
    "MANZENT":       0,  # manzana — unidad más fina
    "ID_DIST":       1,  # distrito censal APC
    "CUT":           2,  # comuna
    "COD_PROVINCIA": 3,  # provincia
    "COD_REGION":    4,  # región — unidad más gruesa
}


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
    >>> from chiledist.rules.scenario_rules import SCENARIO_LEGAL, SCENARIO_APC_FREE
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
    # "contrafactual_regional" → reforma con preservación a nivel regional
    #                            (COD_REGION), además o en vez de comunal
    tipo_reforma: str = "vigente"

    # Unidades geográficas
    observation_unit: str = "ID_DIST"   # unidad de los datos de entrada
    decision_unit: str = "CUT"          # unidad mínima que ReCom puede mover

    # Preservación de límites administrativos.
    #
    # preserve_mode / split_penalty aceptan dos formas:
    #   - str/float único → se aplica uniformemente a todas las columnas
    #     de preserve_units (comportamiento histórico, sigue funcionando
    #     tal cual para escenarios existentes).
    #   - dict {columna: modo/peso} → modo/peso distinto por columna, para
    #     preservación jerárquica multinivel (ej. {"CUT": "hard",
    #     "COD_REGION": "soft"}). Debe declarar TODAS las columnas de
    #     preserve_units explícitamente — ver validate().
    #
    # No leer preserve_mode/split_penalty directamente en código nuevo:
    # usar resolved_preserve_mode()/resolved_split_penalty(), que
    # normalizan ambas formas a dict — único punto de normalización.
    preserve_units: list[str] = field(default_factory=list)
    preserve_mode: str | dict[str, str] = "hard"         # "hard" | "soft" | "none", o dict por columna
    split_penalty: float | dict[str, float] = 0.0        # peso de la penalización en modo soft, o dict por columna
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

    # Balance poblacional: None = ideal uniforme (total_pop/n_districts,
    # comportamiento actual). dict {distrito: magnitud} = ideal ponderado
    # por magnitud (ver chiledist.weighted_population_balance) — para
    # sistemas multimember con magnitud variable (ej. Chile, M∈[3,8]).
    magnitudes: Optional[dict] = None

    # Conectividad e islas
    contiguity: str = "queen"
    island_policy: str = "nearest"
    island_threshold_km: float = 50.0   # solo relevante con island_policy="threshold"

    # CRS métrico (None = auto-detectar desde los datos)
    crs_metric: Optional[str] = None

    def resolved_preserve_mode(self) -> dict[str, str]:
        """
        Normaliza preserve_mode a dict {columna: modo}.

        Único punto de normalización: si preserve_mode ya es un dict, se
        devuelve tal cual (una copia); si es un único str, se expande a
        {col: preserve_mode for col in preserve_units} — el comportamiento
        uniforme histórico. Todo código que necesite saber el modo de una
        columna específica (rules.constraints, engines.samplers.{accept,
        updaters}, scripts/redistritaje.py) debe llamar este método en vez
        de leer self.preserve_mode directamente, para soportar modo
        distinto por nivel sin duplicar la lógica de normalización en cada
        punto de consumo.

        Returns
        -------
        dict[str, str]
        """
        if isinstance(self.preserve_mode, dict):
            return dict(self.preserve_mode)
        return {col: self.preserve_mode for col in self.preserve_units}

    def resolved_split_penalty(self) -> dict[str, float]:
        """
        Normaliza split_penalty a dict {columna: peso}, misma lógica que
        resolved_preserve_mode(): un dict explícito se devuelve tal cual;
        un único float se aplica a todas las columnas de preserve_units
        cuyo modo resuelto (ver resolved_preserve_mode()) sea "soft" — las
        columnas "hard"/"none" no tienen penalización, no tendría efecto.

        Returns
        -------
        dict[str, float]
        """
        if isinstance(self.split_penalty, dict):
            return dict(self.split_penalty)
        modes = self.resolved_preserve_mode()
        return {
            col: self.split_penalty
            for col in self.preserve_units
            if modes.get(col) == "soft"
        }

    def validate(self) -> None:
        """Verifica la coherencia interna de la configuración."""
        valid_units = {"CUT", "ID_DIST", "MANZENT"}
        if self.decision_unit not in valid_units:
            raise ValueError(
                f"decision_unit '{self.decision_unit}' no reconocida. "
                f"Opciones: {sorted(valid_units)}"
            )

        valid_tipos = {"vigente", "contrafactual_fuerte",
                       "contrafactual_intermedio", "control_metodologico",
                       "contrafactual_regional"}
        if self.tipo_reforma not in valid_tipos:
            raise ValueError(
                f"tipo_reforma '{self.tipo_reforma}' no reconocido. "
                f"Opciones: {sorted(valid_tipos)}"
            )

        valid_modes = {"hard", "soft", "none"}

        if isinstance(self.preserve_mode, dict):
            mode_keys = set(self.preserve_mode.keys())
            units_set = set(self.preserve_units)

            extra = mode_keys - units_set
            if extra:
                raise ValueError(
                    f"preserve_mode (dict) declara modo para columnas que "
                    f"no están en preserve_units: {sorted(extra)}."
                )

            missing = units_set - mode_keys
            if missing:
                raise ValueError(
                    f"preserve_mode (dict) debe declarar modo explícito "
                    f"para cada columna de preserve_units; faltan: "
                    f"{sorted(missing)}. No se asume un default silencioso "
                    f"— agrega la columna a preserve_mode o quítala de "
                    f"preserve_units."
                )

            invalid = {m for m in self.preserve_mode.values() if m not in valid_modes}
            if invalid:
                raise ValueError(
                    f"preserve_mode (dict) contiene modos no reconocidos: "
                    f"{sorted(invalid)}. Opciones: {sorted(valid_modes)}"
                )
        else:
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

        resolved_modes = self.resolved_preserve_mode()
        hard_cols = [c for c, m in resolved_modes.items() if m == "hard"]
        soft_cols = [c for c, m in resolved_modes.items() if m == "soft"]

        # decision_unit más fino que una columna hard-preservada: mismo
        # mecanismo de falla documentado para apc_strict (decision_unit=
        # "ID_DIST" más fino que preserve_units=["CUT"] hard) — ReCom
        # propone cortes de árbol de expansión sin sesgo hacia la frontera
        # preservada, así que casi toda propuesta se rechaza y la cadena
        # puede quedar atrapada indefinidamente en el warm-up. No aplica
        # cuando decision_unit == columna (caso trivial, ej. legal_comunas:
        # decision_unit="CUT", preserve_units=["CUT"] — no hay nada que
        # partir por construcción).
        dec_rank = _UNIT_HIERARCHY.get(self.decision_unit)
        if dec_rank is not None:
            for col in hard_cols:
                col_rank = _UNIT_HIERARCHY.get(col)
                if col_rank is not None and dec_rank < col_rank:
                    warnings.warn(
                        f"decision_unit='{self.decision_unit}' es más fino "
                        f"que '{col}' (preserve_mode='hard' para '{col}'). "
                        f"Este es el mismo patrón que causó warm-up "
                        f"infinito con apc_strict (decision_unit='ID_DIST', "
                        f"preserve_units=['CUT'], hard) — ver "
                        f"SCIENTIFIC_HYPOTHESES.md § 'Estado de apc_strict "
                        f"(control metodológico)'. ReCom no tiene sesgo "
                        f"hacia la frontera preservada; probar con un "
                        f"presupuesto de pasos acotado antes de comprometer "
                        f"cómputo de producción.",
                        UserWarning,
                        stacklevel=2,
                    )

        if isinstance(self.split_penalty, dict):
            for col in soft_cols:
                if self.split_penalty.get(col, 0.0) == 0.0:
                    warnings.warn(
                        f"preserve_mode='soft' para '{col}' con "
                        f"split_penalty=0.0 (o no declarado) no tiene "
                        f"efecto. Considera preserve_mode='none' para "
                        f"'{col}' o un split_penalty > 0.",
                        stacklevel=2,
                    )
        elif soft_cols and self.split_penalty == 0.0:
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

        if self.magnitudes is not None and not isinstance(self.magnitudes, dict):
            raise ValueError(
                "magnitudes debe ser dict {distrito: escaños} o None "
                "(balance uniforme)."
            )

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
        if isinstance(self.preserve_mode, str):
            # Comportamiento histórico sin cambios para escenarios existentes.
            if self.preserve_mode == "soft":
                lines.append(f"  Split penalty  : {self.split_penalty}")
        else:
            soft_penalties = {
                c: p for c, p in self.resolved_split_penalty().items()
            }
            if soft_penalties:
                lines.append(f"  Split penalty  : {soft_penalties}")
        island_str = self.island_policy
        if self.island_policy == "threshold":
            island_str += f" ({self.island_threshold_km} km)"
        crs_str = self.crs_metric or "auto"
        lines += [
            f"  Pop col        : {self.pop_col}",
            f"  Pop tolerancia : ±{self.pop_tolerance*100:.0f}%",
            f"  Balance        : {'ponderado por magnitud' if self.magnitudes else 'uniforme'}",
            f"  Sampler        : {self.sampler}",
            f"  Steps          : {self.n_steps:,}",
            f"  Seed           : {self.seed}",
            f"  Islas          : {island_str}",
            f"  CRS métrico    : {crs_str}",
        ]
        return "\n".join(lines)


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
    flat.setdefault("magnitudes", districts.get("magnitudes", flat.get("magnitudes", None)))

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
        "magnitudes",
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
            "magnitudes":  config.magnitudes,
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
