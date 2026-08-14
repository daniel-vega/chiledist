"""
scenario_comparison.scoring
==============================
Configuración de puntaje compuesto (:class:`ScoringConfig`) y constantes
de estilo/métricas estándar compartidas por el resto del paquete.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Tuple

# ── Constantes de visualización ───────────────────────────────────────────────

COLORES_DEFAULT: Dict[str, str] = {
    # nombres ScenarioConfig (actuales)
    "legal":                     "#1D6A96",
    "apc_free":                  "#D85A30",
    "apc_soft":                  "#6A3D9A",
    # aliases de compatibilidad
    "legal_comunas":             "#1D6A96",
    "experimental_apc_libre":    "#D85A30",
    "experimental_apc_soft_cut": "#6A3D9A",
}

NOMBRES_CORTOS: Dict[str, str] = {
    "legal":                     "Legal (CUT)",
    "apc_free":                  "APC libre",
    "apc_soft":                  "APC soft",
    # aliases de compatibilidad
    "legal_comunas":             "Legal (CUT)",
    "experimental_apc_libre":    "APC libre",
    "experimental_apc_soft_cut": "APC soft",
}

# (columna_ensemble, etiqueta_humana, dirección_óptima)
METRICAS_STD: List[Tuple[str, str, str]] = [
    ("max_dev_pob_pct",    "Balance pob. — desv. máx (%)",  "min"),
    ("pp_promedio",        "Compacidad Polsby-Popper",        "max"),
    ("cut_edges",          "Aristas cortadas",                "min"),
    ("n_comunas_partidas", "Comunas partidas",                "min"),
    ("split_severity",     "Severidad de cortes",             "min"),
    ("pop_afectada_pct",   "Pob. en comunas partidas (%)",    "min"),
]

PESOS_DEFAULT: Dict[str, float] = {
    "max_dev_pob_pct":    0.35,
    "pp_promedio":        0.20,
    "cut_edges":          0.15,
    "n_comunas_partidas": 0.15,
    "split_severity":     0.05,
    "pop_afectada_pct":   0.10,
}


# ──────────────────────────────────────────────────────────────────────────────
# ScoringConfig — configuración de puntaje compuesto
# ──────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class ScoringConfig:
    """
    Encapsula la configuración del puntaje compuesto para rank_scenarios.

    Attributes
    ----------
    weights : dict {col: float}
        Pesos relativos por métrica (no necesitan sumar 1.0 — son relativos).
    directions : dict {col: "min"|"max"}
        Dirección óptima de cada métrica.
    normalization : str
        Estrategia de normalización al intervalo [0, 1]:
        - "minmax" : (x − min) / (max − min)   [default]
        - "zscore" : z-score escalado a [0, 1]
        - "rank"   : percentil de rango

    Examples
    --------
    >>> sc = ScoringConfig.default()
    >>> sc_custom = ScoringConfig.from_weights({"pp_promedio": 0.6,
    ...                                          "max_dev_pob_pct": 0.4})
    """
    weights:       Dict[str, float]
    directions:    Dict[str, str]
    normalization: str = "minmax"

    def __post_init__(self):
        valid_dirs   = {"min", "max"}
        valid_norms  = {"minmax", "zscore", "rank"}
        for col, d in self.directions.items():
            if d not in valid_dirs:
                raise ValueError(
                    f"Dirección inválida '{d}' para '{col}'. Use 'min' o 'max'."
                )
        if self.normalization not in valid_norms:
            raise ValueError(
                f"normalization debe ser 'minmax', 'zscore' o 'rank'. "
                f"Recibido: '{self.normalization}'."
            )

    @classmethod
    def default(cls) -> "ScoringConfig":
        """Configuración por defecto desde PESOS_DEFAULT y METRICAS_STD."""
        return cls(
            weights    = dict(PESOS_DEFAULT),
            directions = {col: d for col, _, d in METRICAS_STD},
        )

    @classmethod
    def from_weights(
        cls,
        weights: Dict[str, float],
        extra_directions: Optional[Dict[str, str]] = None,
        normalization: str = "minmax",
    ) -> "ScoringConfig":
        """
        Crea ScoringConfig desde un dict de pesos.

        Infiere las direcciones de METRICAS_STD para las métricas conocidas.
        Las métricas no encontradas en METRICAS_STD usan dirección "min".

        Parameters
        ----------
        weights : dict
            Pesos por columna base (ej. {"pp_promedio": 0.6}).
        extra_directions : dict, opcional
            Sobreescribe o añade direcciones para métricas no en METRICAS_STD.
        """
        directions = {col: d for col, _, d in METRICAS_STD}
        for col in weights:
            if col not in directions:
                directions[col] = "min"
        if extra_directions:
            directions.update(extra_directions)
        return cls(weights=weights, directions=directions, normalization=normalization)
