"""
scripts/compare_scenarios.py
============================
Comparación formal de escenarios de redistritaje para una región.

Corre los tres modos predefinidos (legal, apc_free, apc_soft) sobre la
misma región y produce:
    comparacion_escenarios.csv          — tabla de métricas + deltas + ranking
    comunas_partidas_frecuencia.csv     — comunas partidas por escenario
    tradeoff_balance_splits.png         — balance vs comunas partidas
    tradeoff_compacidad_splits.png      — compacidad vs comunas partidas
    boxplots_comparativos.png           — distribuciones por escenario

Uso:
    python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 13
    python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 5,13 \\
        --scenarios legal,apc_free,apc_soft \\
        --n-distritos 8 --n-steps 5000
"""

import argparse
import glob
import json
import os
import sys
import warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
import matplotlib.pyplot as plt

import chiledist as cd
from chiledist.domain.scenario import load_scenario
from chiledist.rules.scenario_rules import SCENARIOS

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
        description="Comparación de escenarios de redistritaje."
    )
    p.add_argument("--base-dir",   default=".",
                   help="Directorio raíz con SHP_APC2023_R*")
    p.add_argument("--output-dir", default=None,
                   help="Directorio base de salida")
    p.add_argument("--regiones",   default="13",
                   help="Regiones: número, lista (5,8,13) o 'todas'")
    p.add_argument("--scenarios",  default="legal,apc_free,apc_soft",
                   help="Escenarios a comparar (default: legal,apc_free,apc_soft)")
    p.add_argument("--scenario-files", default=None,
                   help="Rutas YAML separadas por coma (override --scenarios)")
    p.add_argument("--n-distritos", type=int, default=None,
                   help="Número de particiones territoriales a generar (NO "
                        "la magnitud electoral 3-8 de Ley 20.840). Default: "
                        "n_districts de cada escenario — cada escenario "
                        "conserva el suyo salvo que se pase este flag "
                        "explícitamente, en cuyo caso se aplica a todos.")
    p.add_argument("--pop-tol",    type=float, default=0.15,
                   help="Tolerancia poblacional usada al CORRER los "
                        "escenarios (ignorado con --skip-run, ya que ahí "
                        "no se invoca analizar_region()). Ya NO se usa para "
                        "validar consistencia entre corridas existentes — "
                        "esa validación ahora compara pop_tolerance_requested "
                        "entre los propios escenarios via sus "
                        "run_manifest.json, ver check_validity_filter_consistency().")
    p.add_argument("--n-steps",    type=int, default=10000)
    p.add_argument("--seed",       type=int, default=42)
    p.add_argument("--skip-viz",   action="store_true")
    p.add_argument("--skip-run",   action="store_true",
                   help="Solo comparar resultados existentes (no correr redistritaje)")
    return p.parse_args()


def parse_regiones(s: str) -> list[int]:
    if s.strip().lower() == "todas":
        return list(range(1, 17))
    return [int(r.strip()) for r in s.split(",")]


def load_scenarios_list(args) -> list:
    if args.scenario_files:
        return [load_scenario(p.strip())
                for p in args.scenario_files.split(",")]
    keys = [k.strip() for k in args.scenarios.split(",")]
    scenarios = []
    for k in keys:
        if k not in SCENARIOS:
            print(f"  ⚠ Escenario '{k}' no reconocido. "
                  f"Opciones: {list(SCENARIOS.keys())}")
            continue
        scenarios.append(SCENARIOS[k])
    return scenarios


# ──────────────────────────────────────────────────────────────────────────────
# Correr redistritaje para cada escenario
# ──────────────────────────────────────────────────────────────────────────────

def _import_analizar_region():
    """Importa analizar_region desde redistritaje.py usando ruta absoluta."""
    import importlib.util
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redistritaje.py")
    _spec = importlib.util.spec_from_file_location("redistritaje", _path)
    _mod  = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod.analizar_region


def run_all_scenarios(
    region_code: int,
    base_dir: str,
    output_base: str,
    scenarios: list,
    n_distritos: int | None,
    pop_tol: float,
    n_steps: int,
    seed: int,
    skip_viz: bool,
) -> list[dict]:
    """
    Corre redistritaje para todos los escenarios en la región.

    n_distritos: si es None, cada escenario conserva su propio
    scenario.n_districts; si se pasa explícito, se aplica a todos
    (comparabilidad pedida por el usuario), sin homogeneizarlos por default.
    """
    analizar_region = _import_analizar_region()

    resultados = []
    for scenario in scenarios:
        n_distritos_efectivo = (
            n_distritos if n_distritos is not None else scenario.n_districts
        )
        print(f"\n{'─'*60}")
        print(f"  Corriendo escenario: {scenario.name}  "
              f"(n_distritos={n_distritos_efectivo})")
        try:
            res = analizar_region(
                region_code=region_code,
                base_dir=base_dir,
                output_base=output_base,
                n_distritos=n_distritos_efectivo,
                pop_tol=pop_tol,
                n_steps=n_steps,
                seed=seed,
                skip_viz=skip_viz,
                scenario=scenario,
            )
            _persist_scenario_status(output_base, region_code, scenario.name, res)
            resultados.append(res)
        except Exception as e:
            import traceback
            print(f"  ⚠ Error en escenario {scenario.name}: {e}")
            traceback.print_exc()
            resultados.append({
                "region": region_code,
                "scenario": scenario.name,
                "status": "error",
                "error": str(e),
            })
    return resultados


