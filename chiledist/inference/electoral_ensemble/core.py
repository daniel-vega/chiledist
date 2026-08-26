"""
electoral_ensemble.core
========================
Análisis distribucional de métricas electorales sobre ensembles de planes.

Flujo:
    Ensemble de planes → D'Hondt binivel → Métricas electorales → Distribuciones
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd

from chiledist.engines.allocation.magnitudes import assign_seat_magnitudes
from chiledist.engines.allocation.dhondt import (
    aggregate_votes,
    run_electoral_plan_binivel,
    run_electoral_plan,
    national_shares,
)
from chiledist.evaluation.proportionality import (
    gallagher_index,
    loosemore_hanby,
    rae_index,
    effective_number_of_parties,
    seat_bonus,
)
from chiledist.evaluation.district_malapportionment import umbral_efectivo
from chiledist.electoral.constants import (
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
)

# Métricas escalares incluidas siempre en el resumen
_SCALAR_METRICS = [
    "gallagher",
    "loosemore_hanby",
    "rae",
    "enp_votos",
    "enp_escanos",
    "n_partidos_con_escanos",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _dist_stats(series: pd.Series) -> dict:
    """Media, mediana, std, percentiles y IC 95% (aproximación normal) de una serie."""
    arr = series.dropna().values
    n = len(arr)
    nan_dict = {k: float("nan") for k in
                ["mean", "median", "std", "p5", "p25", "p75", "p95", "ci95_low", "ci95_high"]}
    if n == 0:
        return {**nan_dict, "n": 0}
    mean_ = float(np.mean(arr))
    std_  = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    sem_  = std_ / float(np.sqrt(n)) if n > 0 else 0.0
    return {
        "mean":      round(mean_, 6),
        "median":    round(float(np.median(arr)), 6),
        "std":       round(std_, 6),
        "p5":        round(float(np.percentile(arr, 5)),  6),
        "p25":       round(float(np.percentile(arr, 25)), 6),
        "p75":       round(float(np.percentile(arr, 75)), 6),
        "p95":       round(float(np.percentile(arr, 95)), 6),
        "ci95_low":  round(mean_ - 1.96 * sem_, 6),
        "ci95_high": round(mean_ + 1.96 * sem_, 6),
        "n":         n,
    }


def _normalize_assignments(
    ensemble_assignments: Union[list[dict], dict[str, dict]],
) -> list[tuple[str, dict]]:
    """Normaliza ensemble a lista de pares (plan_id, assignment)."""
    if isinstance(ensemble_assignments, dict):
        return list(ensemble_assignments.items())
    return [(str(i), a) for i, a in enumerate(ensemble_assignments)]


# ──────────────────────────────────────────────────────────────────────────────
# run_electoral_ensemble
# ──────────────────────────────────────────────────────────────────────────────

def run_electoral_ensemble(
    ensemble_assignments: Union[list[dict], dict[str, dict]],
    votes_df: pd.DataFrame,
    pop_by_unit: pd.Series,
    magnitudes: Optional[Union[pd.Series, dict]] = None,
    pacto_map: Optional[dict] = None,
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
    threshold: float = 0.0,
    unit_col: str = "CUT",
    partido_col: str = "partido",
    votos_col: str = "votos",
    include_seat_bonus: bool = True,
) -> pd.DataFrame:
    """
    Ejecuta D'Hondt binivel sobre todos los planes de un ensemble y devuelve
    métricas electorales por plan.

    Flujo por plan
    --------------
    assignment → magnitudes → aggregate_votes → D'Hondt → métricas → fila

    Parameters
    ----------
    ensemble_assignments : list[dict] or dict[str, dict]
        Colección de planes.  Cada plan es un dict ``{unit_id: district_num}``.
        Si se pasa un dict, sus claves se usan como ``plan_id``.
    votes_df : pd.DataFrame
        Votos con columnas ``unit_col``, ``partido_col``, ``votos_col``.
        Típicamente la salida de ``sv.votos_por_comuna()``.
    pop_by_unit : pd.Series
        Población por unidad censasl (indexed by unit_id).
    magnitudes : pd.Series, dict or None
        Magnitudes fijas por distrito.  Si ``None``, se calculan por plan
        usando :func:`assign_seat_magnitudes`.  Si se pasa un ``dict``, se
        convierte a ``pd.Series``.
    pacto_map : dict {partido: pacto}, optional
        Mapa de partidos a coaliciones.  Si se provee, usa D'Hondt binivel
        (sistema real chileno Ley 18.700).  Si ``None``, D'Hondt uninivel.
    total_seats, min_seats, max_seats : int
        Parámetros de :func:`assign_seat_magnitudes`.
        Ignorados cuando ``magnitudes`` no es ``None``.
    threshold : float
        Umbral mínimo de votos del pacto (0.0 = sin umbral).
    unit_col, partido_col, votos_col : str
        Nombres de columnas en ``votes_df``.
    include_seat_bonus : bool
        Si ``True``, agrega columnas ``seat_bonus_{partido}`` (en puntos
        porcentuales) para cada partido con votos.

    Returns
    -------
    pd.DataFrame
        Una fila por plan, indexada por ``plan_id``. Columnas:

        ``gallagher``, ``loosemore_hanby``, ``rae``,
        ``enp_votos``, ``enp_escanos``, ``n_partidos_con_escanos``,
        ``seat_bonus_{partido}`` (si ``include_seat_bonus=True``),
        ``modo_dhondt``, ``modo_magnitudes``.

    Examples
    --------
    >>> plans = [{1: 1, 2: 1, 3: 2, 4: 2}, {1: 1, 2: 2, 3: 1, 4: 2}]
    >>> res = run_electoral_ensemble(plans, votes_df, pop, magnitudes=mags, pacto_map=pm)
    >>> res[["gallagher", "enp_escanos"]]
    """
    if isinstance(magnitudes, dict):
        magnitudes = pd.Series(magnitudes)

    plans   = _normalize_assignments(ensemble_assignments)
    pop_map = pop_by_unit.to_dict()
    rows: list[dict] = []

    for plan_id, assignment in plans:
        # Población por circunscripción
        pop_by_d = pd.Series(
            {d: sum(pop_map.get(u, 0) for u, dd in assignment.items() if dd == d)
             for d in set(assignment.values())}
        )

        if magnitudes is not None:
            mags     = magnitudes.reindex(pop_by_d.index, fill_value=0)
            modo_mag = "fijas"
        else:
            mags     = assign_seat_magnitudes(pop_by_d, total_seats, min_seats, max_seats)
            modo_mag = "calculadas"

        votes_dist = aggregate_votes(votes_df, assignment, unit_col, partido_col, votos_col)

        if pacto_map is not None:
            votes_dist["pacto"] = (
                votes_dist[partido_col].map(pacto_map).fillna(votes_dist[partido_col])
            )
            results = run_electoral_plan_binivel(
                votes_dist, mags,
                pacto_col="pacto", partido_col=partido_col,
                votos_col=votos_col, threshold=threshold,
            )
            modo = "binivel"
        else:
            results = run_electoral_plan(votes_dist, mags, threshold)
            modo = "uninivel"

        v_sh, s_sh = national_shares(results, partido_col=partido_col)

        escanos_pp     = results.groupby(partido_col)["escanos"].sum()
        n_con_escanos  = int((escanos_pp > 0).sum())

        row: dict = {
            "plan_id":               plan_id,
            "gallagher":             round(gallagher_index(v_sh, s_sh), 4),
            "loosemore_hanby":       round(loosemore_hanby(v_sh, s_sh), 4),
            "rae":                   round(rae_index(v_sh, s_sh), 4),
            "enp_votos":             round(effective_number_of_parties(v_sh), 4),
            "enp_escanos":           round(effective_number_of_parties(s_sh), 4),
            "n_partidos_con_escanos": n_con_escanos,
            "modo_dhondt":           modo,
            "modo_magnitudes":       modo_mag,
        }

        if include_seat_bonus:
            sbonus = seat_bonus(v_sh, s_sh)
            for partido, bonus in sbonus.items():
                row[f"seat_bonus_{partido}"] = round(float(bonus), 4)

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("plan_id")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Funciones de distribución estadística
# ──────────────────────────────────────────────────────────────────────────────

def ensemble_gallagher(ensemble_results: pd.DataFrame) -> dict:
    """
    Estadísticas de distribución del índice de Gallagher sobre el ensemble.

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble`.

    Returns
    -------
    dict con claves:
        ``mean``, ``median``, ``std``, ``p5``, ``p25``, ``p75``, ``p95``,
        ``ci95_low``, ``ci95_high``, ``n``.
    """
    if "gallagher" not in ensemble_results.columns:
        raise ValueError("ensemble_results no contiene columna 'gallagher'.")
    return _dist_stats(ensemble_results["gallagher"])


def ensemble_seat_bonus(
    ensemble_results: pd.DataFrame,
    partido: Optional[str] = None,
) -> Union[dict, pd.DataFrame]:
    """
    Distribución de la prima de escaños (seat share − vote share, en pp).

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble` con ``include_seat_bonus=True``.
    partido : str, optional
        Si se especifica, retorna estadísticas para ese partido (``dict``).
        Si ``None``, retorna un ``pd.DataFrame`` con una fila por partido.

    Returns
    -------
    dict (si partido especificado) o pd.DataFrame (si partido es None).

    Raises
    ------
    ValueError
        Si el ensemble no contiene columnas ``seat_bonus_*`` o si el partido
        solicitado no existe.
    """
    sb_cols = [c for c in ensemble_results.columns if c.startswith("seat_bonus_")]
    if not sb_cols:
        raise ValueError(
            "ensemble_results no contiene columnas seat_bonus_*. "
            "Usa run_electoral_ensemble(..., include_seat_bonus=True)."
        )

    if partido is not None:
        col = f"seat_bonus_{partido}"
        if col not in ensemble_results.columns:
            available = [c[len("seat_bonus_"):] for c in sb_cols]
            raise ValueError(
                f"Partido '{partido}' no encontrado. "
                f"Disponibles: {sorted(available)}"
            )
        return _dist_stats(ensemble_results[col])

    records = []
    for col in sb_cols:
        p = col[len("seat_bonus_"):]
        stats = _dist_stats(ensemble_results[col])
        records.append({"partido": p, **stats})
    return pd.DataFrame(records).set_index("partido").sort_index()


def ensemble_enp(ensemble_results: pd.DataFrame) -> dict:
    """
    Distribución del Número Efectivo de Partidos (Laakso-Taagepera).

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble`.

    Returns
    -------
    dict con claves ``enp_votos`` y ``enp_escanos``, cada una con las
    estadísticas de distribución (mean, median, std, percentiles, ci95).
    """
    result = {}
    for col in ("enp_votos", "enp_escanos"):
        if col not in ensemble_results.columns:
            raise ValueError(f"ensemble_results no contiene columna '{col}'.")
        result[col] = _dist_stats(ensemble_results[col])
    return result


def ensemble_effective_threshold(
    magnitudes_list: list[Union[pd.Series, dict]],
) -> pd.DataFrame:
    """
    Distribución del umbral efectivo (T_U = 1/(M+1)) por distrito.

    Útil cuando las magnitudes varían entre planes (cuando ``magnitudes=None``
    en :func:`run_electoral_ensemble`).

    Parameters
    ----------
    magnitudes_list : list of pd.Series or dict
        Un elemento por plan; cada elemento mapea ``district_id → magnitud``.

    Returns
    -------
    pd.DataFrame con una fila por distrito (indexed by district_id) y columnas
    de estadísticas de distribución.  Distritos con un único valor posible
    (magnitud fija) tendrán ``std=0``.
    """
    series_list = []
    for mags in magnitudes_list:
        if isinstance(mags, dict):
            mags = pd.Series(mags)
        ue = mags.map(umbral_efectivo)
        series_list.append(ue)

    combined = pd.DataFrame(series_list)  # filas=planes, columnas=distritos

    records = []
    for district in combined.columns:
        stats = _dist_stats(combined[district])
        records.append({"district": district, **stats})
    return pd.DataFrame(records).set_index("district").sort_index()


def summarize_electoral_ensemble(ensemble_results: pd.DataFrame) -> pd.DataFrame:
    """
    Resumen estadístico completo del ensemble electoral.

    Calcula media, mediana, desviación estándar, percentiles e IC 95% para
    todas las métricas numéricas del ensemble, incluyendo ``seat_bonus_*``.

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble`.

    Returns
    -------
    pd.DataFrame
        Indexado por ``metric``.  Columnas:
        ``mean``, ``median``, ``std``, ``p5``, ``p25``, ``p75``, ``p95``,
        ``ci95_low``, ``ci95_high``, ``n``.
    """
    sb_cols  = [c for c in ensemble_results.columns if c.startswith("seat_bonus_")]
    all_cols = [c for c in _SCALAR_METRICS + sb_cols if c in ensemble_results.columns]

    records = []
    for col in all_cols:
        stats = _dist_stats(ensemble_results[col])
        records.append({"metric": col, **stats})

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).set_index("metric")
