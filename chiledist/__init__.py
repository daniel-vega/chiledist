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

__version__ = "0.1.0"
__author__  = "chiledist"

# Equivalencia USA-Chile
from .equivalence import (
    get_equivalence_table,
    get_unit,
    get_analog,
    describe_hierarchy,
    print_equivalence,
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

# Redistritaje
from .redistricting import (
    initial_partition,
    run_recom,
    analyze_ensemble,
    export_to_redist,
    chile_constraints,
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
    # equivalence
    "get_equivalence_table", "get_unit", "get_analog",
    "describe_hierarchy", "print_equivalence",
    "EQUIVALENCE_TABLE", "USA_UNITS", "CHILE_UNITS",
    "DBF_COLUMN_MAP", "POPULATION_FIELDS",
    # loader
    "load_layer", "build_national", "load_all", "aggregate_population",
    "list_available_layers", "summarize",
    "LAYER_FILENAMES", "CRS_METRIC", "CRS_GEO",
    # graph
    "build_graph", "contract_graph", "save_graph", "load_graph",
    "graph_stats", "to_edgelist", "subgraph_region",
    # metrics
    "polsby_popper", "reock", "convex_hull_ratio", "schwartzberg",
    "all_compactness", "population_balance", "ideal_population",
    "spatial_summary", "cut_edges", "contiguity_check", "plan_summary",
    # redistricting
    "initial_partition", "run_recom", "analyze_ensemble",
    "export_to_redist", "chile_constraints",
    # viz
    "plot_adjacency_graph", "plot_layer", "plot_plan",
    "plot_compactness", "plot_equivalence_table",
]
