"""
electoral_ensemble
===================
Análisis distribucional de métricas electorales sobre ensembles de planes.

Flujo:
    Ensemble de planes → D'Hondt binivel → Métricas electorales → Distribuciones

Uso rápido
----------
    import chiledist as cd

    # Generar ensemble
    ensemble = [plan_0, plan_1, ..., plan_N]   # list[dict {unit_id: district}]

    results = cd.run_electoral_ensemble(
        ensemble, votes_df, pop_by_unit,
        magnitudes=cd.MAGNITUDES_LEGALES_LEY20840,
        pacto_map=pacto_map,
    )

    # Resumen estadístico
    summary = cd.summarize_electoral_ensemble(results)

    # Distribución del índice de Gallagher
    gall_stats = cd.ensemble_gallagher(results)
    print(f"Gallagher medio: {gall_stats['mean']:.2f}")

    # Gráficos
    cd.plot_ensemble_histogram(results, metric="gallagher", observed=3.4)
    cd.plot_ensemble_violin(results)
    cd.plot_ensemble_ecdf(results, metric="gallagher", observed=3.4)
"""

from .core import (
    run_electoral_ensemble,
    ensemble_gallagher,
    ensemble_seat_bonus,
    ensemble_enp,
    ensemble_effective_threshold,
    summarize_electoral_ensemble,
    _dist_stats,
    _normalize_assignments,
)
from .plots import (
    plot_ensemble_histogram,
    plot_ensemble_violin,
    plot_ensemble_ecdf,
)

__all__ = [
    "run_electoral_ensemble",
    "ensemble_gallagher",
    "ensemble_seat_bonus",
    "ensemble_enp",
    "ensemble_effective_threshold",
    "summarize_electoral_ensemble",
    "plot_ensemble_histogram",
    "plot_ensemble_violin",
    "plot_ensemble_ecdf",
]
