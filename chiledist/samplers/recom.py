"""
chiledist.samplers.recom
========================
Generación de planes de redistritaje mediante cadenas de Markov ReCom
(Random Spanning Tree Recombination) sobre unidades censales chilenas.

Compatible con gerrychain 0.3.2. Para SMC ver samplers.smc.
"""

from __future__ import annotations
import warnings
from typing import Optional

import numpy as np
import networkx as nx
import pandas as pd
import scipy.sparse as sp

from ..metrics import cut_edges, plan_summary, polsby_popper
from ..equivalence import get_optimal_crs, CRS_METRIC


# ──────────────────────────────────────────────────────────────────────────────
# Partición inicial
# ──────────────────────────────────────────────────────────────────────────────

def initial_partition(
    gdf,
    id_col: str,
    partition_col: str,
) -> dict:
    """
    Crea una asignación inicial {id_unidad: distrito} desde una columna
    existente (ej. CUT para usar comunas como distritos base).

    Parameters
    ----------
    partition_col : str
        Columna que define la partición inicial (ej. 'CUT', 'N_REGION').

    Returns
    -------
    dict {id: distrito}
    """
    return dict(zip(gdf[id_col], gdf[partition_col]))


# ──────────────────────────────────────────────────────────────────────────────
# Cadena ReCom (vía gerrychain)
# ──────────────────────────────────────────────────────────────────────────────

