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

from ._version import __version__
__author__  = "chiledist"

# Configuración de escenarios: dataclass + I/O (capa 0 — domain)
from .domain.scenario import (
    ScenarioConfig,
    load_scenario,
    save_scenario,
)

# Presets legales de escenario (capa 1 — rules)
from .rules.scenario_rules import (
    SCENARIO_LEGAL,
    SCENARIO_APC_STRICT,
    SCENARIO_APC_SOFT,
    SCENARIO_APC_FREE,
    SCENARIOS,
)

# Texto de encuadre legislativo (capa 4 — evaluation)
from .evaluation.framing import reforma_context

# Preflight de factibilidad poblacional (capa 1 — rules)
from .rules.feasibility import (
    PopulationFeasibilityResult,
    check_population_feasibility,
    REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND,
)

# Jerarquía y contracción de unidades (capa 0 — domain)
from .domain.hierarchy import (
    contract_to_decision_units,
    build_decision_layer,
    validate_hierarchy,
    propagate_district_assignment,
    normalize_cut,
)

# Restricción legal de preservación (capa 1 — rules)
from .rules.constraints import (
    make_preserve_constraint,
    build_constraints_for_scenario,
)

# Mecánica de motor para el modo "soft" (capa 2 — engines)
from .engines.samplers.updaters import (
    build_updaters_for_scenario,
    make_split_severity_updater,
)
from .engines.samplers.accept import (
    make_split_penalty_accept,
    score_with_split_penalty,
)

# Equivalencia USA-Chile (capa 0 — domain)
from .domain.equivalence import (
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

# Carga de datos (capa 0 — domain)
from .domain.loader import (
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

# Grafos y matrices (capa 0 — domain)
from .domain.graph import (
    build_graph,
    contract_graph,
    save_graph,
    load_graph,
    graph_stats,
    to_edgelist,
    subgraph_region,
)

# Métricas (capa 2 — engines)
from .engines.metrics import (
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
    # métricas de comunas partidas (regla en .rules.split_rules)
    count_split_units,
    split_severity_index,
    split_unit_summary,
    small_fragment_count,
    pop_afectada_pct,
    plan_split_metrics,
)

# Fuentes de población externas (Censo 2024 + SERVEL) (capa 0 — domain)
from .domain import data as data
from .domain.data import normalize_commune_name

# Comparación de escenarios
# Carga de ensembles desde disco y completitud (capa 0 — domain)
from .domain.ensemble_store import (
    load_ensembles_from_disk,
    load_scenario_statuses_from_disk,
    build_scenario_overview,
    assess_comparison_completeness,
)

# Comparación estadística y contrafactual entre ensembles (capa 3 — inference)
from .inference.comparison import (
    compare_ensembles,
    scenario_delta,
    pareto_frontier_nd,
    pareto_optimal_scenarios,
)
from .inference.sensitivity import (
    split_frequency_table,
    position_plan_vigente,
    compare_sensitivity,
    ranking_concordance,
)
from .inference.plots import (
    plot_tradeoff_frontier,
    plot_boxplots_comparativos,
    plot_radar_comparativo,
)

# Puntaje compuesto ponderado (capa 4 — evaluation)
from .evaluation.scoring import (
    ScoringConfig,
    rank_scenarios,
    COLORES_DEFAULT,
    NOMBRES_CORTOS,
    METRICAS_STD,
    PESOS_DEFAULT,
)

# Análisis continuo de la frontera Pareto (barrido de split_penalty) (capa 3 — inference)
from .inference.pareto_sweep import (
    sweep_split_penalty,
    build_tradeoff_frontier,
    detect_knee_point,
    plot_tradeoff_curve,
    summarize_tradeoff,
    SWEEP_METRICS,
    METRIC_DIRECTIONS,
    METRIC_LABELS,
)

# Malapportionment geográfico: índices comparables internacionalmente (capa 4 — evaluation)
from .evaluation.malapportionment import (
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

# Ensemble electoral: análisis distribucional sobre ensembles de planes (capa 3 — inference)
from .inference.electoral_ensemble import (
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

# Fair share biproporcional (capa 2 — engines)
from .engines.fairshare import (
    fair_share_matrix,
    results_to_matrix,
    l1_distance_fair_share,
    l2_distance_fair_share,
    max_cell_deviation,
    fair_share_summary,
)

# Constantes legales del sistema electoral (capa 1 — rules)
from .rules.electoral_rules import (
    TOTAL_ESCANOS_CAMARA,
    MIN_ESCANOS_DISTRITO,
    MAX_ESCANOS_DISTRITO,
    MAGNITUDES_LEGALES_LEY20840,
    MAGNITUDES_LEGALES_2021,
    MAGNITUDES_CENSO2024_2026,
)

# Normalización de nombres de partido/pacto (capa 0 — domain)
from .domain.utils import normalize_party_name

# Asignación de escaños: D'Hondt, magnitudes, agregador de plan (capa 2 — engines)
from .engines.allocation import (
    dhondt,
    dhondt_binivel,
    assign_seat_magnitudes,
    assign_seat_magnitudes_dhondt,
    aggregate_votes,
    run_electoral_plan,
    run_electoral_plan_binivel,
    national_shares,
    comparar_magnitudes,
    plan_electoral_metrics,
)

# Proporcionalidad y malapportionment distrital (capa 4 — evaluation)
from .evaluation import (
    gallagher_index,
    loosemore_hanby,
    rae_index,
    effective_number_of_parties,
    proportionality_summary,
    seat_bonus,
    personas_por_escano,
    peso_relativo_del_voto,
    weighted_population_balance,
    umbral_efectivo,
    margen_ultimo_escano,
)

# Persistencia reproducible (capa 0 — domain)
from .domain.persistence import (
    PlanEnsemble,
    new_run_id,
    sha256_file,
    get_package_versions,
    save_assignments_parquet,
    build_run_manifest,
    save_run_manifest,
)

# Contenedor de datos cargados (capa 0 — domain)
from .domain.map import ChileDistMap

# Muestreo: ReCom, SMC y diagnósticos de convergencia (capa 2 — engines)
from .engines import samplers as samplers
from .engines.samplers import (
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
    "load_scenario", "save_scenario", "reforma_context",
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
    "data", "normalize_commune_name",
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
    "RHAT_THRESHOLD",
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
