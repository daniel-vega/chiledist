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
import dataclasses
import datetime
import os
import random
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
from chiledist.persistence import (
    new_run_id,
    sha256_file,
    build_run_manifest,
    save_run_manifest,
)
from chiledist.samplers.recom import run_recom_chain


# Reason estable/machine-readable para status="sin_particion": el preflight de
# factibilidad poblacional (cd.check_population_feasibility) ya pasó — es decir,
# no se demostró que el espacio de planes sea matemáticamente vacío — pero el
# algoritmo de inicialización (recursive_tree_part) agotó su escalera de
# tolerancias y semillas sin producir una partición. Distinto de
# infeasible_population (cd.REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND), que sí es
# una prueba matemática de inviabilidad.
REASON_INITIALIZATION_SEARCH_EXHAUSTED = "initialization_search_exhausted"

# Análogo a REASON_INITIALIZATION_SEARCH_EXHAUSTED, pero para la fase de
# warm-up: el warm-up (solo contigüidad, sin restricción poblacional) agotó
# su presupuesto de pasos (incluida la extensión) sin bajar la desviación
# poblacional a ±pop_tol. Sin esto, la cadena principal fijaría epsilon_recom
# por encima de pop_tol para "no bloquearse" — exactamente el modelo B
# (sampling amplio + filtrado posterior) que el modelo A busca evitar.
REASON_WARMUP_DID_NOT_CONVERGE = "warmup_did_not_reach_pop_tol"

# Escalera de tolerancias y reintentos de semilla para recursive_tree_part.
# Nombrados como constantes (mismos valores de siempre) únicamente para poder
# probar buscar_particion_inicial() de forma aislada — no cambia el algoritmo.
TOLERANCIA_INICIAL_ESCALERA = [0.25, 0.35, 0.45, 0.60, 0.80]
N_SEED_TRIES_INICIALIZACION = 5

# Etiqueta legible por magnitud de población, indexada por el pop_col YA
# RESUELTO (no por --pop-source): enrich_population() puede hacer fallback a
# "viviendas" si falta --census-path/--padron-path, y en ese caso la etiqueta
# debe seguir a la columna real, no al flag original. Cubre los 3 valores que
# enrich_population() puede devolver ("viviendas", "personas", "inscritos");
# cualquier otro pop_col (ej. un YAML custom) se muestra tal cual.
POP_LABELS = {
    "viviendas": "viviendas",
    "personas":  "personas",
    "inscritos": "inscritos",
}


def buscar_particion_inicial(
    graph, n_distritos_eff, pop_col, ideal_pop, node_repeats, seed,
    recursive_tree_part,
):
    """
    Prueba TOLERANCIA_INICIAL_ESCALERA con N_SEED_TRIES_INICIALIZACION
    semillas cada una, buscando una partición inicial balanceada
    (desviación < 15%) vía recursive_tree_part.

    Devuelve (best_assignment, best_dev, best_tol). best_assignment es
    None si la búsqueda se agota sin encontrar ninguna partición: eso es
    un fallo del algoritmo de búsqueda/inicialización (status
    "sin_particion"), NO una prueba de que el espacio de planes sea
    matemáticamente vacío — esa prueba, cuando existe, la produce antes
    y de forma determinista chiledist.check_population_feasibility
    (status "infeasible_population").
    """
    best_assignment = None
    best_dev        = float("inf")
    best_tol        = None

    for tol_init in TOLERANCIA_INICIAL_ESCALERA:
        for seed_try in range(N_SEED_TRIES_INICIALIZACION):
            try:
                np.random.seed(seed + seed_try)
                random.seed(seed + seed_try)
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

    return best_assignment, best_dev, best_tol


def diagnostico_busqueda_agotada() -> str:
    """
    Mensaje diagnóstico para status="sin_particion".

    Debe dejar explícito que se trata de un fallo del algoritmo de
    búsqueda/inicialización, y NO de una prueba de inviabilidad
    matemática (eso es status="infeasible_population", determinado
    antes por el preflight de factibilidad poblacional).
    """
    return (
        "Búsqueda de partición inicial agotada: se probaron todas las "
        f"tolerancias iniciales {TOLERANCIA_INICIAL_ESCALERA} con "
        f"{N_SEED_TRIES_INICIALIZACION} semillas cada una, sin producir una "
        "partición balanceada. Esto es un fallo del algoritmo de búsqueda/"
        "inicialización, NO una prueba de que el espacio de planes sea "
        "matemáticamente vacío — el preflight de factibilidad poblacional "
        "ya determinó que la tolerancia solicitada es alcanzable "
        "(ver status='infeasible_population' para ese otro caso)."
    )


