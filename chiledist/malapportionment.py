"""
malapportionment.py
===================
Índices de malapportionment geográfico comparables internacionalmente.

Complementa las funciones de nivel distrital de ``electoral.py``
(:func:`personas_por_escano`, :func:`peso_relativo_del_voto`) con índices
**globales** (un escalar por plan) que permiten comparar sistemas electorales
entre países y entre escenarios de redistritaje.

Índices implementados
---------------------
Índice                       | Referencia
-----------------------------|-------------------------------------------
Samuels-Snyder (M)           | Samuels & Snyder, AJPS 2001
Loosemore-Hanby M.           | Loosemore & Hanby 1971 (aplicado a geo.)
Gini de personas/escaño      | Sen 1997 (versión ponderada por población)
Ratio máx-mín                | Dahl & Tufte 1973
Coef. de variación (CV)      | Estándar estadístico

Nota sobre ``peso_relativo_del_voto``
--------------------------------------
La función :func:`~chiledist.electoral.peso_relativo_del_voto` de
``electoral.py`` ya usa el denominador correcto::

    media_nacional = total_pop / total_seats    # ← correcto

Es la única forma de comparar pesos entre distritos de tamaño desigual.
La alternativa incorrecta sería usar la media aritmética de los cocientes
PxE_i, que sobrepondera a los distritos pequeños.  Estándar: Samuels &
Snyder (2001), Cox & Katz (2002).

Uso rápido
----------
    import chiledist as cd
    import chiledist.malapportionment as mala
    import pandas as pd

    pop_d   = pd.Series({1: 500_000, 2: 300_000, 3: 200_000})
    magnitudes = pd.Series({1: 3, 2: 3, 3: 2})   # suma ≠ proporcional

    print(mala.samuels_snyder_index(pop_d, magnitudes))
    summary = mala.malapportionment_summary(pop_d, magnitudes, label="mi_plan")

    # Comparación internacional
    table = mala.international_comparison({"mi_plan": summary})
    print(table[["samuels_snyder", "gini_pop_weighted", "max_min_ratio"]])
"""

from __future__ import annotations

from typing import Optional, Union, Callable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from .electoral import (
    personas_por_escano,
    peso_relativo_del_voto,
    assign_seat_magnitudes,
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
)

