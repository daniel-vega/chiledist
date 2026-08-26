"""
chiledist
=========
Librería para análisis distrital de Chile usando datos APC 2023 (INE).

Provee:
    - Equivalencia de unidades censales USA ↔ Chile
    - Carga unificada de capas geográficas APC
    - Construcción de grafos de adyacencia y matrices sparse
    - Métricas de compacidad y balance poblacional
    - Generación de planes de redistritaje (ReCom / SMC)
    - Visualización de capas, grafos y planes

Uso rápido
----------
    import chiledist as cd

    # Ver equivalencia USA-Chile
    cd.print_equivalence()

    # Cargar distritos
    distritos = cd.load_layer("distrital", base_dir="./datos")

    # Construir grafo
    G, adj, id_list = cd.build_graph(distritos, id_col="ID_DIST")

    # Métricas de compacidad
    metricas = cd.all_compactness(distritos, id_col="ID_DIST")

    # Visualizar
    cd.plot_adjacency_graph(G, adj, indice, color_by="tipo",
                             save_path="grafo_distrital.png")

Referencias
-----------
    ALARM Project (Harvard): https://alarm-redist.org
    APC 2023 (INE Chile):    https://www.ine.gob.cl
    redist (R package):      https://redist.alarm-redist.org
    gerrychain (Python):     https://gerrychain.readthedocs.io
"""

__version__ = "0.2.0"
__author__  = "chiledist"

# Configuración de escenarios
from .config import (
    ScenarioConfig,
    SCENARIO_LEGAL,
    SCENARIO_APC_STRICT,
    SCENARIO_APC_SOFT,
    SCENARIO_APC_FREE,
    SCENARIOS,
    load_scenario,
    save_scenario,
)

# Preflight de factibilidad poblacional
from .feasibility import (
    PopulationFeasibilityResult,
    check_population_feasibility,
    REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND,
)

# Jerarquía y contracción de unidades
from .hierarchy import (
    contract_to_decision_units,
    build_decision_layer,
    validate_hierarchy,
    propagate_district_assignment,
    normalize_cut,
)

# Restricciones para gerrychain
from .constraints import (
    make_preserve_constraint,
    build_updaters_for_scenario,
    build_constraints_for_scenario,
    score_with_split_penalty,
    make_split_severity_updater,
    make_split_penalty_accept,
)

# Métricas de comunas partidas
from .split_metrics import (
    count_split_units,
    split_severity_index,
    split_unit_summary,
    small_fragment_count,
    pop_afectada_pct,
    plan_split_metrics,
)

# Equivalencia USA-Chile
from .equivalence import (
    get_equivalence_table,
    get_unit,
    get_analog,
    describe_hierarchy,
    print_equivalence,
    get_optimal_crs,
    EQUIVALENCE_TABLE,
    USA_UNITS,
    CHILE_UNITS,
    DBF_COLUMN_MAP,
    POPULATION_FIELDS,
)

# Carga de datos
from .loader import (
    build_national,
    load_layer,
    load_all,
    aggregate_population,
    aggregate_rural_proxy,
    apply_rural_proxy_fallback,
    list_available_layers,
    summarize,
    LAYER_FILENAMES,
    CRS_METRIC,
    CRS_GEO,
)

# Grafos y matrices
from .graph import (
    build_graph,
    contract_graph,
    save_graph,
    load_graph,
    graph_stats,
    to_edgelist,
    subgraph_region,
)

# Métricas
from .metrics import (
    polsby_popper,
    reock,
    convex_hull_ratio,
    schwartzberg,
    all_compactness,
    population_balance,
    ideal_population,
    spatial_summary,
    cut_edges,
    contiguity_check,
    plan_summary,
)

# Fuentes de población externas (Censo 2024 + SERVEL)
from . import data as data

# Comparación de escenarios
from .scenario_comparison import (
    ScoringConfig,
    load_ensembles_from_disk,
    load_scenario_statuses_from_disk,
    build_scenario_overview,
    assess_comparison_completeness,
    compare_ensembles,
    scenario_delta,
    rank_scenarios,
    pareto_frontier_nd,
    pareto_optimal_scenarios,
    plot_tradeoff_frontier,
    plot_boxplots_comparativos,
    plot_radar_comparativo,
    split_frequency_table,
    position_plan_vigente,
    compare_sensitivity,
    ranking_concordance,
    COLORES_DEFAULT,
    NOMBRES_CORTOS,
    METRICAS_STD,
    PESOS_DEFAULT,
)

