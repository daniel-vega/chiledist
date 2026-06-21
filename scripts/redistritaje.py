"""
scripts/redistritaje.py
=======================
Redistritaje ReCom parametrizable por región y escenario.

Tres modos de operación (ScenarioConfig):
    legal         → decision_unit=CUT  (comunas indivisibles, Ley 18.700)
    apc_free      → decision_unit=ID_DIST, preserve_mode=none
    apc_soft      → decision_unit=ID_DIST, preserve_mode=soft, penalty=0.25

Salidas en datos/<REGION>/redistritaje/<SCENARIO>/:
    ref_vs_extremo.png         # plan de referencia vs plan de menor score
    cadena_markov.png
    ensemble_distribucion.png
    ref_balance.png            # balance poblacional del plan de referencia
    compacidad.png
    metricas_cadena.csv
    ensemble_stats.csv         # distribución completa — resultado estadístico principal
    plan_referencia_detalle.csv  # plan seleccionado para visualización (no el "mejor")
    comunas_partidas.csv       # solo modos APC

Uso:
    # APC libre (default anterior)
    python scripts/redistritaje.py --base-dir . --regiones 13

    # Modo legal (comunas indivisibles)
    python scripts/redistritaje.py --base-dir . --regiones 13 --scenario legal

    # APC con penalización
    python scripts/redistritaje.py --base-dir . --regiones 13 --scenario apc_soft

    # Desde YAML personalizado
    python scripts/redistritaje.py --base-dir . --regiones 13 \\
        --scenario-file scenarios/mi_escenario.yml

    # Parámetros explícitos
    python scripts/redistritaje.py --base-dir . --regiones 13 \\
        --decision-unit CUT --preserve-mode hard \\
        --n-distritos 8 --pop-tol 0.05
"""

import argparse
import os
import sys
import warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import scipy.sparse as sp
import networkx as nx
from functools import partial

import chiledist as cd
from chiledist.config import ScenarioConfig, SCENARIOS, load_scenario


REGION_NOMBRES = {
    1:  "R01_TARAPACA",    2:  "R02_ANTOFAGASTA",
    3:  "R03_ATACAMA",     4:  "R04_COQUIMBO",
    5:  "R05_VALPARAISO",  6:  "R06_OHIGGINS",
    7:  "R07_MAULE",       8:  "R08_BIOBIO",
    9:  "R09_ARAUCANIA",   10: "R10_LOS_LAGOS",
    11: "R11_AYSEN",       12: "R12_MAGALLANES",
    13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS",
    15: "R15_ARICA",       16: "R16_NUBLE",
}


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Redistritaje ReCom por región con soporte de escenarios."
    )
    p.add_argument("--base-dir",   default=".",
                   help="Directorio raíz con SHP_APC2023_R*")
    p.add_argument("--output-dir", default=None,
                   help="Directorio base de salida (default: <base-dir>/datos)")
    p.add_argument("--regiones",   default="13",
                   help="Regiones: número, lista (5,8,13) o 'todas'")
    p.add_argument("--n-distritos", type=int, default=8,
                   help="Número de distritos electorales a generar (default: 8)")
    p.add_argument("--pop-tol",    type=float, default=None,
                   help="Tolerancia poblacional (default: usa pop_tolerance del escenario, "
                        "normalmente 0.05 = ±5%%. Usa 0.15 para regiones con pocos nodos "
                        "o particiones iniciales difíciles de balancear.)")
    p.add_argument("--n-steps",    type=int, default=10000,
                   help="Pasos de la cadena ReCom (default: 10000)")
    p.add_argument("--seed",       type=int, default=42,
                   help="Semilla aleatoria (default: 42)")
    p.add_argument("--skip-viz",   action="store_true",
                   help="Omitir visualizaciones")

    # Escenario
    g = p.add_argument_group("Escenario de redistritaje")
    g.add_argument("--scenario", default=None,
                   choices=list(SCENARIOS.keys()),
                   help="Escenario predefinido: legal | apc_free | apc_soft")
    g.add_argument("--scenario-file", default=None,
                   help="Ruta a archivo YAML de escenario personalizado")
    g.add_argument("--decision-unit", default=None,
                   choices=["CUT", "ID_DIST"],
                   help="Unidad mínima de decisión (override manual)")
    g.add_argument("--preserve-mode", default=None,
                   choices=["hard", "soft", "none"],
                   help="Modo de preservación (override manual)")
    g.add_argument("--preserve-units", default=None,
                   help="Columnas a preservar, separadas por coma (ej. CUT)")
    g.add_argument("--split-penalty", type=float, default=None,
                   help="Peso de penalización en modo soft (default: 0.25)")

    # Fuente de población
    pg = p.add_argument_group("Fuente de población")
    pg.add_argument("--pop-source", default="viviendas",
                    choices=["viviendas", "censo2024", "manzana", "padron"],
                    help="Fuente de datos de población. "
                         "'viviendas' (default): conteo APC Manzana. "
                         "'manzana': n_per exacto por distrito desde Base_manzana_entidad_CPV24.csv "
                         "(requiere --census-path). "
                         "'censo2024': personas Censo 2024 distribuidas por comuna "
                         "(requiere --census-path con tabla comunal). "
                         "'padron': inscritos SERVEL (requiere --padron-path).")
    pg.add_argument("--census-path", default=None,
                    help="Ruta al CSV del Censo 2024: "
                         "Base_manzana_entidad_CPV24.csv (para --pop-source manzana) o "
                         "tabla comunal (para --pop-source censo2024).")
    pg.add_argument("--padron-path", default=None,
                    help="Ruta al CSV/Excel del padrón SERVEL "
                         "(solo con --pop-source padron).")

    return p.parse_args()


