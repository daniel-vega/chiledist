"""
pareto_sweep
=============
Análisis continuo de la frontera Pareto en el espacio de tradeoffs de redistritaje.

Flujo:
    Ensembles por nivel de penalización → Pool consolidado → Frontera Pareto real →
    Bandas bootstrap → Detección de knee point → Figuras publicables

Diferencia con scripts/pareto_sweep.py
---------------------------------------
Este módulo opera sobre **planes individuales** (no medianas por escenario):
cada plan del ensemble es un punto en el espacio de objetivos. La frontera
Pareto resultante es la verdadera envolvente eficiente del espacio de búsqueda.

Uso rápido
----------
    import chiledist as cd
    import numpy as np, pandas as pd

    penalties = np.linspace(0, 1, 11)
    ensembles = {
        p: pd.read_csv(f"datos/R13_METROPOLITANA/redistritaje/apc_soft_p{p:.2f}/ensemble_stats.csv")
        for p in penalties
    }

    sweep_df       = cd.sweep_split_penalty(ensembles)
    frontier_res   = cd.build_tradeoff_frontier(sweep_df)
    knee           = cd.detect_knee_point(frontier_res["frontier"])
    fig            = cd.plot_tradeoff_curve(sweep_df, frontier_res, knee)
    summary        = cd.summarize_tradeoff(sweep_df, frontier_res, knee)
"""

from .frontier import (
    sweep_split_penalty,
    build_tradeoff_frontier,
    detect_knee_point,
    summarize_tradeoff,
    SWEEP_METRICS,
    METRIC_DIRECTIONS,
    METRIC_LABELS,
)
from .plots import plot_tradeoff_curve

__all__ = [
    "sweep_split_penalty",
    "build_tradeoff_frontier",
    "detect_knee_point",
    "plot_tradeoff_curve",
    "summarize_tradeoff",
    "SWEEP_METRICS",
    "METRIC_DIRECTIONS",
    "METRIC_LABELS",
]
