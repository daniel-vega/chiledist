"""
inference.comparison
======================
Comparación estadística y contrafactual entre ensembles — capa 3 (Inference
& Counterfactuals).

Resume distribuciones de ensembles, calcula deltas respecto a un baseline
y determina la frontera de Pareto N-dimensional. Usa las direcciones de
``evaluation.scoring.METRICAS_STD`` (qué dirección es "mejor" por métrica)
como vocabulario compartido con la capa de evaluación — ver nota en el
reporte de la Etapa 2 sobre esta dependencia hacia evaluation/.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ..evaluation.scoring import METRICAS_STD, ScoringConfig


# ──────────────────────────────────────────────────────────────────────────────
# compare_ensembles
# ──────────────────────────────────────────────────────────────────────────────

def compare_ensembles(
    ensembles: Dict[str, pd.DataFrame],
    baseline: str = "legal_comunas",
    percentiles: Tuple[float, float] = (0.25, 0.75),
) -> pd.DataFrame:
    """
    Resume y compara estadísticas de ensemble entre escenarios.

    Calcula mediana, p25 y p75 de cada métrica estándar, luego agrega
    columnas delta_* con la diferencia respecto al escenario baseline.

    Parameters
    ----------
    ensembles : dict {scenario_name: DataFrame}
        DataFrames de ensemble_stats.csv indexados por nombre de escenario.
    baseline : str
        Nombre del escenario de referencia para los deltas.
    percentiles : (float, float)
        Percentiles inferior y superior a reportar.

    Returns
    -------
    DataFrame con una fila por escenario y columnas:
        escenario, <col>_median, <col>_p25, <col>_p75, delta_<col>_median.
    """
    rows = []
    for sc_name, df in ensembles.items():
        row: Dict = {"escenario": sc_name}
        for col, _, _ in METRICAS_STD:
            if col in df.columns:
                vals = df[col].dropna()
                if len(vals):
                    row[f"{col}_median"] = round(float(vals.median()), 4)
                    row[f"{col}_p25"]    = round(float(vals.quantile(percentiles[0])), 4)
                    row[f"{col}_p75"]    = round(float(vals.quantile(percentiles[1])), 4)
                else:
                    row[f"{col}_median"] = None
                    row[f"{col}_p25"]    = None
                    row[f"{col}_p75"]    = None
            else:
                row[f"{col}_median"] = None
                row[f"{col}_p25"]    = None
                row[f"{col}_p75"]    = None
        rows.append(row)

    df_comp = pd.DataFrame(rows)
    if df_comp.empty:
        return df_comp

    return scenario_delta(df_comp, baseline=baseline)


# ──────────────────────────────────────────────────────────────────────────────
# scenario_delta
# ──────────────────────────────────────────────────────────────────────────────

def scenario_delta(
    df_comp: pd.DataFrame,
    baseline: str = "legal_comunas",
    metric_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Agrega columnas delta_<col> con diferencia respecto al escenario baseline.

    Delta = valor_escenario − valor_baseline.
    Para métricas donde "menor es mejor", delta negativo = mejora.

    Parameters
    ----------
    df_comp : DataFrame
        Salida de compare_ensembles() o tabla con columnas *_median.
    baseline : str
        Escenario de referencia (debe existir en df_comp["escenario"]).
    metric_cols : list[str], opcional
        Columnas a diferenciar. Por defecto: todas las columnas *_median.
    """
    if baseline not in df_comp["escenario"].values:
        return df_comp

    df_out = df_comp.copy()
    baseline_row = df_out[df_out["escenario"] == baseline].iloc[0]

    if metric_cols is None:
        metric_cols = [f"{col}_median" for col, _, _ in METRICAS_STD
                       if f"{col}_median" in df_out.columns]

    for col in metric_cols:
        if col not in df_out.columns:
            continue
        ref = baseline_row.get(col)
        if ref is None or pd.isna(ref):
            continue
        df_out[f"delta_{col}"] = (df_out[col].astype(float) - float(ref)).round(4)

    return df_out


# ──────────────────────────────────────────────────────────────────────────────
# Frontera de Pareto N-dimensional
# ──────────────────────────────────────────────────────────────────────────────

