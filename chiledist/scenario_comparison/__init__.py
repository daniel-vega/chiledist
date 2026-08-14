"""
scenario_comparison
=====================
Funciones para comparar ensembles de redistritaje entre distintos escenarios.

API principal
-------------
    compare_ensembles(ensembles, baseline)    -> DataFrame resumen con deltas
    scenario_delta(df_comp, baseline)         -> DataFrame + columnas delta_*
    rank_scenarios(df_comp, weights)          -> DataFrame ordenado por score
    plot_tradeoff_frontier(...)               -> Figure scatter + Pareto
    plot_boxplots_comparativos(...)           -> Figure boxplots por métrica
    load_ensembles_from_disk(...)             -> dict {nombre: DataFrame}
    split_frequency_table(results_dir, ...)   -> DataFrame frecuencia de cortes
"""

from .scoring import (
    ScoringConfig,
    COLORES_DEFAULT,
    NOMBRES_CORTOS,
    METRICAS_STD,
    PESOS_DEFAULT,
)
from .compare import (
    load_ensembles_from_disk,
    load_scenario_statuses_from_disk,
    build_scenario_overview,
    assess_comparison_completeness,
    compare_ensembles,
    scenario_delta,
    rank_scenarios,
    pareto_frontier_nd,
    pareto_optimal_scenarios,
)
from .sensitivity import (
    split_frequency_table,
    position_plan_vigente,
    compare_sensitivity,
    ranking_concordance,
)
from .plots import (
    plot_tradeoff_frontier,
    plot_boxplots_comparativos,
    plot_radar_comparativo,
)

__all__ = [
    "ScoringConfig",
    "load_ensembles_from_disk",
    "load_scenario_statuses_from_disk",
    "build_scenario_overview",
    "assess_comparison_completeness",
    "compare_ensembles",
    "scenario_delta",
    "rank_scenarios",
    "pareto_frontier_nd",
    "pareto_optimal_scenarios",
    "plot_tradeoff_frontier",
    "plot_boxplots_comparativos",
    "plot_radar_comparativo",
    "split_frequency_table",
    "position_plan_vigente",
    "compare_sensitivity",
    "ranking_concordance",
    "COLORES_DEFAULT",
    "NOMBRES_CORTOS",
    "METRICAS_STD",
    "PESOS_DEFAULT",
]