# ──────────────────────────────────────────────────────────────────────────────
# Persistir status de escenarios sin ensemble válido (infeasible_population,
# sin_particion, etc.) para que sigan visibles en la comparación — incluso
# en una corrida posterior con --skip-run.
# ──────────────────────────────────────────────────────────────────────────────

def _persist_scenario_status(
    output_base: str,
    region_code: int,
    scenario_name: str,
    result: dict,
) -> None:
    """
    Escribe scenario_status.json con el dict de resultado completo de
    analizar_region() cuando status != "ok" (preserva status, reason y el
    resto del diagnóstico, ej. los campos del preflight de factibilidad).

    Si el status es "ok", limpia cualquier scenario_status.json obsoleto de
    una corrida previa no viable, para no dejar un estado fantasma.
    """
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    sc_dir      = os.path.join(output_base, region_name, "redistritaje", scenario_name)
    status_path = os.path.join(sc_dir, "scenario_status.json")

    if result.get("status") == "ok":
        if os.path.exists(status_path):
            os.remove(status_path)
        return

    os.makedirs(sc_dir, exist_ok=True)
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)


# ──────────────────────────────────────────────────────────────────────────────
# Cargar resultados existentes de disco
# ──────────────────────────────────────────────────────────────────────────────

def load_existing_results(
    region_code: int,
    output_base: str,
    scenarios: list,
) -> list[dict]:
    """Lee ensemble_stats.csv de cada escenario desde disco."""
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    resultados  = []
    for sc in scenarios:
        ens_path = os.path.join(
            output_base, region_name, "redistritaje", sc.name,
            "ensemble_stats.csv",
        )
        if not os.path.exists(ens_path):
            print(f"  ⚠ No encontrado: {ens_path}")
            resultados.append({"scenario": sc.name, "status": "no_encontrado"})
            continue
        df = pd.read_csv(ens_path)
        resultados.append({
            "region":     region_code,
            "scenario":   sc.name,
            "status":     "ok",
            "ensemble":   df,
            "out_dir":    os.path.dirname(ens_path),
        })
    return resultados


# ──────────────────────────────────────────────────────────────────────────────
# Validar que los escenarios comparados fueron generados con el mismo
# pop_tolerance_requested (contrato de datos: redistritaje.py::analizar_region()
# lo escribe en manifest["scenario"]["pop_tolerance_requested"] al momento de
# generar el ensemble; ver CAMBIO 1/2). Antes esto se comparaba contra un
# pop_tol externo (--pop-tol de esta invocación de compare_scenarios.py, sin
# relación con los datos ya generados en disco, especialmente en --skip-run) —
# ahora se comparan los escenarios ENTRE SÍ, contra su propio dato real.
# ──────────────────────────────────────────────────────────────────────────────