def parse_regiones(regiones_str: str) -> list[int]:
    if regiones_str.strip().lower() == "todas":
        return list(range(1, 17))
    return [int(r.strip()) for r in regiones_str.split(",")]


def enrich_population(
    distritos,
    pop_source: str,
    census_path: str | None = None,
    padron_path: str | None = None,
) -> tuple:
    """
    Enriquece el GDF de distritos APC con la fuente de población elegida.

    Returns
    -------
    (gdf_enriched, pop_col_name)
    """
    if pop_source == "viviendas":
        return distritos, "viviendas"

    if pop_source == "manzana":
        if not census_path:
            print("  ⚠ --pop-source manzana requiere --census-path con "
                  "Base_manzana_entidad_CPV24.csv. Usando viviendas como fallback.")
            return distritos, "viviendas"
        from chiledist.data import census2024 as c24
        try:
            mz  = c24.load_manzana_censo2024(census_path)
            gdf = c24.join_manzana_to_apc(distritos, mz)
            return gdf, "personas"
        except Exception as e:
            print(f"  ⚠ Error al cargar Base manzana Censo 2024: {e}. "
                  "Usando viviendas como fallback.")
            return distritos, "viviendas"

    if pop_source == "censo2024":
        if not census_path:
            print("  ⚠ --pop-source censo2024 requiere --census-path. "
                  "Usando viviendas como fallback.")
            return distritos, "viviendas"
        from chiledist.data import census2024 as c24
        try:
            census = c24.load_census2024(census_path)
            gdf = c24.join_census_multilevel(
                distritos, census, proxy_col="viviendas"
            )
            return gdf, "personas"
        except Exception as e:
            print(f"  ⚠ Error al cargar Censo 2024: {e}. "
                  "Usando viviendas como fallback.")
            return distritos, "viviendas"

    if pop_source == "padron":
        if not padron_path:
            print("  ⚠ --pop-source padron requiere --padron-path. "
                  "Usando viviendas como fallback.")
            return distritos, "viviendas"
        from chiledist.data import servel as sv
        try:
            padron = sv.load_padron_electoral(padron_path)
            gdf    = sv.join_padron_to_apc(
                distritos, padron, proxy_col="viviendas"
            )
            return gdf, "inscritos"
        except Exception as e:
            print(f"  ⚠ Error al cargar padrón SERVEL: {e}. "
                  "Usando viviendas como fallback.")
            return distritos, "viviendas"

    return distritos, "viviendas"


def build_scenario(args) -> ScenarioConfig:
    """Construye ScenarioConfig desde los argumentos CLI."""
    # Prioridad: scenario-file > --scenario > overrides manuales > default
    if args.scenario_file:
        cfg = load_scenario(args.scenario_file)
    elif args.scenario:
        cfg = SCENARIOS[args.scenario]
        # Crear copia mutable
        import dataclasses
        cfg = dataclasses.replace(cfg)
    else:
        cfg = ScenarioConfig(
            name="apc_libre_default",
            description="Modo APC libre (default, equivalente a v1)",
            decision_unit="ID_DIST",
            preserve_units=[],
            preserve_mode="none",
        )

    # Overrides manuales
    import dataclasses
    changes = {}
    if args.decision_unit:
        changes["decision_unit"] = args.decision_unit
    if args.preserve_mode:
        changes["preserve_mode"] = args.preserve_mode
        if args.preserve_mode == "hard" and not cfg.preserve_units:
            changes["preserve_units"] = ["CUT"]
    if args.preserve_units:
        changes["preserve_units"] = [u.strip()
                                      for u in args.preserve_units.split(",")]
    if args.split_penalty is not None:
        changes["split_penalty"] = args.split_penalty
    if args.n_distritos:
        changes["n_districts"] = args.n_distritos
    if args.pop_tol:
        changes["pop_tolerance"] = args.pop_tol
    if args.n_steps:
        changes["n_steps"] = args.n_steps
    if args.seed:
        changes["seed"] = args.seed

    if changes:
        cfg = dataclasses.replace(cfg, **changes)

    return cfg


# ──────────────────────────────────────────────────────────────────────────────
# Análisis por región
# ──────────────────────────────────────────────────────────────────────────────

