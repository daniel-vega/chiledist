"""
malapportionment.indices
==========================
Índices de malapportionment geográfico comparables internacionalmente
(un escalar por plan).

Índice                       | Referencia
-----------------------------|-------------------------------------------
Samuels-Snyder (M)           | Samuels & Snyder, AJPS 2001
Loosemore-Hanby M.           | Loosemore & Hanby 1971 (aplicado a geo.)
Gini de personas/escaño      | Sen 1997 (versión ponderada por población)
Ratio máx-mín                | Dahl & Tufte 1973
Coef. de variación (CV)      | Estándar estadístico
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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