# Análisis continuo de la frontera Pareto (barrido de split_penalty)
from .pareto_sweep import (
    sweep_split_penalty,
    build_tradeoff_frontier,
    detect_knee_point,
    plot_tradeoff_curve,
    summarize_tradeoff,
    SWEEP_METRICS,
    METRIC_DIRECTIONS,
    METRIC_LABELS,
)

# Malapportionment geográfico: índices comparables internacionalmente
from .malapportionment import (
    samuels_snyder_index,
    loosemore_hanby_malapportionment,
    gini_personas_por_escano,
    max_min_representation_ratio,
    malapportionment_summary,
    compare_plans as compare_malapportionment_plans,
    international_comparison,
    plot_pxe_distribution,
    plot_malapportionment_ranking,
    plot_international_comparison,
    BENCHMARK_MALAPPORTIONMENT,
)

# Ensemble electoral: análisis distribucional sobre ensembles de planes
from .electoral_ensemble import (
    run_electoral_ensemble,
    ensemble_gallagher,
    ensemble_seat_bonus,
    ensemble_enp,
    ensemble_effective_threshold,
    summarize_electoral_ensemble,
    plot_ensemble_histogram,
    plot_ensemble_violin,
    plot_ensemble_ecdf,
)

# Electoral: D'Hondt, magnitudes, proporcionalidad
from .fairshare import (
    fair_share_matrix,
    results_to_matrix,
    l1_distance_fair_share,
    l2_distance_fair_share,
    max_cell_deviation,
    fair_share_summary,
)

from .electoral import (
    dhondt,
    dhondt_binivel,
    assign_seat_magnitudes,
    assign_seat_magnitudes_dhondt,
    aggregate_votes,
    run_electoral_plan,
    run_electoral_plan_binivel,
    national_shares,
    gallagher_index,
    loosemore_hanby,
    rae_index,
    effective_number_of_parties,
    proportionality_summary,
    plan_electoral_metrics,
    # malapportionment
    personas_por_escano,
    peso_relativo_del_voto,
    weighted_population_balance,
    comparar_magnitudes,
    umbral_efectivo,
    margen_ultimo_escano,
    seat_bonus,
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
    MAGNITUDES_LEGALES_LEY20840,
    MAGNITUDES_LEGALES_2021,
    MAGNITUDES_CENSO2024_2026,
    normalize_party_name,
)

# Persistencia reproducible
from .persistence import (
    PlanEnsemble,
    new_run_id,
    sha256_file,
    get_package_versions,
    save_assignments_parquet,
    build_run_manifest,
    save_run_manifest,
)

# Contenedor de datos cargados
from .map import ChileDistMap

# Muestreo: ReCom, SMC y diagnósticos de convergencia
from . import samplers as samplers
from .samplers import (
    # recom
    initial_partition,
    run_recom,
    run_recom_chain,
    analyze_ensemble,
    chile_constraints,
    # smc
    export_to_redist,
    generate_redist_script,
    load_redist_results,
    # diagnostics
    autocorrelation_function,
    effective_sample_size,
    gelman_rubin,
    mixing_diagnostics,
    plot_trace,
    plot_acf,
    plot_gelman_rubin_evolution,
    run_multiple_chains,
    RHAT_THRESHOLD,
)

# Visualización
from .viz import (
    plot_adjacency_graph,
    plot_layer,
    plot_plan,
    plot_compactness,
    plot_equivalence_table,
)

