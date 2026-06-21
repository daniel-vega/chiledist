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
import os
import sys
import warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
import matplotlib.pyplot as plt

import chiledist as cd
from chiledist.config import SCENARIOS, load_scenario

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
    p.add_argument("--n-distritos", type=int, default=8)
    p.add_argument("--pop-tol",    type=float, default=0.15)
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

def run_all_scenarios(
    region_code: int,
    base_dir: str,
    output_base: str,
    scenarios: list,
    n_distritos: int,
    pop_tol: float,
    n_steps: int,
    seed: int,
    skip_viz: bool,
) -> list[dict]:
    """Corre redistritaje para todos los escenarios en la región."""
    from scripts.redistritaje import analizar_region

    resultados = []
    for scenario in scenarios:
        print(f"\n{'─'*60}")
        print(f"  Corriendo escenario: {scenario.name}")
        try:
            res = analizar_region(
                region_code=region_code,
                base_dir=base_dir,
                output_base=output_base,
                n_distritos=n_distritos,
                pop_tol=pop_tol,
                n_steps=n_steps,
                seed=seed,
                skip_viz=skip_viz,
                scenario=scenario,
            )
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
# Comparar y exportar (usa chiledist.scenario_comparison)
# ──────────────────────────────────────────────────────────────────────────────

def compare_and_export(
    region_code: int,
    output_base: str,
    scenarios: list,
    skip_viz: bool,
) -> pd.DataFrame:
    """
    Lee los ensemble_stats de cada escenario y produce la comparación.
    Delega la lógica de análisis y visualización a chiledist.scenario_comparison.
    """
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    out_dir = os.path.join(output_base, region_name, "comparacion")
    os.makedirs(out_dir, exist_ok=True)

    # Cargar ensembles desde disco
    sc_names = [sc.name for sc in scenarios]
    redistritaje_dir = os.path.join(output_base, region_name, "redistritaje")
    ensembles = cd.load_ensembles_from_disk(output_base, region_code, sc_names)

    if not ensembles:
        print("  ⚠ Sin datos suficientes para comparar.")
        return pd.DataFrame()

    # Tabla de comparación con deltas + ranking
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

    return df_comp


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
    print(f"  n_distritos : {args.n_distritos}")

    for region_code in regiones:
        print(f"\n{'#'*60}")
        print(f"  Región {region_code:02d} — {REGION_NOMBRES.get(region_code, '?')}")
        print(f"{'#'*60}")

        if not args.skip_run:
            # Importar dinámicamente para evitar circular
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            from redistritaje import analizar_region

            for scenario in scenarios:
                import dataclasses
                sc = dataclasses.replace(
                    scenario,
                    n_districts=args.n_distritos,
                    pop_tolerance=args.pop_tol,
                    n_steps=args.n_steps,
                    seed=args.seed,
                )
                print(f"\n{'─'*50}")
                print(f"  Corriendo: {sc.name}")
                try:
                    analizar_region(
                        region_code=region_code,
                        base_dir=base_dir,
                        output_base=output_base,
                        n_distritos=args.n_distritos,
                        pop_tol=args.pop_tol,
                        n_steps=args.n_steps,
                        seed=args.seed,
                        skip_viz=args.skip_viz,
                        scenario=sc,
                    )
                except Exception as e:
                    import traceback
                    print(f"  ⚠ Error: {e}")
                    traceback.print_exc()

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