def check_validity_filter_consistency(
    region_code: int,
    output_base: str,
    scenarios: list,
) -> None:
    """
    Para cada escenario, busca el run_manifest.json más reciente (el
    subdirectorio run_* de mayor timestamp) y lee
    manifest["scenario"]["pop_tolerance_requested"] — el pop_tol REAL con el
    que se generó esa corrida. Si los escenarios comparados no comparten el
    mismo valor, imprime una advertencia con el detalle por escenario — no
    interrumpe la comparación, ya que cada ensemble_stats.csv sigue siendo un
    dato válido, solo generado bajo tolerancias distintas entre sí.

    Sin manifest encontrado (corridas previas a este contrato, o escenarios
    sintéticos de test) ese escenario simplemente no participa de la
    comparación cruzada.
    """
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    pop_tol_por_escenario: dict = {}

    for sc in scenarios:
        sc_dir = os.path.join(output_base, region_name, "redistritaje", sc.name)
        run_dirs = sorted(glob.glob(os.path.join(sc_dir, "run_*")))
        if not run_dirs:
            continue
        manifest_path = os.path.join(run_dirs[-1], "run_manifest.json")
        if not os.path.exists(manifest_path):
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        pop_tol_manifest = manifest.get("scenario", {}).get("pop_tolerance_requested")
        if pop_tol_manifest is None:
            continue
        pop_tol_por_escenario[sc.name] = float(pop_tol_manifest)

    valores_distintos = set(pop_tol_por_escenario.values())
    if len(valores_distintos) > 1:
        detalle = ", ".join(
            f"{nombre}={valor:.4f}"
            for nombre, valor in pop_tol_por_escenario.items()
        )
        print(
            f"  ⚠ WARNING: los escenarios comparados no comparten el mismo "
            f"pop_tolerance_requested — {detalle}. El ranking entre ellos "
            f"puede no ser comparable (cada ensemble se generó bajo una "
            f"tolerancia poblacional distinta)."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Comparar y exportar (usa chiledist.scenario_comparison)
# ──────────────────────────────────────────────────────────────────────────────

def compare_and_export(
    region_code: int,
    output_base: str,
    scenarios: list,
    skip_viz: bool,
) -> dict:
    """
    Lee los ensemble_stats de cada escenario y produce la comparación.
    Delega la lógica de análisis y visualización a chiledist.scenario_comparison.

    Un escenario sin ensemble válido (status != "ok" — ej.
    infeasible_population, sin_particion) sigue visible en `overview` con su
    status/reason reales y included_in_scoring=False; nunca entra a
    compare_ensembles/rank_scenarios (sin score artificial, NaN relleno ni
    peor rank). `completeness` marca la comparación global como
    INCOMPLETE cuando falta algún escenario esperado.

    Al inicio, valida que todos los escenarios comparten el mismo
    pop_tolerance_requested (leído del run_manifest.json de cada uno) — ver
    check_validity_filter_consistency(). No depende de ningún --pop-tol
    externo a esta invocación: compara los escenarios entre sí, contra su
    propio dato real.

    Returns
    -------
    dict con:
        ranking      — DataFrame de cd.rank_scenarios, solo escenarios con
                        ensemble válido (vacío si no hay ninguno). Idéntico
                        al comportamiento previo cuando todos son válidos.
        overview     — DataFrame con una fila por escenario ESPERADO
                        (válido o no), ver cd.build_scenario_overview.
        completeness — dict, ver cd.assess_comparison_completeness.
    """
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    out_dir = os.path.join(output_base, region_name, "comparacion")
    os.makedirs(out_dir, exist_ok=True)

    check_validity_filter_consistency(region_code, output_base, scenarios)

    # Cargar ensembles + status de escenarios sin ensemble válido desde disco
    sc_names = [sc.name for sc in scenarios]
    redistritaje_dir = os.path.join(output_base, region_name, "redistritaje")
    ensembles = cd.load_ensembles_from_disk(output_base, region_code, sc_names)
    statuses  = cd.load_scenario_statuses_from_disk(output_base, region_code, sc_names)

    overview     = cd.build_scenario_overview(sc_names, ensembles, statuses)
    completeness = cd.assess_comparison_completeness(
        sc_names, ensembles, baseline="legal_comunas"
    )

    overview_path = os.path.join(out_dir, "escenarios_overview.csv")
    overview.to_csv(overview_path, index=False)

    status_path = os.path.join(out_dir, "comparacion_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(completeness, f, indent=2, ensure_ascii=False)

    print(f"\n  Estado de la comparación: {completeness['comparison_status']} "
          f"({completeness['valid_ensembles']}/{completeness['expected_scenarios']} "
          f"escenarios con ensemble válido)")
    if completeness["comparison_status"] == "INCOMPLETE":
        for _, row in overview[~overview["included_in_scoring"]].iterrows():
            detalle = f", reason={row['reason']}" if row["reason"] else ""
            print(f"    ⚠ {row['escenario']}: status={row['status']}{detalle} "
                  f"— excluido del scoring, no descartado de la salida")
        if completeness["missing_baseline"]:
            print(f"    Baseline ausente del scoring: "
                  f"{completeness['missing_baseline']}. El ranking entre el "
                  f"resto de los escenarios es parcial/descriptivo — no una "
                  f"comparación H1 completa frente al régimen legal.")

    if not ensembles:
        print("  ⚠ Sin datos suficientes para comparar (ningún ensemble válido).")
        return {"ranking": pd.DataFrame(), "overview": overview,
                "completeness": completeness}

    # Tabla de comparación con deltas + ranking — solo escenarios con
    # ensemble válido (compare_ensembles/rank_scenarios sin cambios)
    df_comp = cd.compare_ensembles(ensembles, baseline="legal_comunas")
    df_comp = cd.rank_scenarios(df_comp)

    comp_path = os.path.join(out_dir, "comparacion_escenarios.csv")
    df_comp.to_csv(comp_path, index=False)
    print(f"\n  Comparación guardada: {comp_path}")
    cols_show = ["escenario", "rank", "composite_score",
                 "max_dev_pob_pct_median", "pp_promedio_median",
                 "n_comunas_partidas_median"]
    print(df_comp[[c for c in cols_show if c in df_comp.columns]]
          .to_string(index=False))

    # Frecuencia de comunas partidas por escenario
    freq_df = cd.split_frequency_table(redistritaje_dir, sc_names)
    if not freq_df.empty:
        freq_path = os.path.join(out_dir, "comunas_partidas_frecuencia.csv")
        freq_df.to_csv(freq_path, index=False)
        print(f"  Comunas partidas (frecuencia): {freq_path} "
              f"({len(freq_df)} comunas)")

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not skip_viz and len(ensembles) >= 2:
        # Tradeoff 1: balance vs comunas partidas
        has_splits = any("n_comunas_partidas" in df.columns
                         for df in ensembles.values())
        if has_splits:
            fig = cd.plot_tradeoff_frontier(
                ensembles,
                x_col="n_comunas_partidas",
                y_col="max_dev_pob_pct",
                title=f"{region_name} — Tradeoff: balance vs comunas partidas",
                show_pareto=True,
            )
            fig.savefig(os.path.join(out_dir, "tradeoff_balance_splits.png"),
                        dpi=150, bbox_inches="tight")
            plt.close(fig)

        # Tradeoff 2: compacidad vs comunas partidas
        has_pp_splits = any(
            "n_comunas_partidas" in df.columns and "pp_promedio" in df.columns
            for df in ensembles.values()
        )
        if has_pp_splits:
            fig = cd.plot_tradeoff_frontier(
                ensembles,
                x_col="n_comunas_partidas",
                y_col="pp_promedio",
                minimize_y=False,
                title=f"{region_name} — Tradeoff: compacidad vs comunas partidas",
                show_pareto=True,
            )
            fig.savefig(os.path.join(out_dir, "tradeoff_compacidad_splits.png"),
                        dpi=150, bbox_inches="tight")
            plt.close(fig)

        # Boxplots comparativos
        fig = cd.plot_boxplots_comparativos(
            ensembles,
            title=f"{region_name} — Comparación de escenarios",
        )
        fig.savefig(os.path.join(out_dir, "boxplots_comparativos.png"),
                    dpi=150, bbox_inches="tight")
        plt.close(fig)

        print(f"  Figuras guardadas en {out_dir}/")

    return {"ranking": df_comp, "overview": overview, "completeness": completeness}


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args        = parse_args()
    base_dir    = args.base_dir
    output_base = args.output_dir or os.path.join(base_dir, "datos")
    regiones    = parse_regiones(args.regiones)
    scenarios   = load_scenarios_list(args)

    if not scenarios:
        print("No hay escenarios válidos. Abortando.")
        return

    print(f"\nchiledist — Comparación de escenarios")
    print(f"  base_dir    : {base_dir}")
    print(f"  regiones    : {regiones}")
    print(f"  escenarios  : {[s.name for s in scenarios]}")
    if args.n_distritos is not None:
        print(f"  n_distritos : {args.n_distritos}  "
              f"(--n-distritos explícito, aplica a todos los escenarios)")
    else:
        print(f"  n_distritos : según cada escenario (scenario.n_districts)")

    for region_code in regiones:
        print(f"\n{'#'*60}")
        print(f"  Región {region_code:02d} — {REGION_NOMBRES.get(region_code, '?')}")
        print(f"{'#'*60}")

        if not args.skip_run:
            analizar_region = _import_analizar_region()

            for scenario in scenarios:
                import dataclasses
                n_distritos_efectivo = (
                    args.n_distritos if args.n_distritos is not None
                    else scenario.n_districts
                )
                sc = dataclasses.replace(
                    scenario,
                    n_districts=n_distritos_efectivo,
                    pop_tolerance=args.pop_tol,
                    n_steps=args.n_steps,
                    seed=args.seed,
                )
                print(f"\n{'─'*50}")
                print(f"  Corriendo: {sc.name}  (n_distritos={n_distritos_efectivo})")
                try:
                    res = analizar_region(
                        region_code=region_code,
                        base_dir=base_dir,
                        output_base=output_base,
                        n_distritos=n_distritos_efectivo,
                        pop_tol=args.pop_tol,
                        n_steps=args.n_steps,
                        seed=args.seed,
                        skip_viz=args.skip_viz,
                        scenario=sc,
                    )
                    _persist_scenario_status(output_base, region_code, sc.name, res)
                except Exception as e:
                    import traceback
                    print(f"  ⚠ Error: {e}")
                    traceback.print_exc()
                    _persist_scenario_status(
                        output_base, region_code, sc.name,
                        {"status": "error", "error": str(e)},
                    )

        # Comparar resultados
        print(f"\n  Comparando resultados...")
        compare_and_export(
            region_code=region_code,
            output_base=output_base,
            scenarios=scenarios,
            skip_viz=args.skip_viz,
        )


if __name__ == "__main__":
    main()