__all__ = [
    # config
    "ScenarioConfig",
    "SCENARIO_LEGAL", "SCENARIO_APC_STRICT",
    "SCENARIO_APC_SOFT", "SCENARIO_APC_FREE", "SCENARIOS",
    "load_scenario", "save_scenario",
    # hierarchy
    "contract_to_decision_units", "build_decision_layer",
    "validate_hierarchy", "propagate_district_assignment",
    "normalize_cut",
    # constraints
    "make_preserve_constraint", "build_updaters_for_scenario",
    "build_constraints_for_scenario", "score_with_split_penalty",
    "make_split_severity_updater", "make_split_penalty_accept",
    # split_metrics
    "count_split_units", "split_severity_index", "split_unit_summary",
    "small_fragment_count", "pop_afectada_pct", "plan_split_metrics",
    # equivalence
    "get_equivalence_table", "get_unit", "get_analog",
    "describe_hierarchy", "print_equivalence", "get_optimal_crs",
    "EQUIVALENCE_TABLE", "USA_UNITS", "CHILE_UNITS",
    "DBF_COLUMN_MAP", "POPULATION_FIELDS",
    # loader
    "load_layer", "build_national", "load_all", "aggregate_population",
    "aggregate_rural_proxy", "apply_rural_proxy_fallback",
    "list_available_layers", "summarize",
    "LAYER_FILENAMES", "CRS_METRIC", "CRS_GEO",
    # graph
    "build_graph", "contract_graph", "save_graph", "load_graph",
    "graph_stats", "to_edgelist", "subgraph_region",
    # metrics
    "polsby_popper", "reock", "convex_hull_ratio", "schwartzberg",
    "all_compactness", "population_balance", "ideal_population",
    "spatial_summary", "cut_edges", "contiguity_check", "plan_summary",
    # data (subpaquete — acceder vía cd.data.census2024 / cd.data.servel)
    "data",
    # scenario_comparison
    "ScoringConfig",
    "load_ensembles_from_disk", "load_scenario_statuses_from_disk",
    "build_scenario_overview", "assess_comparison_completeness",
    "compare_ensembles", "scenario_delta",
    "rank_scenarios", "pareto_frontier_nd", "pareto_optimal_scenarios",
    "plot_tradeoff_frontier", "plot_boxplots_comparativos",
    "plot_radar_comparativo", "split_frequency_table",
    "position_plan_vigente", "compare_sensitivity", "ranking_concordance",
    "COLORES_DEFAULT", "NOMBRES_CORTOS", "METRICAS_STD", "PESOS_DEFAULT",
    # pareto_sweep
    "sweep_split_penalty", "build_tradeoff_frontier",
    "detect_knee_point", "plot_tradeoff_curve", "summarize_tradeoff",
    "SWEEP_METRICS", "METRIC_DIRECTIONS", "METRIC_LABELS",
    # malapportionment
    "samuels_snyder_index", "loosemore_hanby_malapportionment",
    "gini_personas_por_escano", "max_min_representation_ratio",
    "malapportionment_summary", "compare_malapportionment_plans",
    "international_comparison",
    "plot_pxe_distribution", "plot_malapportionment_ranking",
    "plot_international_comparison",
    "BENCHMARK_MALAPPORTIONMENT",
    # electoral_ensemble
    "run_electoral_ensemble",
    "ensemble_gallagher", "ensemble_seat_bonus", "ensemble_enp",
    "ensemble_effective_threshold", "summarize_electoral_ensemble",
    "plot_ensemble_histogram", "plot_ensemble_violin", "plot_ensemble_ecdf",
    # fairshare
    "fair_share_matrix", "results_to_matrix",
    "l1_distance_fair_share", "l2_distance_fair_share",
    "max_cell_deviation", "fair_share_summary",
    # electoral
    "dhondt", "dhondt_binivel",
    "assign_seat_magnitudes", "assign_seat_magnitudes_dhondt", "aggregate_votes",
    "run_electoral_plan", "run_electoral_plan_binivel", "national_shares",
    "gallagher_index", "loosemore_hanby", "rae_index",
    "effective_number_of_parties", "proportionality_summary",
    "plan_electoral_metrics",
    # malapportionment
    "personas_por_escano", "peso_relativo_del_voto", "weighted_population_balance",
    "comparar_magnitudes",
    "umbral_efectivo", "margen_ultimo_escano", "seat_bonus",
    "TOTAL_ESCANOS_CAMARA", "MIN_ESCANOS_DISTRITO", "MAX_ESCANOS_DISTRITO",
    "MAGNITUDES_LEGALES_LEY20840", "MAGNITUDES_LEGALES_2021",
    "MAGNITUDES_CENSO2024_2026",
    "normalize_party_name",
    # diagnostics
    "autocorrelation_function", "effective_sample_size", "gelman_rubin",
    "mixing_diagnostics", "plot_trace", "plot_acf",
    "plot_gelman_rubin_evolution", "run_multiple_chains",
    "generate_redist_script", "load_redist_results", "RHAT_THRESHOLD",
    # persistence
    "PlanEnsemble", "new_run_id", "sha256_file", "get_package_versions",
    "save_assignments_parquet", "build_run_manifest", "save_run_manifest",
    # map
    "ChileDistMap",
    # samplers (subpaquete — acceder vía cd.samplers.recom / .smc / .diagnostics)
    "samplers",
    # samplers.recom
    "initial_partition", "run_recom", "run_recom_chain",
    "analyze_ensemble", "chile_constraints",
    # samplers.smc
    "export_to_redist", "generate_redist_script", "load_redist_results",
    # viz
    "plot_adjacency_graph", "plot_layer", "plot_plan",
    "plot_compactness", "plot_equivalence_table",
]