def run_recom(
    gdf,
    id_col: str,
    pop_col: str,
    n_districts: int,
    n_steps: int = 10_000,
    pop_tolerance: float = 0.05,
    initial_assignment: Optional[dict] = None,
    preserve_col: Optional[str] = None,
    random_seed: int = 42,
    save_every: int = 500,
    output_prefix: str = "plan",
    island_policy: str = "nearest",
    island_threshold_km: float = 50.0,
    crs_metric: Optional[str] = None,
) -> list[dict]:
    """
    Ejecuta una cadena de Markov ReCom para generar planes de redistritaje.

    Requiere: pip install gerrychain

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Unidades con geometrías y población.
    id_col : str
        Columna identificadora única.
    pop_col : str
        Columna de población (ej. 'viviendas').
    n_districts : int
        Número de distritos a generar.
    n_steps : int
        Número de pasos de la cadena de Markov.
    pop_tolerance : float
        Desviación máxima permitida del ideal (0.05 = ±5%).
    initial_assignment : dict, optional
        Asignación inicial {id: distrito}. Si None, se genera automáticamente.
    preserve_col : str, optional
        Columna cuyas unidades no deben partirse (ej. 'CUT' — Ley 18.700).
    random_seed : int
        Semilla para reproducibilidad.
    save_every : int
        Guardar snapshot del plan cada N pasos.
    output_prefix : str
        Prefijo para los archivos de salida.
    island_policy : str
        Política de conexión de islas en el grafo gerrychain:
        'nearest' | 'threshold' | 'none'.
    island_threshold_km : float
        Umbral de distancia (km) para island_policy='threshold'.
    crs_metric : str, opcional
        CRS métrico para cálculo de distancias. None = auto-detectar.

    Returns
    -------
    list[dict]  Lista de planes, cada uno = {id: distrito}.
    """
    try:
        import gerrychain as gc
    except ImportError:
        raise ImportError(
            "gerrychain no está instalado. "
            "Instala con: pip install gerrychain"
        )

    if crs_metric is None:
        crs_metric = get_optimal_crs(gdf)

    np.random.seed(random_seed)
    gdf = gdf.copy().reset_index(drop=True)

    gdf[pop_col] = pd.to_numeric(gdf[pop_col], errors="coerce").fillna(0)

    print("Construyendo grafo gerrychain...")
    cols = [id_col, pop_col] + (
        [preserve_col] if preserve_col and preserve_col in gdf.columns else []
    )
    graph = gc.Graph.from_geodataframe(
        gdf,
        adjacency="queen",
        cols_to_add=[c for c in cols if c in gdf.columns],
    )

    # Aplicar política de islas al grafo de gerrychain
    isolated = [n for n in graph.nodes() if graph.degree(n) == 0]
    if isolated and island_policy != "none":
        gdf_m     = gdf.to_crs(crs_metric)
        centroids = gdf_m.geometry.centroid
        cx        = centroids.x.to_numpy()
        cy        = centroids.y.to_numpy()
        threshold_m = island_threshold_km * 1000.0

        for node in isolated:
            dx   = cx - cx[node]
            dy   = cy - cy[node]
            dist = np.sqrt(dx * dx + dy * dy)
            dist[node] = np.inf

            # En modo threshold, forzar infinito más allá del umbral
            if island_policy == "threshold":
                dist[dist > threshold_m] = np.inf

            nearest = int(np.argmin(dist))
            if dist[nearest] < np.inf:
                graph.add_edge(node, nearest)

        n_connected = sum(1 for n in isolated if graph.degree(n) > 0)
        print(f"  Islas conectadas en gerrychain "
              f"({island_policy}): {n_connected}/{len(isolated)}")

    if not graph.is_connected():
        n_comp = len(list(nx.connected_components(graph)))
        warnings.warn(
            f"El grafo gerrychain tiene {n_comp} componentes desconectados. "
            "Considera island_policy='nearest' o reducir island_threshold_km."
        )

    if initial_assignment is None:
        print(f"Generando partición inicial con {n_districts} distritos...")
        assignment_col = _make_initial_assignment(gdf, id_col, pop_col,
                                                   n_districts, graph)
    else:
        gdf["__init_dist__"] = gdf[id_col].map(initial_assignment)
        assignment_col = "__init_dist__"

    updaters = {
        "population": gc.updaters.Tally(pop_col, alias="population"),
        "cut_edges":  gc.updaters.cut_edges,
    }
    if preserve_col and preserve_col in gdf.columns:
        updaters["splits"] = gc.updaters.CountSplits(preserve_col)

    partition = gc.Partition(
        graph=graph,
        assignment=assignment_col,
        updaters=updaters,
    )

    constraints = [gc.constraints.contiguous]
    constraints.append(
        gc.constraints.within_percent_of_ideal_population(
            partition, pop_tolerance
        )
    )
    if preserve_col and preserve_col in gdf.columns:
        print(f"  Restricción: preservar límites de '{preserve_col}'")
        constraints.append(
            lambda p: p["splits"].total == 0
        )

    chain = gc.MarkovChain(
        proposal=gc.proposals.recom,
        constraints=constraints,
        accept=gc.accept.always_accept,
        initial_state=partition,
        total_steps=n_steps,
    )

    print(f"Iniciando ReCom: {n_steps:,} pasos · "
          f"{n_districts} distritos · tolerancia ±{pop_tolerance*100:.0f}%")

    plans   = []
    metrics = []

    for step, state in enumerate(chain):
        assignment = dict(state.assignment)
        plans.append(assignment)

        if step % save_every == 0:
            pop_dev = max(
                abs(pop - state["population"].ideal_pop)
                / state["population"].ideal_pop
                for pop in state["population"].values()
            ) * 100
            n_cuts = len(state["cut_edges"])
            metrics.append({
                "step":        step,
                "cut_edges":   n_cuts,
                "max_pop_dev": round(pop_dev, 3),
            })
            print(f"  Paso {step:6,} | "
                  f"aristas cortadas: {n_cuts:,} | "
                  f"desv. pob. máx: {pop_dev:.2f}%")

    df_plans = pd.DataFrame(plans)
    df_plans.to_csv(f"{output_prefix}_planes.csv", index=False)
    pd.DataFrame(metrics).to_csv(f"{output_prefix}_metricas.csv", index=False)
    print(f"\nGuardado: {output_prefix}_planes.csv  ({len(plans)} planes)")
    print(f"Guardado: {output_prefix}_metricas.csv")

    return plans