def pareto_frontier_nd(
    points: Union[np.ndarray, pd.DataFrame],
    minimize: Optional[Union[np.ndarray, List[bool], Dict[str, bool]]] = None,
) -> np.ndarray:
    """
    Índices de los puntos no-dominados en un espacio N-dimensional.

    Un punto i es dominado por j si j es igual-o-mejor en TODOS los objetivos
    y estrictamente mejor en AL MENOS UNO.

    Parameters
    ----------
    points : array-like shape (n_points, n_objectives) o DataFrame
        Matriz de valores; una fila por punto, una columna por objetivo.
    minimize : array-like de bool, dict {col: bool} o None
        True = minimizar ese objetivo, False = maximizar.
        None → minimizar todos.
        Si points es DataFrame y minimize es dict, usa nombres de columna.

    Returns
    -------
    np.ndarray de índices (int) de los puntos no-dominados.

    Examples
    --------
    >>> pts = np.array([[0.1, 5], [0.2, 3], [0.3, 2], [0.1, 6]])
    >>> pareto_frontier_nd(pts, minimize=[True, True])
    array([0, 1, 2])   # [0.3, 2] domina a [0.1, 6] en y pero no en x
    """
    if isinstance(points, pd.DataFrame):
        cols = points.columns.tolist()
        if isinstance(minimize, dict):
            minimize = np.array([minimize.get(c, True) for c in cols])
        pts = points.values.astype(float)
    else:
        pts = np.asarray(points, dtype=float)

    n, m = pts.shape

    if minimize is None:
        minimize = np.ones(m, dtype=bool)
    else:
        minimize = np.asarray(minimize, dtype=bool)

    # Convertir todo a minimización: voltear los ejes de maximización
    work = pts.copy()
    work[:, ~minimize] *= -1

    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        if not is_pareto[i]:
            continue
        # j domina a i si j <= i en todo y j < i en algo
        better_or_equal = np.all(work <= work[i], axis=1)   # (n,)
        strictly_better = np.any(work  < work[i], axis=1)   # (n,)
        dominated_by    = better_or_equal & strictly_better
        dominated_by[i] = False
        if dominated_by.any():
            is_pareto[i] = False

    return np.where(is_pareto)[0]


# ──────────────────────────────────────────────────────────────────────────────
# pareto_optimal_scenarios
# ──────────────────────────────────────────────────────────────────────────────

def pareto_optimal_scenarios(
    df_comp: pd.DataFrame,
    metric_cols: Optional[List[str]] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> pd.DataFrame:
    """
    Devuelve las filas de df_comp (salida de compare_ensembles) que son
    Pareto-óptimas entre los escenarios comparados.

    Un escenario es Pareto-óptimo si no existe otro que sea igual-o-mejor
    en todas las métricas y estrictamente mejor en al menos una.

    Parameters
    ----------
    df_comp : DataFrame
        Tabla de compare_ensembles() con columnas <col>_median.
    metric_cols : list[str], opcional
        Métricas base a considerar (sin sufijo _median).
        None → usa todas las de METRICAS_STD que estén disponibles.
    scoring_config : ScoringConfig, opcional
        Si se provee, sus `directions` sobreescriben las de METRICAS_STD.

    Returns
    -------
    DataFrame con las filas Pareto-óptimas (puede ser un subconjunto o todo).

    Examples
    --------
    >>> tabla = cd.compare_ensembles(ensembles)
    >>> cd.pareto_optimal_scenarios(tabla)
    """
    if metric_cols is None:
        metric_cols = [col for col, _, _ in METRICAS_STD]

    directions = {col: d for col, _, d in METRICAS_STD}
    if scoring_config is not None:
        directions.update(scoring_config.directions)

    avail   = [c for c in metric_cols if f"{c}_median" in df_comp.columns]
    med_cols = [f"{c}_median" for c in avail]

    if not avail:
        return df_comp.copy()

    pts = df_comp[med_cols].values.astype(float)
    minimize = np.array([directions.get(c, "min") == "min" for c in avail])

    idx = pareto_frontier_nd(pts, minimize=minimize)
    return df_comp.iloc[idx].copy().reset_index(drop=True)
