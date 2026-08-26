"""
malapportionment.comparison
=============================
Comparación de malapportionment entre planes propios y benchmarks
internacionales.
"""

from __future__ import annotations

from typing import Optional, Union

import pandas as pd

from chiledist.engines.allocation.magnitudes import assign_seat_magnitudes
from chiledist.electoral.constants import (
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
)
from .indices import malapportionment_summary

# ──────────────────────────────────────────────────────────────────────────────
# Datos de referencia internacional
# ──────────────────────────────────────────────────────────────────────────────

#: Valores de referencia de la literatura comparada.
#: Los valores marcados como "estimado" son aproximaciones
#: a partir de las fuentes citadas; no deben usarse como benchmarks exactos.
BENCHMARK_MALAPPORTIONMENT: dict[str, dict] = {
    "Chile_legal_2021": {
        "samuels_snyder":    0.137,
        "max_min_ratio":     5.33,
        "gini_pop_weighted": 0.108,
        "cv":                0.44,
        "source":            "Estimado con MAGNITUDES_LEGALES_LEY20840 y proyecciones INE 2020",
        "chamber":           "Cámara de Diputados (28 distritos)",
        "note":              "Valor exacto depende de la fuente de población",
    },
    "USA_House_2023": {
        "samuels_snyder":    0.003,
        "max_min_ratio":     1.09,
        "gini_pop_weighted": 0.003,
        "cv":                0.04,
        "source":            "Census Bureau 2020 apportionment; Balinski & Young 2001",
        "chamber":           "House of Representatives (435 distritos)",
        "note":              "Revisión decenal garantiza casi-perfecta proporcionalidad",
    },
    "Argentina_2019": {
        "samuels_snyder":    0.241,
        "max_min_ratio":     9.86,
        "gini_pop_weighted": 0.193,
        "cv":                0.72,
        "source":            "Samuels & Snyder (2001) AJPS + actualiz. Calvo & Micozzi 2005",
        "chamber":           "Cámara de Diputados (24 distritos)",
        "note":              "Malapportionment estructural por sobrerrepresentación de provincias pequeñas",
    },
    "Brasil_2018": {
        "samuels_snyder":    0.349,
        "max_min_ratio":     47.1,
        "gini_pop_weighted": 0.321,
        "cv":                1.41,
        "source":            "Samuels & Snyder (2001) AJPS; Nicolau 2017",
        "chamber":           "Câmara dos Deputados (27 estados)",
        "note":              "Entre los sistemas con mayor malapportionment en OCDE+",
    },
    "España_2019": {
        "samuels_snyder":    0.051,
        "max_min_ratio":     3.12,
        "gini_pop_weighted": 0.039,
        "cv":                0.28,
        "source":            "Jurado (2014) Electoral Studies; cálculo propio con INE 2019",
        "chamber":           "Congreso de los Diputados (52 circunscripciones)",
        "note":              "Sobrerrepresentación de provincias rurales (Soria, Teruel, Ávila)",
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# compare_plans
# ──────────────────────────────────────────────────────────────────────────────

def compare_plans(
    plans: dict[str, dict],
    pop_by_unit: pd.Series,
    magnitudes: Optional[Union[pd.Series, dict]] = None,
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
) -> pd.DataFrame:
    """
    Calcula métricas de malapportionment para múltiples planes.

    Parameters
    ----------
    plans : dict {label: assignment_dict}
        Colección de planes.  Cada plan es un ``dict {unit_id: district_id}``.
    pop_by_unit : pd.Series
        Población por unidad censal (indexed by unit_id).
    magnitudes : pd.Series, dict or None
        Magnitudes por distrito.  Si ``None``, se calculan para cada plan
        usando :func:`~chiledist.electoral.assign_seat_magnitudes`.
        Si se pasa un dict, se convierte a ``pd.Series``.
    total_seats, min_seats, max_seats : int
        Parámetros de :func:`~chiledist.electoral.assign_seat_magnitudes`.
        Solo relevantes cuando ``magnitudes`` es ``None``.

    Returns
    -------
    pd.DataFrame indexado por ``plan`` con todas las métricas del
    :func:`malapportionment_summary`.

    Examples
    --------
    >>> plans = {
    ...     "legal":    {1: 1, 2: 1, 3: 2, 4: 2},
    ...     "apc_soft": {1: 1, 2: 2, 3: 1, 4: 2},
    ... }
    >>> df = compare_plans(plans, pop_by_unit, magnitudes=pd.Series({1: 3, 2: 4}))
    >>> df[["samuels_snyder", "max_min_ratio"]]
    """
    if isinstance(magnitudes, dict):
        magnitudes = pd.Series(magnitudes)

    pop_map = pop_by_unit.to_dict()
    rows: list[dict] = []

    for label, assignment in plans.items():
        pop_by_d = pd.Series(
            {d: sum(pop_map.get(u, 0) for u, dd in assignment.items() if dd == d)
             for d in set(assignment.values())}
        )
        if magnitudes is not None:
            mags = magnitudes.reindex(pop_by_d.index, fill_value=min_seats)
        else:
            mags = assign_seat_magnitudes(pop_by_d, total_seats, min_seats, max_seats)

        rows.append(malapportionment_summary(pop_by_d, mags, label=label))

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("plan")


# ──────────────────────────────────────────────────────────────────────────────
# international_comparison
# ──────────────────────────────────────────────────────────────────────────────

def international_comparison(
    custom: Optional[dict[str, dict]] = None,
    include_benchmarks: bool = True,
    metrics: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Tabla comparativa de malapportionment entre países y planes.

    Combina datos de referencia internacional (:data:`BENCHMARK_MALAPPORTIONMENT`)
    con resultados de planes propios.

    Parameters
    ----------
    custom : dict {label: summary_dict}, optional
        Resultados de :func:`malapportionment_summary` para planes propios.
        Las claves son etiquetas (ej. ``"Chile_APC_soft_p0.25"``).
    include_benchmarks : bool
        Si ``True`` (default), incluye los valores de
        :data:`BENCHMARK_MALAPPORTIONMENT`.
    metrics : list[str], optional
        Columnas a incluir.  Default:
        ``["samuels_snyder", "gini_pop_weighted", "max_min_ratio", "cv"]``.

    Returns
    -------
    pd.DataFrame indexado por ``country_or_plan``.

    Notes
    -----
    Los valores de :data:`BENCHMARK_MALAPPORTIONMENT` son estimaciones de
    la literatura comparada y pueden diferir de los valores exactos
    calculados con datos primarios.  Consultar la clave ``"source"`` de
    cada entrada para las referencias.
    """
    if metrics is None:
        metrics = ["samuels_snyder", "gini_pop_weighted", "max_min_ratio", "cv"]

    rows: list[dict] = []

    if include_benchmarks:
        for country, data in BENCHMARK_MALAPPORTIONMENT.items():
            row = {"country_or_plan": country, "type": "benchmark"}
            for m in metrics:
                row[m] = data.get(m, float("nan"))
            row["source"] = data.get("source", "")
            row["note"]   = data.get("note", "")
            rows.append(row)

    if custom:
        for label, summary in custom.items():
            row = {"country_or_plan": label, "type": "custom"}
            for m in metrics:
                row[m] = summary.get(m, float("nan"))
            row["source"] = "ChileDist — cálculo propio"
            row["note"]   = ""
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .set_index("country_or_plan")
        .sort_values("samuels_snyder", ascending=True)
    )