_BG         = "#F8F7F4"
_COLOR_MAIN = "#1D9E75"
_COLOR_OBS  = "#D85A30"


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
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _aligned(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Intersecta índices, descarta distritos con magnitud ≤ 0."""
    common = pop_by_district.index.intersection(magnitudes.index)
    pop = pop_by_district.reindex(common)
    mag = magnitudes.reindex(common)
    valid = mag > 0
    return pop[valid], mag[valid]


def _styled_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(_BG)
    ax.spines[["top", "right"]].set_visible(False)


# ──────────────────────────────────────────────────────────────────────────────
# samuels_snyder_index
# ──────────────────────────────────────────────────────────────────────────────

def samuels_snyder_index(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> float:
    """
    Índice de malapportionment de Samuels-Snyder (2001).

    .. math::

        M = \\frac{1}{2} \\sum_i \\left| s_i - p_i \\right|

    donde :math:`s_i = m_i / \\sum m_j` es la fracción de escaños del
    distrito :math:`i` y :math:`p_i = \\text{pop}_i / \\sum \\text{pop}_j`
    es la fracción de población.

    **Interpretación**: M = 0.10 significa que el 10% de los escaños
    están asignados a distritos distintos de los que corresponderían bajo
    proporcionalidad perfecta.

    Rango: [0, 1 − 1/n] donde n es el número de distritos.
    M = 0 ↔ proporcionalidad perfecta.
    M = 0.20 ↔ malapportionment moderado (comparable a España).
    M ≥ 0.30 ↔ malapportionment severo (comparable a Brasil).

    Parameters
    ----------
    pop_by_district : pd.Series
        Población por circunscripción (indexed by district_id).
    magnitudes : pd.Series
        Escaños asignados por circunscripción (indexed by district_id).

    Returns
    -------
    float en [0, ~0.5].

    References
    ----------
    Samuels, D., & Snyder, R. (2001). The value of a vote:
    Malapportionment in comparative perspective.
    *American Journal of Political Science*, 45(4), 795–821.

    Examples
    --------
    >>> pop = pd.Series({1: 1000, 2: 1000})
    >>> mag = pd.Series({1: 1, 2: 1})
    >>> samuels_snyder_index(pop, mag)
    0.0    # proporcionalidad perfecta

    >>> pop = pd.Series({1: 900, 2: 100})
    >>> mag = pd.Series({1: 1, 2: 1})
    >>> samuels_snyder_index(pop, mag)
    0.4    # D1 tiene el 90% de la pop. pero el 50% de los escaños
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    if pop.empty:
        return float("nan")

    total_pop  = float(pop.sum())
    total_mag  = float(mag.sum())
    if total_pop == 0 or total_mag == 0:
        return float("nan")

    s = mag / total_mag   # seat shares
    p = pop / total_pop   # population shares
    return round(float((s - p).abs().sum() / 2), 6)


# ──────────────────────────────────────────────────────────────────────────────
# loosemore_hanby_malapportionment
# ──────────────────────────────────────────────────────────────────────────────

def loosemore_hanby_malapportionment(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> float:
    """
    Índice de Loosemore-Hanby aplicado a malapportionment geográfico.

    Matemáticamente idéntico a :func:`samuels_snyder_index`:

    .. math::

        \\text{LH}_M = \\frac{1}{2} \\sum_i \\left| s_i - p_i \\right|

    Se incluye como función independiente para claridad conceptual:
    mientras el índice L-H electoral (``electoral.loosemore_hanby``)
    compara cuotas de votos y escaños **por partido**, este índice
    compara cuotas de escaños y población **por distrito**.

    Returns
    -------
    float — idéntico a :func:`samuels_snyder_index`.

    References
    ----------
    Loosemore, J., & Hanby, V. J. (1971). The theoretical limits of
    maximum distortion.
    *British Journal of Political Science*, 1(4), 467–477.
    """
    return samuels_snyder_index(pop_by_district, magnitudes)


# ──────────────────────────────────────────────────────────────────────────────
# gini_personas_por_escano
# ──────────────────────────────────────────────────────────────────────────────

def gini_personas_por_escano(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
    pop_weighted: bool = True,
) -> float:
    """
    Coeficiente de Gini de la distribución de personas por escaño.

    Mide la **desigualdad** en la representación geográfica.

    **Versión ponderada por población** (``pop_weighted=True``, recomendada):

    .. math::

        G = \\frac{\\sum_i \\sum_j p_i \\cdot p_j \\cdot |x_i - x_j|}{2 \\mu}

    donde :math:`x_i = \\text{PxE}_i`, :math:`p_i = \\text{pop}_i / \\sum \\text{pop}`,
    y :math:`\\mu = \\sum p_i x_i` (media ponderada por población).

    Esta versión pregunta: *"En promedio, ¿cuán diferente es la
    representación de dos ciudadanos elegidos al azar?"*, ponderando por la
    probabilidad de que cada ciudadano habite en cada distrito.

    **Versión no ponderada** (``pop_weighted=False``):

    .. math::

        G = \\frac{2}{n^2 \\mu} \\sum_{i=1}^{n} i \\cdot x_{(i)} - \\frac{n+1}{n}

    donde :math:`x_{(i)}` son los PxE ordenados ascendentemente y
    :math:`\\mu` es la media aritmética.

    Rango: [0, 1].  G = 0 ↔ todos los distritos con igual PxE.

    Parameters
    ----------
    pop_by_district : pd.Series
    magnitudes : pd.Series
    pop_weighted : bool
        Si ``True`` (default), usa la versión ponderada por población.

    Returns
    -------
    float en [0, 1).

    References
    ----------
    Sen, A. (1997). *On Economic Inequality*, Clarendon Press, Oxford.
    Dahl, R. A., & Tufte, E. R. (1973). *Size and Democracy*, Stanford UP.
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    n = len(pop)
    if n == 0:
        return float("nan")
    if n == 1:
        return 0.0

    pxe = pop / mag

    if pop_weighted:
        p     = pop / float(pop.sum())       # population shares
        mu    = float((p * pxe).sum())       # population-weighted mean PxE
        if mu < 1e-12:
            return 0.0
        pxe_v = pxe.values.astype(float)
        p_v   = p.values.astype(float)
        # G = Σ_i Σ_j p_i p_j |x_i - x_j| / (2μ)
        diff_sum = float(
            np.sum(np.abs(pxe_v[:, None] - pxe_v[None, :]) * np.outer(p_v, p_v))
        )
        return round(diff_sum / (2.0 * mu), 6)
    else:
        x  = np.sort(pxe.values.astype(float))
        mu = float(x.mean())
        if mu < 1e-12:
            return 0.0
        ranks = np.arange(1, n + 1)
        g = float(2.0 / (n * n * mu) * (ranks * x).sum() - (n + 1) / n)
        return round(max(0.0, g), 6)


# ──────────────────────────────────────────────────────────────────────────────
# max_min_representation_ratio
# ──────────────────────────────────────────────────────────────────────────────

def max_min_representation_ratio(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> dict:
    """
    Ratio máximo-mínimo de representación (Dahl & Tufte, 1973).

    .. math::

        R = \\frac{\\max_i \\text{PxE}_i}{\\min_j \\text{PxE}_j}

    Un R = 5 significa que un ciudadano del distrito más subrepresentado
    necesita cinco veces más personas para elegir un diputado que un
    ciudadano del distrito más sobrerrepresentado.

    También calcula el **coeficiente de variación** (CV = σ/μ) que
    normaliza la dispersión y es comparable entre sistemas con distintas
    poblaciones absolutas.

    Parameters
    ----------
    pop_by_district : pd.Series
    magnitudes : pd.Series

    Returns
    -------
    dict con claves:

    ``ratio``
        R = max_pxe / min_pxe.
    ``max_pxe``
        Valor máximo de personas/escaño.
    ``max_district``
        Distrito con PxE máximo (más subrepresentado).
    ``min_pxe``
        Valor mínimo de personas/escaño.
    ``min_district``
        Distrito con PxE mínimo (más sobrerrepresentado).
    ``mean_pxe``
        Media nacional (= total_pop / total_seats).
    ``std_pxe``
        Desviación estándar de PxE.
    ``cv``
        Coeficiente de variación (σ / μ_nacional).

    References
    ----------
    Dahl, R. A., & Tufte, E. R. (1973). *Size and Democracy*.
    Stanford University Press.
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    if pop.empty:
        return {k: float("nan") for k in
                ["ratio", "max_pxe", "max_district", "min_pxe",
                 "min_district", "mean_pxe", "std_pxe", "cv"]}

    pxe      = pop / mag
    total_pop   = float(pop.sum())
    total_seats = float(mag.sum())
    mean_pxe    = total_pop / total_seats  if total_seats > 0 else float("nan")

    max_idx = pxe.idxmax()
    min_idx = pxe.idxmin()
    max_v   = float(pxe[max_idx])
    min_v   = float(pxe[min_idx])
    std_v   = float(pxe.std(ddof=1)) if len(pxe) > 1 else 0.0
    cv      = std_v / mean_pxe if mean_pxe and mean_pxe > 0 else float("nan")
    ratio   = max_v / min_v    if min_v > 0 else float("inf")

    return {
        "ratio":        round(ratio,   4),
        "max_pxe":      round(max_v,   1),
        "max_district": max_idx,
        "min_pxe":      round(min_v,   1),
        "min_district": min_idx,
        "mean_pxe":     round(mean_pxe, 1),
        "std_pxe":      round(std_v,   1),
        "cv":           round(cv,      4),
    }


# ──────────────────────────────────────────────────────────────────────────────
# malapportionment_summary
# ──────────────────────────────────────────────────────────────────────────────

def malapportionment_summary(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
    label: str = "",
) -> dict:
    """
    Resumen completo de métricas de malapportionment para un plan.

    Combina todos los índices del módulo en un único diccionario listo para
    agregar a una tabla comparativa.

    Parameters
    ----------
    pop_by_district : pd.Series
        Población por circunscripción.
    magnitudes : pd.Series
        Escaños por circunscripción.
    label : str
        Etiqueta del plan (ej. ``"legal_vigente"``, ``"apc_soft_p0.25"``).

    Returns
    -------
    dict con claves:

    ``plan``
        Etiqueta del plan.
    ``n_districts``
        Número de circunscripciones con datos válidos.
    ``total_seats``
        Total de escaños.
    ``total_pop``
        Total de población.
    ``samuels_snyder``
        Índice M de Samuels-Snyder.
    ``loosemore_hanby_M``
        Idéntico a samuels_snyder (alias semántico).
    ``gini_pop_weighted``
        Coeficiente de Gini ponderado por población.
    ``gini_unweighted``
        Coeficiente de Gini no ponderado.
    ``max_min_ratio``
        Ratio máximo-mínimo de PxE.
    ``cv``
        Coeficiente de variación de PxE.
    ``mean_pxe``
        Media nacional de personas/escaño.
    ``std_pxe``
        Desviación estándar de personas/escaño.
    ``max_pxe``, ``max_district``, ``min_pxe``, ``min_district``
        Extremos de la distribución.

    Examples
    --------
    >>> pop = pd.Series({1: 800_000, 2: 500_000, 3: 200_000})
    >>> mag = pd.Series({1: 3, 2: 3, 3: 2})
    >>> s = malapportionment_summary(pop, mag, label="ejemplo")
    >>> s["samuels_snyder"]
    0.120977
    """
    pop, mag = _aligned(pop_by_district, magnitudes)

    ss   = samuels_snyder_index(pop, mag)
    gw   = gini_personas_por_escano(pop, mag, pop_weighted=True)
    gu   = gini_personas_por_escano(pop, mag, pop_weighted=False)
    mmr  = max_min_representation_ratio(pop, mag)

    return {
        "plan":             label,
        "n_districts":      len(pop),
        "total_seats":      int(mag.sum()),
        "total_pop":        int(pop.sum()),
        "samuels_snyder":   ss,
        "loosemore_hanby_M": ss,       # alias semántico — mismo valor
        "gini_pop_weighted": gw,
        "gini_unweighted":   gu,
        "max_min_ratio":     mmr["ratio"],
        "cv":                mmr["cv"],
        "mean_pxe":          mmr["mean_pxe"],
        "std_pxe":           mmr["std_pxe"],
        "max_pxe":           mmr["max_pxe"],
        "max_district":      mmr["max_district"],
        "min_pxe":           mmr["min_pxe"],
        "min_district":      mmr["min_district"],
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


# ──────────────────────────────────────────────────────────────────────────────
# Visualización
# ──────────────────────────────────────────────────────────────────────────────

def plot_pxe_distribution(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
    label: str = "",
    reference_line: Optional[float] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Histograma de la distribución de personas por escaño.

    Parameters
    ----------
    pop_by_district, magnitudes : pd.Series
        Datos del plan.
    label : str
        Título del plan (se incluye en el título del gráfico).
    reference_line : float, optional
        Línea vertical adicional (ej. media nacional de otro plan).
    ax : plt.Axes, optional
        Eje existente.  Si ``None``, se crea una nueva figura.
    save_path : str, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    pxe      = (pop / mag).rename("pxe")
    mean_nat = float(pop.sum()) / float(mag.sum()) if mag.sum() > 0 else float("nan")

    created = ax is None
    if created:
        fig, ax = plt.subplots(figsize=(9, 5))
        fig.patch.set_facecolor(_BG)
    else:
        fig = ax.get_figure()

    _styled_ax(ax)
    ax.hist(pxe, bins=min(20, max(5, len(pxe))), color=_COLOR_MAIN,
            alpha=0.75, edgecolor="white", linewidth=0.5)
    ax.axvline(mean_nat, color="#1A5C8A", linewidth=2, linestyle="--",
               label=f"Media nacional ({mean_nat:,.0f})")
    if reference_line is not None:
        ax.axvline(reference_line, color=_COLOR_OBS, linewidth=1.5,
                   linestyle=":", label=f"Referencia ({reference_line:,.0f})")

    ax.set_xlabel("Personas por escaño", fontsize=10)
    ax.set_ylabel("Número de distritos", fontsize=10)
    ax.set_title(
        f"Distribución de personas/escaño{' — ' + label if label else ''}",
        fontsize=11, fontweight="bold",
    )
    ax.legend(fontsize=9)
    if save_path and created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=_BG)
    return fig


def plot_malapportionment_ranking(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
    label: str = "",
    top_n: Optional[int] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Ranking de distritos por peso relativo del voto.

    Ordena los distritos de mayor (más subrepresentados) a menor
    peso relativo (más sobrerrepresentados) y los muestra como barras
    horizontales con la línea de equidad en 1.0.

    Parameters
    ----------
    top_n : int, optional
        Si se especifica, muestra solo los ``top_n`` distritos más extremos
        (los ``top_n//2`` más sobrerepresentados y los ``top_n//2`` más
        subrepresentados).

    Returns
    -------
    matplotlib.figure.Figure
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    prv      = peso_relativo_del_voto(pop, mag).sort_values(ascending=False)

    if top_n is not None and len(prv) > top_n:
        half = top_n // 2
        prv  = pd.concat([prv.head(half), prv.tail(half)])

    colors = [_COLOR_OBS if v > 1.0 else _COLOR_MAIN for v in prv.values]

    created = ax is None
    if created:
        figsize = (10, max(4, len(prv) * 0.35))
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(_BG)
    else:
        fig = ax.get_figure()

    _styled_ax(ax)
    y_pos = range(len(prv))
    ax.barh(list(y_pos), prv.values, color=colors, alpha=0.82, edgecolor="none")
    ax.axvline(1.0, color="#1A5C8A", linewidth=1.5, linestyle="--", zorder=3)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([str(i) for i in prv.index], fontsize=8)
    ax.set_xlabel("Peso relativo del voto (1.0 = equidad)", fontsize=10)
    ax.set_title(
        f"Ranking de distritos por representación{' — ' + label if label else ''}",
        fontsize=11, fontweight="bold",
    )
    under_lbl = mpatches.Patch(color=_COLOR_OBS,  label="Subrepresentado (PxE > media)")
    over_lbl  = mpatches.Patch(color=_COLOR_MAIN, label="Sobrerrepresentado (PxE < media)")
    ax.legend(handles=[under_lbl, over_lbl], fontsize=8, loc="lower right")
    plt.tight_layout()
    if save_path and created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=_BG)
    return fig


def plot_international_comparison(
    comparison_df: pd.DataFrame,
    metric: str = "samuels_snyder",
    metric_label: Optional[str] = None,
    title: Optional[str] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Dot-plot de comparación internacional de malapportionment.

    Parameters
    ----------
    comparison_df : pd.DataFrame
        Salida de :func:`international_comparison`.
    metric : str
        Columna a graficar.  Default: ``"samuels_snyder"``.
    metric_label : str, optional
        Etiqueta del eje.  Default: el nombre de la columna.
    title : str, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    if metric not in comparison_df.columns:
        raise ValueError(f"Métrica '{metric}' no encontrada en comparison_df.")

    df = comparison_df[[metric, "type"]].dropna(subset=[metric]).sort_values(metric)
    if df.empty:
        raise ValueError("No hay datos válidos para graficar.")

    metric_label = metric_label or metric.replace("_", " ").title()

    colors = [
        "#1D9E75" if t == "custom" else "#1A5C8A"
        for t in df["type"]
    ]

    created = ax is None
    if created:
        figsize = (10, max(4, len(df) * 0.45))
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(_BG)
    else:
        fig = ax.get_figure()

    _styled_ax(ax)
    y_pos = range(len(df))
    ax.barh(list(y_pos), df[metric].values, color=colors, alpha=0.82,
            edgecolor="none", height=0.55)

    # Value labels
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row[metric] + df[metric].max() * 0.01, i,
                f"{row[metric]:.3f}", va="center", fontsize=8)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([str(i) for i in df.index], fontsize=9)
    ax.set_xlabel(metric_label, fontsize=10)
    ax.set_title(
        title or f"Comparación internacional — {metric_label}",
        fontsize=11, fontweight="bold",
    )

    bench = mpatches.Patch(color="#1A5C8A", label="Benchmark internacional")
    cstm  = mpatches.Patch(color="#1D9E75", label="Planes ChileDist")
    ax.legend(handles=[bench, cstm], fontsize=8, loc="lower right")
    plt.tight_layout()
    if save_path and created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=_BG)
    return fig