def analizar_region(
    region_code: int,
    base_dir: str,
    output_base: str,
    n_distritos: int,
    pop_tol: float,
    n_steps: int,
    seed: int,
    skip_viz: bool,
    scenario: ScenarioConfig = None,
    pop_source: str = "viviendas",
    census_path: str | None = None,
    padron_path: str | None = None,
) -> dict:
    """Ejecuta el análisis completo de redistritaje para una región."""

    if scenario is None:
        scenario = ScenarioConfig(
            name="apc_libre_default",
            decision_unit="ID_DIST",
            preserve_units=[],
            preserve_mode="none",
        )

    # Sincronizar parámetros desde args si no vienen del escenario
    import dataclasses
    scenario = dataclasses.replace(
        scenario,
        n_districts=n_distritos,
        pop_tolerance=pop_tol,
        n_steps=n_steps,
        seed=seed,
    )

    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    # Subcarpeta por escenario dentro de redistritaje/
    out_dir = os.path.join(
        output_base, region_name, "redistritaje", scenario.name
    )
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"  Región {region_code:02d} — {region_name}")
    print(f"  Escenario: {scenario.name}")
    print(f"  Output: {out_dir}")
    print(f"{'#'*60}")
    print(scenario.summary())

    # ── Cargar datos APC ──────────────────────────────────────────────────────
    try:
        distritos = cd.load_layer("distrital", base_dir=base_dir,
                                   regions=[region_code])
        mz_urb    = cd.load_layer("manzana_urbana", base_dir=base_dir,
                                   regions=[region_code])
        mz_ald    = cd.load_layer("manzana_aldea",  base_dir=base_dir,
                                   regions=[region_code])
    except FileNotFoundError as e:
        print(f"  ⚠ {e}")
        return {"region": region_code, "status": "error", "error": str(e)}

    # Agregar población desde manzanas
    pop_urb = cd.aggregate_population(mz_urb, level="distrito", source="urbana")
    pop_ald = cd.aggregate_population(mz_ald, level="distrito", source="aldea")
    pop = (
        pop_urb.merge(pop_ald, on=["CUT", "COD_DISTRITO"],
                      how="outer", suffixes=("_urb", "_ald"))
        .fillna(0)
    )
    pop["viviendas"] = pop.get("viviendas_urb", 0) + pop.get("viviendas_ald", 0)
    distritos = distritos.merge(
        pop[["CUT", "COD_DISTRITO", "viviendas"]],
        on=["CUT", "COD_DISTRITO"], how="left"
    ).fillna({"viviendas": 0})
    distritos["viviendas"] = distritos["viviendas"].astype(int)

    # ── Enriquecer con fuente de población alternativa ────────────────────────
    if pop_source != "viviendas":
        print(f"\n  Enriqueciendo población: fuente='{pop_source}'...")
    distritos, _resolved_pop_col = enrich_population(
        distritos, pop_source, census_path, padron_path
    )

    # Respetar pop_col del escenario si ya está definido y existe en el GDF;
    # de lo contrario usar el resuelto por pop_source.
    import dataclasses
    if scenario.pop_col != "viviendas" and scenario.pop_col in distritos.columns:
        pass  # el escenario ya tenía pop_col correcto
    elif _resolved_pop_col != "viviendas":
        scenario = dataclasses.replace(scenario, pop_col=_resolved_pop_col)

    pop_col       = scenario.pop_col
    decision_unit = scenario.decision_unit

    # ── Preparar GDF según unidad de decisión ────────────────────────────────
    if decision_unit == "CUT":
        print("\n  Contrayendo APC → comunas (modo legal)...")
        agg_spec = {pop_col: "sum"}
        if pop_col != "viviendas":
            agg_spec["viviendas"] = "sum"
        gdf_dec = cd.contract_to_decision_units(
            distritos, decision_unit="CUT",
            agg_spec=agg_spec,
        )
        id_col = "CUT"
    else:
        gdf_dec   = distritos.copy()
        id_col    = "ID_DIST"

    n_units    = len(gdf_dec)
    total_viv  = gdf_dec[pop_col].sum() if pop_col in gdf_dec.columns else 0
    n_comunas  = gdf_dec["CUT"].nunique() if "CUT" in gdf_dec.columns else 0

    if total_viv == 0:
        print("  ⚠ Sin datos de población — saltando redistritaje")
        return {"region": region_code, "status": "sin_poblacion",
                "scenario": scenario.name}

    # Ajustar n_distritos para unidades pequeñas
    n_distritos_max = max(2, n_units // 4)
    n_distritos_eff = n_distritos
    if n_distritos_eff > n_distritos_max:
        print(f"  ⚠ n_distritos ajustado: {n_distritos_eff} → {n_distritos_max} "
              f"({n_units} unidades de decisión)")
        n_distritos_eff = n_distritos_max

    ideal_pop = total_viv / n_distritos_eff

    print(f"\n  Unidades dec.  : {n_units} ({id_col})")
    if id_col == "ID_DIST":
        print(f"  Comunas (CUT)  : {n_comunas}")
    print(f"  Viviendas      : {total_viv:,}")
    print(f"  Ideal/distrito : {ideal_pop:,.0f}")
    print(f"  N grupos       : {n_distritos_eff}")

    # ── Grafo gerrychain ──────────────────────────────────────────────────────
    try:
        import gerrychain as gc
        from gerrychain.proposals   import recom
        from gerrychain.constraints import contiguous
        from gerrychain.tree        import recursive_tree_part
        try:
            from gerrychain.accept import always_accept
        except ImportError:
            always_accept = gc.accept.always_accept
    except ImportError:
        print("  ⚠ gerrychain no instalado — omitiendo redistritaje")
        return {"region": region_code, "status": "sin_gerrychain",
                "scenario": scenario.name}

    np.random.seed(seed)

    gdf_gc = gdf_dec.reset_index(drop=True).to_crs("EPSG:32719")

    # Columnas a añadir al grafo
    cols_gc = [id_col, pop_col]
    if "CUT" in gdf_gc.columns and "CUT" not in cols_gc:
        cols_gc.append("CUT")
    for c in ["N_COMUNA", "TIPO_DISTRITO", "N_REGION"]:
        if c in gdf_gc.columns:
            cols_gc.append(c)

    graph = gc.Graph.from_geodataframe(
        gdf_gc, adjacency="queen",
        cols_to_add=[c for c in cols_gc if c in gdf_gc.columns],
    )

    # Conectar islas y componentes en el grafo gerrychain
    centroids = {}
    for n in graph.nodes():
        geom = gdf_gc.iloc[n].geometry
        centroids[n] = (geom.centroid.x, geom.centroid.y)

    islands_gc = [n for n in graph.nodes() if graph.degree(n) == 0]
    if islands_gc:
        print(f"  Conectando {len(islands_gc)} isla(s) en grafo gerrychain...")
        non_islands = [n for n in graph.nodes() if graph.degree(n) > 0]
        if non_islands:
            for island in islands_gc:
                ix, iy = centroids[island]
                nearest = min(non_islands,
                              key=lambda n: (centroids[n][0]-ix)**2
                                            + (centroids[n][1]-iy)**2)
                graph.add_edge(island, nearest)

    if not nx.is_connected(graph):
        n_comp = nx.number_connected_components(graph)
        print(f"  Conectando {n_comp} componentes desconectados...")
        components = list(nx.connected_components(graph))
        for i in range(1, len(components)):
            comp0  = list(components[0])[:50]
            comp_i = list(components[i])[:50]
            best_d, best_u, best_v = float("inf"), None, None
            for u in comp0:
                ux, uy = centroids[u]
                for v in comp_i:
                    vx, vy = centroids[v]
                    d = (ux-vx)**2 + (uy-vy)**2
                    if d < best_d:
                        best_d, best_u, best_v = d, u, v
            if best_u is not None:
                graph.add_edge(best_u, best_v)
            components[0] = components[0] | components[i]

    if nx.is_connected(graph):
        print(f"  ✓ Grafo conexo ({graph.number_of_nodes()} nodos · "
              f"{graph.number_of_edges()} aristas)")
    else:
        print(f"  ⚠ Grafo aún no conexo — algunos pasos pueden fallar")

    # ── Partición inicial ─────────────────────────────────────────────────────
    print(f"\n  Buscando partición inicial...")
    best_assignment = None
    best_dev        = float("inf")
    best_tol        = None

    node_repeats = (40 if n_units < 60  else
                    30 if n_units < 100 else
                    20 if n_units < 200 else 10)

    for tol_init in [0.25, 0.35, 0.45, 0.60, 0.80]:
        for seed_try in range(5):
            try:
                np.random.seed(seed + seed_try)
                candidate = recursive_tree_part(
                    graph, parts=range(n_distritos_eff),
                    pop_target=ideal_pop, pop_col=pop_col,
                    epsilon=tol_init,
                    node_repeats=node_repeats,
                )
                pop_by_part = {}
                for node, part in candidate.items():
                    pop_by_part[part] = (pop_by_part.get(part, 0)
                                         + graph.nodes[node].get(pop_col, 0))
                dev = max(abs(p - ideal_pop)/ideal_pop
                          for p in pop_by_part.values()) * 100
                if dev < best_dev:
                    best_dev        = dev
                    best_assignment = candidate
                    best_tol        = tol_init
                if dev < 15:
                    break
            except Exception:
                continue
        if best_dev < 15:
            break

    if best_assignment is None:
        print("  ⚠ No se encontró partición inicial válida")
        return {"region": region_code, "status": "sin_particion",
                "scenario": scenario.name}

    print(f"  Partición inicial: tol=±{best_tol*100:.0f}%, desv={best_dev:.1f}%")

    # ── Updaters (con soporte de CountSplits si preserve_mode=hard) ───────────
    updaters = cd.build_updaters_for_scenario(scenario, gdf_gc, pop_col=pop_col)

    partition = gc.Partition(
        graph=graph, assignment=best_assignment, updaters=updaters,
    )

    # ── Warm-up (solo contigüidad) ────────────────────────────────────────────
    epsilon_warmup = max(best_dev / 100 + 0.05, pop_tol)
    N_WARMUP       = min(500, n_steps // 4)

    recom_kwargs_warmup = dict(
        pop_col=pop_col, pop_target=ideal_pop,
        epsilon=epsilon_warmup, node_repeats=node_repeats,
    )

    try:
        import inspect
        if "pair_reselection" in inspect.signature(recom).parameters:
            recom_kwargs_warmup["pair_reselection"] = True
    except Exception:
        pass

    recom_warmup = partial(recom, **recom_kwargs_warmup)
    chain_warmup = gc.MarkovChain(
        proposal=recom_warmup, constraints=[contiguous],
        accept=always_accept, initial_state=partition,
        total_steps=N_WARMUP,
    )

    warmed_state = partition
    try:
        for step_w, state_w in enumerate(chain_warmup):
            warmed_state = state_w
            pop_w = list(state_w["population"].values())
            dev_w = max(abs(p - ideal_pop)/ideal_pop for p in pop_w) * 100
            if dev_w <= pop_tol * 100 * 1.5:
                print(f"  Warm-up convergió en paso {step_w} (desv={dev_w:.1f}%)")
                break
    except (IndexError, RuntimeError) as e:
        print(f"  ⚠ Warmup interrumpido ({e.__class__.__name__}) — "
              f"usando partición inicial")
        warmed_state = partition

    dev_warmed = max(
        abs(p - ideal_pop)/ideal_pop
        for p in warmed_state["population"].values()
    ) * 100

    # ── Cadena principal ──────────────────────────────────────────────────────
    # epsilon_recom se define AQUÍ, post-warmup, con la desviación real
    epsilon_recom = max(dev_warmed / 100 + 0.02, pop_tol)

    recom_kwargs_main = dict(
        pop_col=pop_col, pop_target=ideal_pop,
        epsilon=epsilon_recom, node_repeats=node_repeats,
    )
    try:
        import inspect
        if "pair_reselection" in inspect.signature(recom).parameters:
            recom_kwargs_main["pair_reselection"] = True
            print("  ✓ pair_reselection habilitado")
    except Exception:
        pass

    # Restricciones de la cadena principal según escenario
    constraints_main = cd.build_constraints_for_scenario(
        scenario, warmed_state, gdf_gc, epsilon_recom
    )

    recom_proposal = partial(recom, **recom_kwargs_main)
    chain = gc.MarkovChain(
        proposal=recom_proposal,
        constraints=constraints_main,
        accept=always_accept,
        initial_state=warmed_state,
        total_steps=n_steps,
    )

    print(f"\n  Iniciando ReCom: {n_steps:,} pasos · "
          f"{n_distritos_eff} distritos · ±{pop_tol*100:.0f}% · "
          f"preserve={scenario.preserve_mode}...")

    planes      = []
    metricas_mc = []
    try:
        for step, state in enumerate(chain):
            planes.append(dict(state.assignment))
            pop_vals = list(state["population"].values())
            max_dev  = max(abs(p - ideal_pop)/ideal_pop for p in pop_vals) * 100
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
            return {"region": region_code, "status": "sin_planes",
                    "scenario": scenario.name, "error": str(e)}
        print(f"  Continuando con {len(planes)} planes generados")

    # Filtrar planes válidos
    planes_validos = [p for p, m in zip(planes, metricas_mc)
                      if m["max_dev_pct"] <= pop_tol * 100]
    if not planes_validos:
        for tol_f in [pop_tol*1.5, pop_tol*2, 1.0]:
            planes_validos = [p for p, m in zip(planes, metricas_mc)
                              if m["max_dev_pct"] <= tol_f * 100]
            if planes_validos:
                print(f"  Usando tolerancia ±{tol_f*100:.0f}%: "
                      f"{len(planes_validos)} planes")
                break
    if not planes_validos:
        planes_validos = planes

    n_generados = len(metricas_mc)
    print(f"  Planes válidos: {len(planes_validos)}/{n_generados}")
    planes = planes_validos

    if not planes:
        return {"region": region_code, "status": "sin_planes_validos",
                "scenario": scenario.name, "n_generados": n_generados}

    # ── Reconstruir asignaciones con IDs de cadena ────────────────────────────
    ids_ordenados = gdf_dec[id_col].tolist()

    def reconstruir_asignacion(plan_dict, graph, ids_list):
        result = {}
        for node, distrito in plan_dict.items():
            id_val = graph.nodes[node].get(id_col)
            if id_val is None and isinstance(node, int) and node < len(ids_list):
                id_val = ids_list[node]
            if id_val is not None:
                result[id_val] = distrito
        return result

    # ── Métricas del ensemble ─────────────────────────────────────────────────
    df_ensemble = pd.DataFrame([
        {"plan_id": i, "max_dev_pob_pct": round(float(m["max_dev_pct"]), 3),
         "pp_promedio": np.nan, "cut_edges": int(m["cut_edges"])}
        for i, m in enumerate(metricas_mc[:len(planes)])
    ])

    # Polsby-Popper para muestra de 30 planes
    gdf_m = gdf_dec.to_crs("EPSG:32719")
    for idx in df_ensemble.sample(min(30, len(df_ensemble)),
                                   random_state=seed).index:
        plan_id = int(df_ensemble.loc[idx, "plan_id"])
        a_m = reconstruir_asignacion(planes[plan_id], graph, ids_ordenados)
        gdf_m["__d__"] = gdf_m[id_col].map(a_m)
        df_p = gdf_m[gdf_m["__d__"].notna()]
        if df_p.empty:
            continue
        try:
            dissolved = df_p.dissolve("__d__")
            pp_mean   = float(
                (4 * np.pi * dissolved.geometry.area
                 / dissolved.geometry.length ** 2).dropna().mean()
            )
            df_ensemble.loc[idx, "pp_promedio"] = (
                round(pp_mean, 4) if np.isfinite(pp_mean) else np.nan
            )
        except Exception:
            pass

    # Métricas de comunas partidas (solo modos APC)
    if id_col == "ID_DIST" and "CUT" in gdf_dec.columns:
        print("  Calculando métricas de comunas partidas...")
        split_sample_size = min(50, len(planes))
        split_indices = np.linspace(0, len(planes)-1,
                                     split_sample_size, dtype=int)
        n_splits_list  = []
        severity_list  = []
        for si in split_indices:
            a_s = reconstruir_asignacion(planes[si], graph, ids_ordenados)
            sm  = cd.plan_split_metrics(
                a_s, gdf_dec, unit_col="CUT", id_col="ID_DIST",
                pop_col=pop_col,
            )
            n_splits_list.append(sm["n_comunas_partidas"])
            severity_list.append(sm["split_severity"])

        # Asignar al ensemble con interpolación simple
        df_ensemble["n_comunas_partidas"] = np.nan
        df_ensemble["split_severity"]     = np.nan
        for ii, si in enumerate(split_indices):
            df_ensemble.loc[si, "n_comunas_partidas"] = n_splits_list[ii]
            df_ensemble.loc[si, "split_severity"]     = round(severity_list[ii], 4)

        print(f"  Comunas partidas (mediana): "
              f"{np.nanmedian(n_splits_list):.1f} / "
              f"{gdf_dec['CUT'].nunique()}")
    else:
        df_ensemble["n_comunas_partidas"] = 0
        df_ensemble["split_severity"]     = 0.0

    # ── Plan de referencia: seleccionado por score heurístico para visualización ─
    # NOTA: en MCMC redistributing el resultado estadístico ES la distribución
    # del ensemble completo (ensemble_stats.csv). Este plan es solo un representante
    # conveniente para visualización — no es el plan "correcto" ni el "óptimo".
    # Score: -dev_norm + pp_norm - cut_norm  (menor desviación, mayor compacidad,
    #        menos cortes); con penalización de splits en modo soft.
    dev_norm = df_ensemble["max_dev_pob_pct"] / (
        df_ensemble["max_dev_pob_pct"].max() + 1e-10
    )
    cut_norm = df_ensemble["cut_edges"] / (
        df_ensemble["cut_edges"].max() + 1e-10
    )
    pp_col   = df_ensemble["pp_promedio"].fillna(
        df_ensemble["pp_promedio"].median()
    )
    pp_range = pp_col.max() - pp_col.min() + 1e-10
    pp_norm  = (pp_col - pp_col.min()) / pp_range
    base_score = -dev_norm + pp_norm.fillna(0) - cut_norm

    if (scenario.preserve_mode == "soft"
            and scenario.split_penalty > 0
            and "split_severity" in df_ensemble.columns):
        sev = df_ensemble["split_severity"].fillna(
            df_ensemble["split_severity"].median()
        ).fillna(0)
        sev_norm = sev / (sev.max() + 1e-10)
        df_ensemble["score"] = base_score - scenario.split_penalty * sev_norm
    else:
        df_ensemble["score"] = base_score

    ref_idx     = int(df_ensemble["score"].idxmax())
    ref_plan_id = int(df_ensemble.loc[ref_idx, "plan_id"])
    ext_idx     = int(df_ensemble["score"].idxmin())
    ext_plan_id = int(df_ensemble.loc[ext_idx, "plan_id"])

    ref_plan        = planes[ref_plan_id]
    ext_plan        = planes[ext_plan_id]
    ref_plan_mapped = reconstruir_asignacion(ref_plan, graph, ids_ordenados)
    ext_plan_mapped = reconstruir_asignacion(ext_plan, graph, ids_ordenados)

    print(f"\n  Plan de referencia (id={ref_plan_id}, mayor score heurístico): "
          f"desv={df_ensemble.loc[ref_idx,'max_dev_pob_pct']:.2f}%, "
          f"cortes={df_ensemble.loc[ref_idx,'cut_edges']}")

    # Resumen detallado del plan de referencia
    gdf_dec["__d__"] = gdf_dec[id_col].map(ref_plan_mapped)
    agg_cols_resumen = {pop_col: "sum", id_col: "count"}
    if "CUT" in gdf_dec.columns and id_col != "CUT":
        agg_cols_resumen["CUT"] = "nunique"

    pop_summary = (
        gdf_dec[gdf_dec["__d__"].notna()]
        .groupby("__d__")
        .agg({pop_col: "sum", id_col: "count",
              **({} if id_col == "CUT" else
                 ({"CUT": "nunique"} if "CUT" in gdf_dec.columns else {}))})
        .reset_index()
    )
    pop_summary["desv_pct"] = (
        (pop_summary[pop_col] - ideal_pop) / ideal_pop * 100
    ).round(2)

    if id_col == "ID_DIST":
        col_names = ["Distrito", "Viviendas", "N_APC", "N_Comunas", "Desv_%"]
        if "CUT" not in gdf_dec.columns:
            col_names = ["Distrito", "Viviendas", "N_APC", "Desv_%"]
    else:
        col_names = ["Distrito", "Viviendas", "N_Comunas", "Desv_%"]

    try:
        pop_summary.columns = col_names
    except ValueError:
        pass

    print(f"\n  Detalle del plan de referencia (id={ref_plan_id}):")
    print(pop_summary.to_string(index=False))

    # ── Métricas de comunas partidas del plan de referencia ───────────────────
    if id_col == "ID_DIST" and "CUT" in gdf_dec.columns:
        split_summary = cd.split_unit_summary(
            ref_plan_mapped, gdf_dec,
            unit_col="CUT", id_col="ID_DIST", pop_col=pop_col,
        )
        if not split_summary.empty:
            print(f"\n  Comunas partidas en plan de referencia: {len(split_summary)}")
            print(split_summary[["CUT","nombre","n_fragmentos",
                                  "pop_total","split_severity"]]
                  .head(10).to_string(index=False))
        split_summary.to_csv(
            os.path.join(out_dir, "comunas_partidas.csv"), index=False
        )

    # ── Guardar CSVs ──────────────────────────────────────────────────────────
    df_mc = pd.DataFrame(metricas_mc)
    df_mc.to_csv(os.path.join(out_dir, "metricas_cadena.csv"), index=False)
    df_ensemble.to_csv(os.path.join(out_dir, "ensemble_stats.csv"), index=False)
    pop_summary.to_csv(os.path.join(out_dir, "plan_referencia_detalle.csv"),
                       index=False)

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not skip_viz:
        BG    = "#F8F7F4"
        pal_n = [plt.cm.Set2.colors[i % 8] for i in range(n_distritos_eff)]

        def plot_single_plan(gdf_plot, assignment, title, ax):
            gdf_plot = gdf_plot.copy().to_crs("EPSG:32719")
            gdf_plot["__d__"] = gdf_plot[id_col].map(assignment)
            gdf_plot = gdf_plot[gdf_plot["__d__"].notna()]
            if gdf_plot.empty:
                ax.text(0.5, 0.5, "sin datos", ha="center", va="center",
                        transform=ax.transAxes)
                ax.axis("off")
                return
            districts = sorted(gdf_plot["__d__"].unique())
            cmap = {d: pal_n[i % len(pal_n)] for i, d in enumerate(districts)}
            for d in districts:
                gdf_plot[gdf_plot["__d__"] == d].plot(
                    ax=ax, color=cmap[d], edgecolor="#CCCCCC", linewidth=0.1
                )
            try:
                gdf_plot.dissolve("__d__").boundary.plot(
                    ax=ax, color="#333333", linewidth=0.8
                )
            except Exception:
                pass
            ax.set_title(title, fontsize=9, fontweight="bold", color="#1a1a18")
            ax.axis("off")

        # Figura 1: plan de referencia vs plan extremo
        fig1, axes = plt.subplots(1, 2, figsize=(16, 10))
        fig1.patch.set_facecolor(BG)
        for ax in axes:
            ax.set_facecolor(BG)
        plot_single_plan(
            gdf_dec, ref_plan_mapped,
            f"Referencia (id={ref_plan_id}) "
            f"desv={df_ensemble.loc[ref_idx,'max_dev_pob_pct']:.1f}%",
            axes[0]
        )
        plot_single_plan(
            gdf_dec, ext_plan_mapped,
            f"Extremo (id={ext_plan_id}) "
            f"desv={df_ensemble.loc[ext_idx,'max_dev_pob_pct']:.1f}%",
            axes[1]
        )
        fig1.suptitle(
            f"{region_name} [{scenario.name}] — ReCom  "
            f"({n_distritos_eff} distritos · {n_steps:,} pasos · "
            f"±{pop_tol*100:.0f}%)",
            fontsize=11, fontweight="bold"
        )
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "ref_vs_extremo.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 2: cadena de Markov
        fig2, axes = plt.subplots(1, 2, figsize=(16, 5))
        fig2.patch.set_facecolor(BG)
        for ax in axes:
            ax.set_facecolor(BG)
            ax.spines[["top", "right"]].set_visible(False)
        axes[0].plot(df_mc["step"], df_mc["cut_edges"],
                     color="#1D9E75", linewidth=0.8, alpha=0.8)
        axes[0].set_xlabel("Paso"); axes[0].set_ylabel("Aristas cortadas")
        axes[0].set_title("Evolución — aristas cortadas", fontweight="bold")
        axes[1].plot(df_mc["step"], df_mc["max_dev_pct"],
                     color="#D85A30", linewidth=0.8, alpha=0.8)
        axes[1].axhline(pop_tol*100, color="#BA7517", linestyle="--",
                        linewidth=1, label=f"Límite ±{pop_tol*100:.0f}%")
        axes[1].set_xlabel("Paso"); axes[1].set_ylabel("Desv. pob. máx (%)")
        axes[1].set_title("Evolución — balance poblacional", fontweight="bold")
        axes[1].legend(fontsize=9)
        fig2.suptitle(f"Cadena de Markov ReCom — {region_name} [{scenario.name}]",
                      fontsize=11, fontweight="bold")
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "cadena_markov.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 3: distribución ensemble
        n_cols = 4 if id_col == "ID_DIST" else 3
        cols_ens = ["pp_promedio", "max_dev_pob_pct", "cut_edges"]
        labels_ens = ["Polsby-Popper", "Desv. pob. máx (%)", "Aristas cortadas"]
        colors_ens = ["#1D9E75", "#D85A30", "#BA7517"]
        if id_col == "ID_DIST" and "n_comunas_partidas" in df_ensemble.columns:
            cols_ens.append("n_comunas_partidas")
            labels_ens.append("Comunas partidas")
            colors_ens.append("#6A3D9A")

        fig3, axes = plt.subplots(1, len(cols_ens), figsize=(5*len(cols_ens), 5))
        if len(cols_ens) == 1:
            axes = [axes]
        fig3.patch.set_facecolor(BG)
        for ax, col, color, label in zip(axes, cols_ens, colors_ens, labels_ens):
            ax.set_facecolor(BG)
            vals = df_ensemble[col].dropna()
            if vals.empty or vals.nunique() < 2:
                ax.text(0.5, 0.5, f"{label}\nno disponible",
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=10, color="#888880")
                ax.axis("off")
                continue
            ax.hist(vals, bins=min(20, len(vals)), color=color,
                    edgecolor="white", linewidth=0.5)
            ax.axvline(vals.mean(), color="#333333", linewidth=1.5,
                       linestyle="--", label=f"Media: {vals.mean():.3f}")
            ax.set_xlabel(label); ax.set_ylabel("Frecuencia")
            ax.legend(fontsize=8)
            ax.spines[["top", "right"]].set_visible(False)
        fig3.suptitle(
            f"Distribución ensemble — {region_name} [{scenario.name}] "
            f"({len(planes)} planes)",
            fontsize=11, fontweight="bold"
        )
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "ensemble_distribucion.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 4: balance poblacional del plan de referencia
        cd.plot_plan(
            gdf_dec, assignment=ref_plan_mapped,
            id_col=id_col, pop_col=pop_col,
            title=f"{region_name} [{scenario.name}] — Plan de referencia (id={ref_plan_id})",
            show_pop_balance=True,
            save_path=os.path.join(out_dir, "ref_balance.png"),
        )
        plt.close("all")

        # Figura 5: compacidad
        metricas_dist = cd.all_compactness(gdf_dec, id_col=id_col)
        cd.plot_compactness(
            gdf_dec, metricas_dist, id_col=id_col,
            metric="polsby_popper",
            title=f"{region_name} [{scenario.name}] — Compacidad",
            save_path=os.path.join(out_dir, "compacidad.png"),
        )
        plt.close("all")

        print(f"\n  Figuras guardadas en {out_dir}/")

    # ── Resumen final ─────────────────────────────────────────────────────────
    n_split_ref = int(df_ensemble.loc[ref_idx, "n_comunas_partidas"]) \
        if not pd.isna(df_ensemble.loc[ref_idx, "n_comunas_partidas"]) else 0

    return {
        "region":         region_code,
        "region_name":    region_name,
        "scenario":       scenario.name,
        "decision_unit":  scenario.decision_unit,
        "preserve_mode":  scenario.preserve_mode,
        "status":         "ok",
        "n_unidades":     n_units,
        "n_planes":       len(planes),
        "ref_plan_id":    ref_plan_id,
        "ref_desv":       df_ensemble.loc[ref_idx, "max_dev_pob_pct"],
        "comunas_partidas_ref": n_split_ref,
        "out_dir":        out_dir,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args        = parse_args()
    base_dir    = args.base_dir
    output_base = args.output_dir or os.path.join(base_dir, "datos")
    regiones    = parse_regiones(args.regiones)
    scenario    = build_scenario(args)

    # pop_tol: --pop-tol explícito tiene precedencia; si no se pasa, se toma del
    # escenario (scenario.pop_tolerance, default 0.05). El CLI acepta None para
    # que el escenario sea la fuente de verdad y los resultados sean reproducibles.
    pop_tol = args.pop_tol if args.pop_tol is not None else scenario.pop_tolerance

    print(f"\nchiledist — Redistritaje")
    print(f"  base_dir    : {base_dir}")
    print(f"  output_base : {output_base}")
    print(f"  regiones    : {regiones}")
    print(f"  escenario   : {scenario.name}")
    print(f"  n_distritos : {args.n_distritos}")
    print(f"  pop_tol     : ±{pop_tol*100:.0f}%"
          f"{'  (--pop-tol explícito)' if args.pop_tol is not None else '  (desde escenario)'}")
    print(f"  n_steps     : {args.n_steps:,}")
    print(f"  pop_source  : {args.pop_source}")

    resultados = []
    for r in regiones:
        try:
            res = analizar_region(
                region_code=r,
                base_dir=base_dir,
                output_base=output_base,
                n_distritos=args.n_distritos,
                pop_tol=pop_tol,
                n_steps=args.n_steps,
                seed=args.seed,
                skip_viz=args.skip_viz,
                scenario=scenario,
                pop_source=args.pop_source,
                census_path=getattr(args, "census_path", None),
                padron_path=getattr(args, "padron_path", None),
            )
            resultados.append(res)
        except Exception as e:
            import traceback
            print(f"\n  ⚠ Error en región {r}: {e}")
            traceback.print_exc()
            resultados.append({
                "region": r, "scenario": scenario.name,
                "status": "error", "error": str(e),
            })

    # Resumen final
    print(f"\n{'='*60}")
    print(f"  RESUMEN FINAL — {scenario.name}")
    print(f"{'='*60}")
    df_res = pd.DataFrame(resultados)
    cols_resumen = ["region", "scenario", "status"]
    if "n_planes" in df_res.columns:
        cols_resumen += ["n_planes", "ref_desv"]
    if "comunas_partidas_ref" in df_res.columns:
        cols_resumen.append("comunas_partidas_ref")
    print(df_res[[c for c in cols_resumen if c in df_res.columns]]
          .to_string(index=False))

    resumen_path = os.path.join(
        output_base, f"redistritaje_resumen_{scenario.name}.csv"
    )
    df_res.to_csv(resumen_path, index=False)
    print(f"\nResumen guardado: {resumen_path}")


if __name__ == "__main__":
    main()