# ──────────────────────────────────────────────────────────────────────────────
# Bucle canónico de la cadena ReCom (delegado desde scripts/redistritaje.py)
# ──────────────────────────────────────────────────────────────────────────────

def run_recom_chain(
    chain,
    n_steps: int,
    id_col: str,
    ids_ordenados: list,
    graph,
    ideal_pop: float,
    output_dir: Optional[str] = None,
    run_id: Optional[str] = None,
    scenario_name: str = "",
    chain_id: int = 0,
) -> tuple:
    """
    Ejecuta un gerrychain.MarkovChain ya configurado y recolecta planes + métricas.

    Implementación canónica del bucle ReCom. Es la única fuente de verdad para
    el muestreo; scripts/redistritaje.py delega aquí en lugar de reimplementar.

    Parameters
    ----------
    chain : gc.MarkovChain
        Cadena configurada (propuesta + restricciones + estado inicial).
    n_steps : int
        Pasos totales a ejecutar.
    id_col : str
        Columna identificadora de unidades ('ID_DIST' o 'CUT').
    ids_ordenados : list
        Lista ordenada de unit IDs (misma posición que los nodos del grafo).
    graph : gc.Graph
        Grafo gerrychain; usado para resolver node_idx → unit_id.
    ideal_pop : float
        Población ideal por distrito (para calcular max_dev_pct).
    output_dir : str, opcional
        Si se indica, guarda assignments.parquet en este directorio.
    run_id : str, opcional
        UUID de la corrida; se incluye en assignments.parquet.
    scenario_name : str
        Nombre del escenario; se incluye en assignments.parquet.
    chain_id : int
        Índice de cadena (0 para ejecución única).

    Returns
    -------
    tuple (planes, metricas_mc, n_executed)
        planes : list[dict]   — {node_idx: district} por paso
        metricas_mc : list[dict]  — métricas por paso
        n_executed : int      — pasos realmente ejecutados
    """
    planes: list[dict]      = []
    metricas_mc: list[dict] = []

    try:
        for step, state in enumerate(chain):
            planes.append(dict(state.assignment))
            pop_vals = list(state["population"].values())
            max_dev  = (max(abs(p - ideal_pop) / ideal_pop for p in pop_vals) * 100
                        if ideal_pop > 0 else 0.0)
            n_cuts   = len(state["cut_edges"])
            metricas_mc.append({
                "step":        step,
                "cut_edges":   n_cuts,
                "max_dev_pct": round(max_dev, 3),
            })
            if step % max(1, n_steps // 10) == 0:
                print(f"    Paso {step:6,} | cortes: {n_cuts:4d} | "
                      f"desv: {max_dev:.2f}%")
    except (IndexError, RuntimeError) as e:
        print(f"  ⚠ Cadena interrumpida en paso {len(planes)}: {e}")
        if not planes:
            return [], [], 0

    n_executed = len(planes)

    # Guardar assignments.parquet si se solicitó
    if output_dir and planes:
        try:
            from ..persistence import save_assignments_parquet

            # Construir id_map: node_idx → unit_id
            id_map: dict = {}
            for node in graph.nodes():
                id_val = graph.nodes[node].get(id_col)
                if id_val is None and isinstance(node, int) and node < len(ids_ordenados):
                    id_val = ids_ordenados[node]
                id_map[node] = id_val

            save_assignments_parquet(
                planes=planes,
                id_map=id_map,
                run_id=run_id or "",
                scenario_name=scenario_name,
                output_dir=output_dir,
                chain_id=chain_id,
            )
        except Exception as e:
            warnings.warn(
                f"No se pudo guardar assignments.parquet: {e}",
                RuntimeWarning,
                stacklevel=2,
            )

    return planes, metricas_mc, n_executed


def _make_initial_assignment(gdf, id_col, pop_col, n_districts, graph):
    """Genera una asignación inicial aleatoria válida."""
    try:
        import gerrychain as gc
        return gc.constraints.contiguous_bfs(graph, n_districts)
    except Exception:
        warnings.warn("No se pudo generar partición contigua inicial. "
                      "Usando asignación por módulo.")
        gdf["__init__"] = [i % n_districts for i in range(len(gdf))]
        return "__init__"


# ──────────────────────────────────────────────────────────────────────────────
# Análisis de ensemble
# ──────────────────────────────────────────────────────────────────────────────

def analyze_ensemble(
    plans: list[dict],
    gdf,
    id_col: str,
    pop_col: str,
    adj: Optional[sp.csr_matrix] = None,
    id_list: Optional[list] = None,
    sample_size: int = 100,
) -> pd.DataFrame:
    """
    Analiza un ensemble de planes calculando métricas agregadas.

    Parameters
    ----------
    plans : list[dict]
        Lista de planes generados por run_recom().
    sample_size : int
        Número de planes a analizar (subsample si len(plans) > sample_size).

    Returns
    -------
    pd.DataFrame con métricas por plan:
        plan_id, n_distritos, max_desv_pob_pct, pp_promedio, aristas_cortadas.
    """
    from ..metrics import _ensure_metric

    if len(plans) > sample_size:
        idx   = np.linspace(0, len(plans) - 1, sample_size, dtype=int)
        plans = [plans[i] for i in idx]

    gdf_m = _ensure_metric(gdf)
    rows  = []

    for plan_id, assignment in enumerate(plans):
        gdf_m["__d__"] = gdf_m[id_col].map(assignment)

        pop_by_d = gdf_m.groupby("__d__")[pop_col].sum()
        ideal    = pop_by_d.mean()
        max_dev  = ((pop_by_d - ideal).abs() / ideal).max() * 100

        dissolved = gdf_m.dissolve("__d__")
        pp = (
            4 * np.pi * dissolved.geometry.area
            / (dissolved.geometry.length ** 2)
        ).mean()

        n_cuts = (
            cut_edges(adj, assignment, id_list)
            if adj is not None and id_list is not None
            else np.nan
        )

        rows.append({
            "plan_id":          plan_id,
            "n_distritos":      pop_by_d.shape[0],
            "max_desv_pob_pct": round(max_dev, 3),
            "pp_promedio":      round(pp, 4),
            "aristas_cortadas": n_cuts,
        })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Restricciones específicas para Chile
# ──────────────────────────────────────────────────────────────────────────────

def chile_constraints(
    gdf,
    id_col: str,
    adj: sp.csr_matrix,
    id_list: list,
    preserve_comunas: bool = True,
    preserve_regiones: bool = False,
) -> dict:
    """
    Define las restricciones del sistema electoral chileno.

    Ley 18.700: los distritos electorales no pueden partir comunas.

    Returns
    -------
    dict con 'preserve_comunas', 'preserve_regiones', 'descripcion'.
    """
    result = {
        "preserve_comunas":  preserve_comunas,
        "preserve_regiones": preserve_regiones,
        "descripcion": [],
    }

    if preserve_comunas:
        n_comunas = gdf["CUT"].nunique() if "CUT" in gdf.columns else "?"
        result["descripcion"].append(
            f"Ley 18.700: {n_comunas} comunas deben preservarse íntegras."
        )

    if preserve_regiones:
        n_reg = gdf["N_REGION"].nunique() if "N_REGION" in gdf.columns else "?"
        result["descripcion"].append(
            f"Restricción regional: {n_reg} regiones no deben partirse."
        )

    result["descripcion"].append("Contigüidad geográfica obligatoria (Queen).")

    print("\n── Restricciones electorales Chile ──────────────────────")
    for d in result["descripcion"]:
        print(f"  • {d}")

    return result