def conectar_islas_y_componentes(graph, gdf_nodos) -> None:
    """
    Conecta islas (grado 0) al nodo más cercano y fusiona componentes
    desconectados por distancia de centroides. Modifica `graph` in-place.

    `gdf_nodos` debe estar en el mismo orden/índice que los nodos de
    `graph` (reset_index(drop=True) antes de construir el grafo con
    gc.Graph.from_geodataframe) — se usa solo para leer la geometría de
    cada nodo vía posición entera (`.iloc[n]`).
    """
    centroids = {}
    for n in graph.nodes():
        geom = gdf_nodos.iloc[n].geometry
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
    p.add_argument("--n-distritos", type=int, default=None,
                   help="Número de particiones territoriales a generar en la "
                        "simulación (NO la magnitud electoral / escaños por "
                        "distrito de la Ley 20.840 — ver "
                        "MAGNITUDES_LEGALES_LEY20840). Default: usa "
                        "n_districts del escenario (ScenarioConfig.n_districts).")
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
    if args.n_distritos is not None:
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
    scenario = dataclasses.replace(
        scenario,
        n_districts=n_distritos,
        pop_tolerance=pop_tol,
        n_steps=n_steps,
        seed=seed,
    )

    # Identificador único de esta corrida
    run_id          = new_run_id()
    timestamp_start = datetime.datetime.now().isoformat(timespec="seconds")

    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    # Subcarpeta por escenario dentro de redistritaje/
    out_dir = os.path.join(
        output_base, region_name, "redistritaje", scenario.name
    )
    os.makedirs(out_dir, exist_ok=True)

    # Directorio de la corrida específica (timestamped + run_id prefix)
    ts_str  = timestamp_start.replace(":", "").replace("-", "").replace("T", "_")
    run_dir = os.path.join(out_dir, f"run_{ts_str}_{run_id[:8]}")
    os.makedirs(run_dir, exist_ok=True)
    run_dir_figuras = os.path.join(run_dir, "figuras")
    os.makedirs(run_dir_figuras, exist_ok=True)

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

    # Puntos_Edificacion_Rural: capa opcional, usada solo como fallback de
    # proxy para comunas sin ninguna manzana urbana ni de aldea (ver
    # apply_rural_proxy_fallback más abajo).
    try:
        puntos_rural = cd.load_layer("puntos_rural", base_dir=base_dir,
                                      regions=[region_code])
    except FileNotFoundError:
        puntos_rural = None

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
    # Fallback: comunas sin ninguna manzana urbana ni de aldea (proxy=0 tras
    # el merge+fillna de arriba — incluye comunas que no aparecían siquiera
    # en pop_urb/pop_ald) usan conteo de edificaciones rurales en su lugar.
    # Debe aplicarse aquí, DESPUÉS del merge contra distritos (no antes,
    # sobre pop): pop solo contiene combinaciones CUT+COD_DISTRITO con al
    # menos una manzana, así que una comuna sin ninguna manzana (ej. Lago
    # Verde, CUT 11102 — ver tests/test_integration_r11.py) no aparece ahí
    # en absoluto, ni siquiera como 0 — recién existe como 0 explícito tras
    # el .fillna({"viviendas": 0}) contra el universo completo de distritos.
    distritos = cd.apply_rural_proxy_fallback(distritos, puntos_rural)
    distritos["viviendas"] = distritos["viviendas"].astype(int)

    # ── Enriquecer con fuente de población alternativa ────────────────────────
    if pop_source != "viviendas":
        print(f"\n  Enriqueciendo población: fuente='{pop_source}'...")
    distritos, _resolved_pop_col = enrich_population(
        distritos, pop_source, census_path, padron_path
    )

    # Respetar pop_col del escenario si ya está definido y existe en el GDF;
    # de lo contrario usar el resuelto por pop_source.
    if scenario.pop_col != "viviendas" and scenario.pop_col in distritos.columns:
        pass  # el escenario ya tenía pop_col correcto
    elif _resolved_pop_col != "viviendas":
        scenario = dataclasses.replace(scenario, pop_col=_resolved_pop_col)

    pop_col       = scenario.pop_col
    # Etiqueta de salida para la magnitud de población (CLI/tablas). Derivada
    # de pop_col ya resuelto (no de --pop-source directamente) para que
    # coincida con la fuente REAL usada, incluido el fallback a "viviendas"
    # cuando --census-path/--padron-path no se pasan.
    pop_label     = POP_LABELS.get(pop_col, pop_col)
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

    # ── Preflight: factibilidad poblacional (con n_distritos ORIGINAL) ───────
    # Determinista, sin gerrychain: si una unidad de decisión indivisible por
    # sí sola excede pop_tol respecto del ideal, ningún recursive_tree_part
    # ni número de semillas puede producir un plan que cumpla la tolerancia.
    # Se evalúa ANTES del guard de n_distritos_max (más abajo): ese guard
    # sustituye n_distritos por una razón topológica (muy pocas unidades
    # para que ReCom encuentre cortes, ej. Arica 37 APC/Aysén 56 APC), no
    # porque el n_distritos pedido sea poblacionalmente inviable. Evaluar
    # la factibilidad ya con n_distritos sustituido respondería una
    # pregunta distinta a la que pidió el usuario.
    unit_pops = dict(zip(gdf_dec[id_col], gdf_dec[pop_col]))
    feasibility = cd.check_population_feasibility(
        unit_pops, n_distritos, pop_tol
    )
    if not feasibility.feasible:
        print(f"\n  ⚠ {feasibility.diagnostic_message()}")
        return {
            "region": region_code,
            "region_name": region_name,
            "scenario": scenario.name,
            "status": "infeasible_population",
            "reason": feasibility.reason,
            "total_population": feasibility.total_population,
            "n_districts": feasibility.n_districts,
            "ideal_population": feasibility.ideal_population,
            "largest_indivisible_unit": feasibility.largest_indivisible_unit,
            "largest_indivisible_unit_id": feasibility.largest_indivisible_unit_id,
            "minimum_required_tolerance": feasibility.minimum_required_tolerance,
            "requested_tolerance": feasibility.requested_tolerance,
        }

    # Ajustar n_distritos solo para regiones con muy pocas unidades de
    # decisión en términos ABSOLUTOS (topología de grafo: ReCom no puede
    # encontrar cortes balanceados con pocos nodos) — no relativo a
    # n_distritos. Para n_units >= 80 el usuario controla n_distritos
    # directamente; el preflight de arriba ya evaluó la factibilidad
    # poblacional sobre el n_distritos real pedido.
    n_distritos_max = max(2, n_units // 4)
    n_distritos_eff = n_distritos
    if n_units < 80 and n_distritos_eff > n_distritos_max:
        print(f"  ⚠ n_distritos ajustado: {n_distritos_eff} → {n_distritos_max} "
              f"({n_units} unidades de decisión)")
        n_distritos_eff = n_distritos_max

    ideal_pop = total_viv / n_distritos_eff

    print(f"\n  Unidades dec.  : {n_units} ({id_col})")
    if id_col == "ID_DIST":
        print(f"  Comunas (CUT)  : {n_comunas}")
    print(f"  {pop_label.capitalize():<15}: {total_viv:,}")
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
    random.seed(seed)

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
    conectar_islas_y_componentes(graph, gdf_gc)

    # ── Partición inicial ─────────────────────────────────────────────────────
    print(f"\n  Buscando partición inicial...")

    node_repeats = (40 if n_units < 60  else
                    30 if n_units < 100 else
                    20 if n_units < 200 else 10)

    # preserve_mode="hard" + CUT en preserve_units + decision_unit != CUT
    # (ej. apc_strict): recursive_tree_part sobre el grafo ID_DIST no tiene
    # ningún concepto de "no partir comunas" -- puede (y en la práctica
    # suele) repartir los ID_DIST de un mismo CUT en grupos distintos, lo
    # que la restricción preserve_CUT de gerrychain rechaza al arrancar la
    # cadena. Fix: construir la partición inicial en dos pasos -- (1)
    # recursive_tree_part sobre el grafo comunal contraído, para obtener
    # n_distritos_eff grupos de CUT; (2) expandir, cada ID_DIST hereda el
    # grupo de su CUT. Por construcción, ningún ID_DIST de un mismo CUT
    # puede terminar en grupos distintos.
    if (scenario.preserve_mode == "hard"
            and "CUT" in scenario.preserve_units
            and id_col != "CUT"):

        # Paso 1: grafo comunal contraído
        gdf_cut = cd.contract_to_decision_units(
            distritos, decision_unit="CUT",
            agg_spec={pop_col: "sum"},
        )
        graph_cut = gc.Graph.from_geodataframe(
            gdf_cut.reset_index(drop=True).to_crs("EPSG:32719"),
            adjacency="queen",
            cols_to_add=["CUT", pop_col],
        )
        conectar_islas_y_componentes(graph_cut, gdf_cut)

        # Paso 2: buscar partición sobre el grafo comunal (reusa la misma
        # función de búsqueda, solo con graph_cut en vez de graph)
        cut_assignment, best_dev, best_tol = buscar_particion_inicial(
            graph_cut, n_distritos_eff, pop_col, ideal_pop, node_repeats, seed,
            recursive_tree_part,
        )

        if cut_assignment is None:
            print(f"\n  ⚠ {diagnostico_busqueda_agotada()}")
            return {
                "region": region_code,
                "region_name": region_name,
                "scenario": scenario.name,
                "status": "sin_particion",
                "reason": REASON_INITIALIZATION_SEARCH_EXHAUSTED,
            }

        # Paso 3: expandir ID_DIST → grupo del CUT (atributo "CUT" ya
        # presente en ambos grafos vía cols_to_add)
        cut_index = {
            graph_cut.nodes[n]["CUT"]: cut_assignment[n]
            for n in graph_cut.nodes()
        }
        best_assignment = {
            node: cut_index[graph.nodes[node]["CUT"]]
            for node in graph.nodes()
        }
        print(f"  Partición inicial (vía CUT): tol=±{best_tol*100:.0f}%,"
              f" desv={best_dev:.1f}%")

    else:
        best_assignment, best_dev, best_tol = buscar_particion_inicial(
            graph, n_distritos_eff, pop_col, ideal_pop, node_repeats, seed,
            recursive_tree_part,
        )

    if best_assignment is None:
        print(f"\n  ⚠ {diagnostico_busqueda_agotada()}")
        return {
            "region": region_code,
            "region_name": region_name,
            "scenario": scenario.name,
            "status": "sin_particion",
            "reason": REASON_INITIALIZATION_SEARCH_EXHAUSTED,
        }

    print(f"  Partición inicial: tol=±{best_tol*100:.0f}%, desv={best_dev:.1f}%")

    # ── Updaters (con soporte de CountSplits si preserve_mode=hard) ───────────
    updaters = cd.build_updaters_for_scenario(scenario, gdf_gc, pop_col=pop_col)

    partition = gc.Partition(
        graph=graph, assignment=best_assignment, updaters=updaters,
    )

    # ── Warm-up (solo contigüidad) ────────────────────────────────────────────
    epsilon_warmup = max(best_dev / 100 + 0.05, pop_tol)
    # Presupuesto escalado por n_units: menos unidades (ej. legal, CUT) implica
    # recombinaciones más "grandes"/costosas de balancear por paso, así que
    # necesitan más pasos de warm-up que apc_free/apc_soft (ID_DIST, más
    # unidades y más finas).
    _warmup_base = 2000 if n_units <= 100 else (
                   1000 if n_units <= 200 else 500)
    N_WARMUP       = min(_warmup_base, n_steps // 4)

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

    if (scenario.preserve_mode == "hard"
            and "CUT" in scenario.preserve_units
            and id_col != "CUT"):
        # apc_strict: warm-up sobre el grafo comunal contraído (graph_cut,
        # ya construido arriba para la partición inicial), no sobre el
        # grafo ID_DIST. preserve_CUT es tautológico en graph_cut (cada
        # nodo ya es una comuna distinta), así que basta contiguous --
        # sin el problema de auto-loops por rechazo que tenía la versión
        # anterior (preserve_CUT añadido al grafo ID_DIST de 451 nodos).
        #
        # Epsilon calibrado a lo que 52 comunas pueden alcanzar (best_dev
        # de la partición inicial + 5pp, con floor de 20%), no a pop_tol:
        # en R13, Puente Alto solo es 61% del ideal por distrito, lo que
        # hace ±10% inalcanzable con piezas del tamaño de una comuna. La
        # cadena principal balanceará después con las piezas finas de
        # ID_DIST -- este warm-up solo necesita dejarla en un punto de
        # partida razonable, no en pop_tol.
        epsilon_warmup_cut = max(best_dev / 100 + 0.05, 0.20)

        recom_warmup_cut = partial(
            recom, pop_col=pop_col, pop_target=ideal_pop,
            epsilon=epsilon_warmup_cut, node_repeats=node_repeats,
        )

        updaters_cut = {
            "population": gc.updaters.Tally(pop_col, alias="population"),
        }
        partition_cut = gc.Partition(
            graph=graph_cut,
            assignment={n: cut_assignment[n] for n in graph_cut.nodes()},
            updaters=updaters_cut,
        )
        chain_warmup_cut = gc.MarkovChain(
            proposal=recom_warmup_cut,
            constraints=[contiguous],
            accept=always_accept,
            initial_state=partition_cut,
            total_steps=N_WARMUP,
        )

        warmed_cut = partition_cut
        n_warmup_efectivo = 0
        try:
            for step_w, state_w in enumerate(chain_warmup_cut):
                warmed_cut = state_w
                n_warmup_efectivo = step_w + 1
                pop_w = list(state_w["population"].values())
                dev_w = max(abs(p - ideal_pop) / ideal_pop for p in pop_w) * 100
                if dev_w <= epsilon_warmup_cut * 100 * 0.8:
                    print(f"  Warm-up comunal convergió en paso {step_w}"
                          f" (desv={dev_w:.1f}%)")
                    break
        except (IndexError, RuntimeError) as e:
            print(f"  ⚠ Warm-up comunal interrumpido: {e}")

        cut_index_warmed = {
            graph_cut.nodes[n]["CUT"]: warmed_cut.assignment[n]
            for n in graph_cut.nodes()
        }
        expanded = {
            node: cut_index_warmed[graph.nodes[node]["CUT"]]
            for node in graph.nodes()
        }
        warmed_state = gc.Partition(
            graph=graph, assignment=expanded, updaters=updaters,
        )

        dev_warmed = max(
            abs(p - ideal_pop) / ideal_pop
            for p in warmed_state["population"].values()
        ) * 100
        print(f"  Warm-up comunal expandido: dev={dev_warmed:.1f}%")

        # Segunda ronda: warm-up fino sobre graph (451 ID_DIST). El warm-up
        # comunal (arriba) solo puede llegar a lo que 52 piezas permiten
        # (~15-25% en R13); esta ronda usa las piezas finas de ID_DIST para
        # bajar de ahí a ≤pop_tol. Parte de warmed_state, que ya respeta CUT
        # por construcción (viene expandido desde graph_cut) -- por eso esta
        # ronda SÍ necesita preserve_CUT en constraints: sin ella, ReCom
        # podría partir una comuna al buscar el balance fino, y warmed_state
        # ya no sería válido para la cadena principal (que exige preserve_CUT
        # desde su propio initial_state).
        epsilon_warmup2 = max(dev_warmed / 100 + 0.02, pop_tol)

        recom_warmup2 = partial(
            recom, pop_col=pop_col, pop_target=ideal_pop,
            epsilon=epsilon_warmup2, node_repeats=node_repeats,
        )

        constraints_warmup2 = [contiguous, cd.make_preserve_constraint("CUT")]

        chain_warmup2 = gc.MarkovChain(
            proposal=recom_warmup2,
            constraints=constraints_warmup2,
            accept=always_accept,
            initial_state=warmed_state,
            total_steps=N_WARMUP * 3,
            # presupuesto generoso: la restricción conjunta (balance +
            # preserve_CUT) rechaza más propuestas que solo contiguous.
        )

        step_w2 = -1
        try:
            for step_w2, state_w2 in enumerate(chain_warmup2):
                warmed_state = state_w2
                pop_w2 = list(state_w2["population"].values())
                dev_w2 = max(abs(p - ideal_pop) / ideal_pop
                             for p in pop_w2) * 100
                if dev_w2 <= pop_tol * 100:
                    print(f"  Warm-up fino convergió en paso {step_w2}"
                          f" (desv={dev_w2:.1f}%)")
                    break
        except (IndexError, RuntimeError) as e:
            print(f"  ⚠ Warm-up fino interrumpido: {e}")

        n_warmup_efectivo += step_w2 + 1
        dev_warmed = max(
            abs(p - ideal_pop) / ideal_pop
            for p in warmed_state["population"].values()
        ) * 100

    else:
        chain_warmup = gc.MarkovChain(
            proposal=recom_warmup, constraints=[contiguous],
            accept=always_accept, initial_state=partition,
            total_steps=N_WARMUP,
        )

        warmed_state       = partition
        n_warmup_efectivo  = 0
        try:
            for step_w, state_w in enumerate(chain_warmup):
                warmed_state      = state_w
                n_warmup_efectivo = step_w + 1
                pop_w = list(state_w["population"].values())
                dev_w = max(abs(p - ideal_pop)/ideal_pop for p in pop_w) * 100
                if dev_w <= pop_tol * 100:
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

        warmup_converged_first_pass = bool(dev_warmed <= pop_tol * 100)

        # Si el warm-up no bajó de ±pop_tol, extenderlo una vez (mismo proposal,
        # continuando desde warmed_state) antes de rendirse. Sin esto, la cadena
        # principal terminaría fijando epsilon_recom por encima de pop_tol para
        # no bloquearse — el modelo B que el modelo A busca evitar.
        if not warmup_converged_first_pass:
            print(f"  ⚠ Warm-up no convergió a ±{pop_tol*100:.0f}% "
                  f"(dev_warmed={dev_warmed:.1f}%) — extendiendo...")
            chain_warmup_ext = gc.MarkovChain(
                proposal=recom_warmup, constraints=[contiguous],
                accept=always_accept, initial_state=warmed_state,
                total_steps=N_WARMUP * 2,
            )
            step_w = -1
            try:
                for step_w, state_w in enumerate(chain_warmup_ext):
                    warmed_state = state_w
                    pop_w = list(state_w["population"].values())
                    dev_w = max(abs(p - ideal_pop)/ideal_pop for p in pop_w) * 100
                    if dev_w <= pop_tol * 100:
                        print(f"  Warm-up (extendido) convergió en paso {step_w} "
                              f"(desv={dev_w:.1f}%)")
                        break
            except (IndexError, RuntimeError) as e:
                print(f"  ⚠ Warmup extendido interrumpido ({e.__class__.__name__})")

            # Posición final (no acumulación por iteración): N_WARMUP (paso 1,
            # fijo) + pasos consumidos en la extensión hasta converger/salir.
            n_warmup_efectivo = N_WARMUP + (step_w + 1)

            dev_warmed = max(
                abs(p - ideal_pop)/ideal_pop
                for p in warmed_state["population"].values()
            ) * 100

    # ── Chequeo final de convergencia de warm-up (compartido por ambas ramas) ──
    warmup_converged = bool(dev_warmed <= pop_tol * 100)

    if not warmup_converged:
        print(f"  ⚠ Warm-up agotó {n_warmup_efectivo} pasos sin converger "
              f"a ±{pop_tol*100:.0f}% (dev_warmed={dev_warmed:.1f}%)")
        return {
            "region": region_code,
            "region_name": region_name,
            "scenario": scenario.name,
            "status": "sin_convergencia_warmup",
            "reason": REASON_WARMUP_DID_NOT_CONVERGE,
            "n_warmup_steps": n_warmup_efectivo,
            "warmup_final_dev": dev_warmed,
        }

    # ── Cadena principal ──────────────────────────────────────────────────────
    # Modelo A: epsilon_recom = pop_tol directamente. El warm-up (arriba) ya
    # garantiza dev_warmed <= pop_tol, así que la restricción dura de la
    # cadena principal es exactamente la tolerancia solicitada desde el
    # draw 0 — no una versión inflada por dev_warmed (modelo B).
    epsilon_recom = pop_tol

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

    # Modo soft: la penalización por partir comunas actúa en la aceptación de la
    # cadena principal (Metropolis sobre split_severity), no solo en la elección
    # del plan de referencia. Modo none/hard: aceptación incondicional, igual
    # que antes — misma población, tolerancia, n_distritos, datos y kwargs de
    # recom_proposal en ambos casos; solo cambia este criterio de aceptación.
    if (scenario.preserve_mode == "soft"
            and scenario.split_penalty > 0
            and "split_severity" in warmed_state.updaters):
        accept_main = cd.make_split_penalty_accept(scenario.split_penalty)
        print(f"  ✓ Aceptación penalizada por split_severity "
              f"(split_penalty={scenario.split_penalty})")
    else:
        accept_main = always_accept

    recom_proposal = partial(recom, **recom_kwargs_main)
    chain = gc.MarkovChain(
        proposal=recom_proposal,
        constraints=constraints_main,
        accept=accept_main,
        initial_state=warmed_state,
        total_steps=n_steps,
    )

    print(f"\n  Iniciando ReCom: {n_steps:,} pasos · "
          f"{n_distritos_eff} distritos · ±{pop_tol*100:.0f}% · "
          f"preserve={scenario.preserve_mode}...")

    # IDs en el mismo orden que los nodos del grafo (necesario para reconstruir
    # asignaciones y para guardar assignments.parquet con unit IDs reales)
    ids_ordenados = gdf_dec[id_col].tolist()

    # Delegar el bucle al módulo canónico — single source of truth para el muestreo
    planes, metricas_mc, n_steps_ejecutados = run_recom_chain(
        chain=chain,
        n_steps=n_steps,
        id_col=id_col,
        ids_ordenados=ids_ordenados,
        graph=graph,
        ideal_pop=ideal_pop,
        output_dir=run_dir,
        run_id=run_id,
        scenario_name=scenario.name,
        chain_id=0,
    )

    if not planes:
        return {"region": region_code, "status": "sin_planes",
                "scenario": scenario.name}

    # Filtrar planes válidos — rastrear tolerancia efectiva para el manifiesto.
    # IMPORTANTE: se filtra (plan, métrica) como pares para no perder la
    # correspondencia entre el plan efectivamente válido y SU métrica real
    # (un filtrado que descarta pasos deja huecos; recortar metricas_mc por
    # prefijo después de filtrar planes reasigna métricas de otros pasos).
    pop_tol_effective     = pop_tol
    pop_tol_fallback_used = False

    pares_validos = [(p, m) for p, m in zip(planes, metricas_mc)
                      if m["max_dev_pct"] <= pop_tol * 100]
    if not pares_validos:
        for tol_f in [pop_tol*1.5, pop_tol*2, 1.0]:
            pares_validos = [(p, m) for p, m in zip(planes, metricas_mc)
                              if m["max_dev_pct"] <= tol_f * 100]
            if pares_validos:
                print(f"  Usando tolerancia ±{tol_f*100:.0f}%: "
                      f"{len(pares_validos)} planes")
                pop_tol_effective     = tol_f
                pop_tol_fallback_used = True
                break
    if not pares_validos:
        pares_validos         = list(zip(planes, metricas_mc))
        pop_tol_effective     = 1.0
        pop_tol_fallback_used = True

    n_generados = len(metricas_mc)
    print(f"  Planes válidos: {len(pares_validos)}/{n_generados}")

    if not pares_validos:
        return {"region": region_code, "status": "sin_planes_validos",
                "scenario": scenario.name, "n_generados": n_generados}

    planes, metricas_validas = (list(t) for t in zip(*pares_validos))

    # ── Reconstruir asignaciones con IDs de unidad ───────────────────────────
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
    # metricas_validas[i] es la métrica REAL del paso de cadena del que vino
    # planes[i] (ver filtrado por pares más arriba) — plan_id indexa de forma
    # consistente tanto para max_dev_pob_pct/cut_edges (aquí) como para
    # pp_promedio/n_comunas_partidas/split_severity (calculados más abajo
    # sobre planes[plan_id]).
    df_ensemble = pd.DataFrame([
        {"plan_id": i, "max_dev_pob_pct": round(float(m["max_dev_pct"]), 3),
         "pp_promedio": np.nan, "cut_edges": int(m["cut_edges"])}
        for i, m in enumerate(metricas_validas)
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
        n_splits_list   = []
        severity_list   = []
        pop_affect_list = []
        for si in split_indices:
            a_s = reconstruir_asignacion(planes[si], graph, ids_ordenados)
            sm  = cd.plan_split_metrics(
                a_s, gdf_dec, unit_col="CUT", id_col="ID_DIST",
                pop_col=pop_col,
            )
            n_splits_list.append(sm["n_comunas_partidas"])
            severity_list.append(sm["split_severity"])
            pop_affect_list.append(sm["pop_afectada_pct"])

        # Asignar al ensemble con interpolación simple
        df_ensemble["n_comunas_partidas"] = np.nan
        df_ensemble["split_severity"]     = np.nan
        df_ensemble["pop_afectada_pct"]   = np.nan
        for ii, si in enumerate(split_indices):
            df_ensemble.loc[si, "n_comunas_partidas"] = n_splits_list[ii]
            df_ensemble.loc[si, "split_severity"]     = round(severity_list[ii], 4)
            df_ensemble.loc[si, "pop_afectada_pct"]   = round(pop_affect_list[ii], 4)

        print(f"  Comunas partidas (mediana): "
              f"{np.nanmedian(n_splits_list):.1f} / "
              f"{gdf_dec['CUT'].nunique()}")
        print(f"  Pob. afectada (mediana):    "
              f"{np.nanmedian(pop_affect_list)*100:.1f}%")
    else:
        df_ensemble["n_comunas_partidas"] = 0
        df_ensemble["split_severity"]     = 0.0
        df_ensemble["pop_afectada_pct"]   = 0.0

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

    pop_label_col = pop_label.capitalize()
    if id_col == "ID_DIST":
        col_names = ["Distrito", pop_label_col, "N_APC", "N_Comunas", "Desv_%"]
        if "CUT" not in gdf_dec.columns:
            col_names = ["Distrito", pop_label_col, "N_APC", "Desv_%"]
    else:
        col_names = ["Distrito", pop_label_col, "N_Comunas", "Desv_%"]

    try:
        pop_summary.columns = col_names
    except ValueError:
        pass

    print(f"\n  Detalle del plan de referencia (id={ref_plan_id}):")
    print(pop_summary.to_string(index=False))

    # ── Métricas de comunas partidas del plan de referencia ───────────────────
    n_split_ref = 0
    if id_col == "ID_DIST" and "CUT" in gdf_dec.columns:
        split_summary = cd.split_unit_summary(
            ref_plan_mapped, gdf_dec,
            unit_col="CUT", id_col="ID_DIST", pop_col=pop_col,
        )
        n_split_ref = len(split_summary)
        if not split_summary.empty:
            print(f"\n  Comunas partidas en plan de referencia: {len(split_summary)}")
            print(split_summary[["CUT","nombre","n_fragmentos",
                                  "pop_total","split_severity"]]
                  .head(10).to_string(index=False))
        split_summary.to_csv(
            os.path.join(run_dir, "comunas_partidas.csv"), index=False
        )

    # ── Guardar CSVs ──────────────────────────────────────────────────────────
    df_mc = pd.DataFrame(metricas_mc)
    # is_valid vive a nivel de draw en metricas_cadena.csv (no en
    # assignments.parquet, que no lleva columna de validez — evita repetir
    # el valor una vez por unidad de decisión por plan). Mismo umbral que
    # ensemble.validity_filter en run_manifest.json (pop_tol*100, no
    # pop_tol_effective — la tolerancia declarada, no la relajada por fallback).
    df_mc["is_valid"] = df_mc["max_dev_pct"] <= pop_tol * 100
    # Primario: en run_dir (con run_id)
    df_mc.to_csv(os.path.join(run_dir, "metricas_cadena.csv"), index=False)
    df_ensemble.to_csv(os.path.join(run_dir, "ensemble_stats.csv"), index=False)
    pop_summary.to_csv(os.path.join(run_dir, "plan_referencia_detalle.csv"), index=False)
    # Compatibilidad retroactiva: ensemble_stats y metricas_cadena también en out_dir
    df_mc.to_csv(os.path.join(out_dir, "metricas_cadena.csv"), index=False)
    df_ensemble.to_csv(os.path.join(out_dir, "ensemble_stats.csv"), index=False)

    # ── Guardar scenario.yml en run_dir ───────────────────────────────────────
    cd.save_scenario(scenario, os.path.join(run_dir, "scenario.yml"))

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
        plt.savefig(os.path.join(run_dir_figuras, "ref_vs_extremo.png"),
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
        plt.savefig(os.path.join(run_dir_figuras, "cadena_markov.png"),
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
        plt.savefig(os.path.join(run_dir_figuras, "ensemble_distribucion.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 4: balance poblacional del plan de referencia
        cd.plot_plan(
            gdf_dec, assignment=ref_plan_mapped,
            id_col=id_col, pop_col=pop_col,
            title=f"{region_name} [{scenario.name}] — Plan de referencia (id={ref_plan_id})",
            show_pop_balance=True,
            save_path=os.path.join(run_dir_figuras, "ref_balance.png"),
        )
        plt.close("all")

        # Figura 5: compacidad
        metricas_dist = cd.all_compactness(gdf_dec, id_col=id_col)
        cd.plot_compactness(
            gdf_dec, metricas_dist, id_col=id_col,
            metric="polsby_popper",
            title=f"{region_name} [{scenario.name}] — Compacidad",
            save_path=os.path.join(run_dir_figuras, "compacidad.png"),
        )
        plt.close("all")

        print(f"\n  Figuras guardadas en {run_dir_figuras}/")

    # ── Resumen final ─────────────────────────────────────────────────────────
    timestamp_end = datetime.datetime.now().isoformat(timespec="seconds")

    # ── run_manifest.json ─────────────────────────────────────────────────────
    try:
        manifest = build_run_manifest(
            run_id=run_id,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            scenario=scenario,
            pop_source=pop_source,
            pop_col_effective=pop_col,
            pop_tolerance_requested=pop_tol,
            pop_tolerance_effective=pop_tol_effective,
            pop_tolerance_fallback_used=pop_tol_fallback_used,
            n_steps_requested=n_steps,
            n_steps_executed=n_steps_ejecutados,
            n_steps_warmup=n_warmup_efectivo,
            n_plans_generated=n_generados,
            n_plans_valid=len(planes),
            region_code=region_code,
            region_name=region_name,
            n_units=n_units,
            n_islands_found=len(islands_gc),
            extra={
                "sampler_diagnostics": {
                    "epsilon_recom":     epsilon_recom,
                    "warmup_converged":  warmup_converged,
                    "warmup_final_dev":  dev_warmed,
                    "total_draws":       n_generados,
                    "valid_draws":       len(planes),
                    "valid_fraction":    (len(planes) / n_generados) if n_generados else 0.0,
                    "pop_tol_used":      pop_tol,
                    "warmup_steps":      n_warmup_efectivo,
                    # gerrychain emite warnings de bipartición fallida vía
                    # warnings.warn() dentro de recom()/bipartition_tree, sin
                    # exponer un contador accesible desde MarkovChain. Mejora
                    # futura: envolver el bucle de la cadena en
                    # warnings.catch_warnings(record=True) y contar las
                    # entradas correspondientes. Por ahora, null.
                    "bipartition_warnings": None,
                },
                "population_source":  pop_source,
                "population_measure": pop_label,
                # Contrato de datos explícito entre assignments.parquet (todos
                # los draws, sin filtrar) y ensemble_stats.csv (solo draws
                # válidos) — ver metricas_cadena.csv:is_valid para la condición
                # a nivel de draw y CAMBIO 3 de compare_scenarios.py, que
                # verifica este threshold contra el pop_tol de la comparación.
                "ensemble": {
                    "assignments_scope":       "all_draws",
                    "assignments_n_draws":     n_generados,
                    "analysis_scope":          "valid_draws_only",
                    "analysis_n_draws":        len(pares_validos),
                    "validity_filter": {
                        "metric":    "max_dev_pob_pct",
                        "operator":  "<=",
                        "threshold": pop_tol * 100,
                    },
                    "canonical_analysis_file": "ensemble_stats.csv",
                },
            },
        )
        save_run_manifest(manifest, run_dir)
    except Exception as e:
        warnings.warn(f"No se pudo guardar run_manifest.json: {e}")

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
        "run_dir":        run_dir,
        "run_id":         run_id,
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
    print(f"  n_distritos : {scenario.n_districts}"
          f"{'  (--n-distritos explícito)' if args.n_distritos is not None else '  (desde escenario)'}")
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
                n_distritos=scenario.n_districts,
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
    if "reason" in df_res.columns:
        cols_resumen.append("reason")
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
