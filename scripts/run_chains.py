"""
scripts/run_chains.py
=====================
H5 — Robustez metodológica: múltiples cadenas ReCom + diagnósticos de convergencia.

Pasos:
    1. Carga o corre N cadenas ReCom independientes (semillas distintas)
       sobre un escenario y región dados.
    2. Calcula diagnósticos de mezcla: R-hat (Gelman-Rubin), ESS, ACF.
    3. Genera trazas y evolución del R-hat.
    4. (Opcional) Análisis de sensibilidad del score compuesto a los pesos.

Uso básico:
    python scripts/run_chains.py --regiones 13 --scenario apc_soft --n-chains 4

Solo diagnósticos (cadenas ya corridas):
    python scripts/run_chains.py --regiones 13 --scenario apc_soft --skip-run

Sensibilidad de pesos:
    python scripts/run_chains.py --regiones 13 --scenario apc_soft --sensitivity

Salidas en datos/<REGION>/chains/<SCENARIO>/:
    cadena_XX_metricas.csv           métricas por cadena (step, cut_edges, max_dev_pct)
    convergencia_diagnosticos.csv    tabla R-hat / ESS / ACF
    trace_plot.png
    gelman_rubin_evolution.png
    sensibilidad_pesos.csv           (solo con --sensitivity)
    sensibilidad_pesos.png           (solo con --sensitivity)
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
import matplotlib.pyplot as plt

import chiledist as cd
from chiledist.config import load_scenario, SCENARIOS


# ──────────────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────────────

CHAIN_METRICS = ["max_dev_pct", "cut_edges"]

SENSITIVITY_WEIGHT_SETS = {
    "default":      {"max_dev_pob_pct": 0.35, "pp_promedio": 0.20,
                     "cut_edges": 0.15, "n_comunas_partidas": 0.15,
                     "split_severity": 0.05, "pop_afectada_pct": 0.10},
    "solo_balance": {"max_dev_pob_pct": 0.80, "pp_promedio": 0.10,
                     "cut_edges": 0.05, "n_comunas_partidas": 0.05},
    "solo_compact": {"pp_promedio": 0.70, "max_dev_pob_pct": 0.20,
                     "cut_edges": 0.10},
    "equi":         {"max_dev_pob_pct": 0.20, "pp_promedio": 0.20,
                     "cut_edges": 0.20, "n_comunas_partidas": 0.20,
                     "split_severity": 0.10, "pop_afectada_pct": 0.10},
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _import_analizar_region():
    import importlib.util
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redistritaje.py")
    _spec = importlib.util.spec_from_file_location("redistritaje", _path)
    _mod  = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod.analizar_region


def _chain_output_dir(base_dir: str, region_code: int, scenario_name: str) -> str:
    from chiledist.data import REGIONES_APC
    region_nombre = REGIONES_APC.get(region_code, {}).get("nombre", f"R{region_code}")
    return os.path.join(base_dir, "datos", region_nombre, "chains", scenario_name)


def _chain_run_dir(chain_dir: str, seed: int) -> str:
    return os.path.join(chain_dir, f"seed_{seed:04d}")


# ──────────────────────────────────────────────────────────────────────────────
# Paso 1: correr cadenas
# ──────────────────────────────────────────────────────────────────────────────

def run_chains(
    region_code: int,
    base_dir: str,
    scenario: object,
    n_chains: int,
    base_seed: int,
    n_steps: int,
    pop_tol: float,
    n_distritos: int,
) -> list[str]:
    """Corre N cadenas independientes y retorna las rutas de sus directorios."""
    analizar_region = _import_analizar_region()

    chain_dir = _chain_output_dir(base_dir, region_code, scenario.name)
    run_dirs  = []

    for k in range(n_chains):
        seed    = base_seed + k
        run_dir = _chain_run_dir(chain_dir, seed)
        os.makedirs(run_dir, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"  Cadena {k+1}/{n_chains}  (seed={seed})")
        print(f"  Salida: {run_dir}")
        print(f"{'='*60}")

        analizar_region(
            region_code=region_code,
            base_dir=base_dir,
            output_dir=run_dir,
            scenario=scenario,
            n_distritos=n_distritos,
            pop_tol=pop_tol,
            n_steps=n_steps,
            seed=seed,
            skip_viz=True,
        )
        run_dirs.append(run_dir)

    return run_dirs


# ──────────────────────────────────────────────────────────────────────────────
# Paso 2: cargar métricas de cadena
# ──────────────────────────────────────────────────────────────────────────────

def load_chain_metrics(
    chain_dir: str,
    n_chains: int,
    base_seed: int,
) -> list[pd.DataFrame]:
    """Carga metricas_cadena.csv de cada subcarpeta seed_XXXX."""
    cadenas = []
    for k in range(n_chains):
        seed    = base_seed + k
        run_dir = _chain_run_dir(chain_dir, seed)
        csv_path = os.path.join(run_dir, "metricas_cadena.csv")

        if not os.path.exists(csv_path):
            print(f"  [WARN] No encontrado: {csv_path}")
            continue

        df = pd.read_csv(csv_path)
        df["chain"] = k + 1
        cadenas.append(df)
        print(f"  Cadena {k+1}: {len(df)} pasos  ({csv_path})")

    return cadenas


# ──────────────────────────────────────────────────────────────────────────────
# Paso 3: diagnósticos de convergencia
# ──────────────────────────────────────────────────────────────────────────────

def run_convergence_diagnostics(
    cadenas: list[pd.DataFrame],
    output_dir: str,
) -> pd.DataFrame:
    """Calcula R-hat, ESS, ACF-1 y genera figuras de traza y evolución."""
    os.makedirs(output_dir, exist_ok=True)

    # Tabla de diagnósticos
    df_diag = cd.mixing_diagnostics(cadenas, metrics=CHAIN_METRICS)
    print("\n--- Diagnósticos de convergencia ---")
    print(df_diag.to_string(index=False))
    diag_path = os.path.join(output_dir, "convergencia_diagnosticos.csv")
    df_diag.to_csv(diag_path, index=False)
    print(f"\n  Guardado: {diag_path}")

    # Trazas
    trace_path = os.path.join(output_dir, "trace_plot.png")
    cd.plot_trace(cadenas, metrics=CHAIN_METRICS, save_path=trace_path)
    plt.close("all")

    # Evolución R-hat (requiere >= 2 cadenas)
    if len(cadenas) >= 2:
        gr_path = os.path.join(output_dir, "gelman_rubin_evolution.png")
        cd.plot_gelman_rubin_evolution(cadenas, metrics=CHAIN_METRICS, save_path=gr_path)
        plt.close("all")
    else:
        print("  [INFO] Evolución R-hat omitida: se necesitan ≥ 2 cadenas.")

    return df_diag


# ──────────────────────────────────────────────────────────────────────────────
# Paso 4: sensibilidad a pesos del score compuesto
# ──────────────────────────────────────────────────────────────────────────────

def run_sensitivity_analysis(
    chain_dir: str,
    n_chains: int,
    base_seed: int,
    output_dir: str,
) -> None:
    """
    Para cada configuración de pesos en SENSITIVITY_WEIGHT_SETS, calcula
    el score compuesto del ensemble de cada cadena y reporta la concordancia
    de rankings entre configuraciones.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Cargar ensemble_stats de cada cadena
    ensemble_by_chain: dict[str, pd.DataFrame] = {}
    for k in range(n_chains):
        seed    = base_seed + k
        run_dir = _chain_run_dir(chain_dir, seed)
        csv_path = os.path.join(run_dir, "ensemble_stats.csv")
        if not os.path.exists(csv_path):
            print(f"  [WARN] Sin ensemble_stats.csv: {run_dir}")
            continue
        ensemble_by_chain[f"cadena_{k+1}"] = pd.read_csv(csv_path)

    if len(ensemble_by_chain) < 2:
        print("  [INFO] Sensibilidad omitida: se necesitan ensemble_stats de ≥ 2 cadenas.")
        return

    # Comparar distribuciones entre cadenas con score default
    print("\n--- Sensibilidad: KS entre cadenas (pesos default) ---")
    df_ks = cd.compare_sensitivity(ensemble_by_chain)
    print(df_ks.to_string(index=False))
    ks_path = os.path.join(output_dir, "sensibilidad_ks_cadenas.csv")
    df_ks.to_csv(ks_path, index=False)

    # Score por conjunto de pesos para cada cadena
    scores_by_config: dict[str, dict[str, float]] = {}
    for config_name, weights in SENSITIVITY_WEIGHT_SETS.items():
        sc = cd.ScoringConfig.from_weights(weights)
        scores_config: dict[str, float] = {}
        for cadena_name, df_ens in ensemble_by_chain.items():
            # Mediana como representante escalar del ensemble
            score_vals = {}
            for col, w in weights.items():
                if col in df_ens.columns:
                    score_vals[col] = float(df_ens[col].median())
            # Score compuesto simple (sin rank_scenarios completo — sin referencia)
            total_w = sum(weights.values())
            composite = sum(
                w / total_w * score_vals.get(col, 0.0)
                for col, w in weights.items()
            )
            scores_config[cadena_name] = composite
        scores_by_config[config_name] = scores_config

    # Concordancia de rankings entre configuraciones de pesos
    print("\n--- Concordancia de rankings entre configuraciones de pesos ---")
    config_names = list(scores_by_config.keys())
    rows_conc = []
    for i in range(len(config_names)):
        for j in range(i + 1, len(config_names)):
            ca, cb = config_names[i], config_names[j]
            conc = cd.ranking_concordance(scores_by_config[ca], scores_by_config[cb])
            rows_conc.append({
                "config_a":    ca,
                "config_b":    cb,
                "kendall_tau": conc["kendall_tau"],
                "spearman_rho": conc["spearman_rho"],
                "n_comunes":   conc["n_comunes"],
                "discordantes": len(conc["discordantes"]),
            })
            print(f"  {ca} vs {cb}: τ={conc['kendall_tau']:.3f}  ρ={conc['spearman_rho']:.3f}")

    df_conc = pd.DataFrame(rows_conc)
    conc_path = os.path.join(output_dir, "sensibilidad_pesos.csv")
    df_conc.to_csv(conc_path, index=False)
    print(f"\n  Guardado: {conc_path}")

    # Figura: τ de Kendall por par de configuraciones
    if len(df_conc) > 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        labels = [f"{r.config_a}\nvs\n{r.config_b}" for _, r in df_conc.iterrows()]
        ax.bar(range(len(df_conc)), df_conc["kendall_tau"], color="steelblue", alpha=0.8)
        ax.axhline(0.8, color="green", linestyle="--", linewidth=1, label="τ ≥ 0.8 (robusto)")
        ax.axhline(0.5, color="orange", linestyle="--", linewidth=1, label="τ ≥ 0.5 (moderado)")
        ax.set_xticks(range(len(df_conc)))
        ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylabel("τ de Kendall", fontsize=10)
        ax.set_ylim(-1.1, 1.1)
        ax.legend(fontsize=8)
        ax.set_title("Concordancia de rankings entre configuraciones de pesos", fontsize=10)
        fig.tight_layout()
        fig_path = os.path.join(output_dir, "sensibilidad_pesos.png")
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Guardado: {fig_path}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="H5 — Múltiples cadenas ReCom + diagnósticos de convergencia",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--base-dir", default=".", help="Directorio raíz del proyecto")
    p.add_argument("--regiones", type=int, nargs="+", default=[13],
                   help="Código(s) de región INE")
    p.add_argument("--scenario", default="apc_soft",
                   help="Nombre del escenario (o 'legal', 'apc_free', 'apc_soft')")
    p.add_argument("--scenario-file", default=None,
                   help="Ruta a YAML de escenario personalizado")
    p.add_argument("--n-chains", type=int, default=4,
                   help="Número de cadenas independientes")
    p.add_argument("--base-seed", type=int, default=42,
                   help="Semilla base; cadena k usa base_seed + k")
    p.add_argument("--n-steps", type=int, default=5_000,
                   help="Pasos de la cadena ReCom por cadena")
    p.add_argument("--pop-tol", type=float, default=0.05,
                   help="Tolerancia poblacional ReCom")
    p.add_argument("--n-distritos", type=int, default=None,
                   help="Número de distritos (None = inferido del escenario/región)")
    p.add_argument("--skip-run", action="store_true",
                   help="Omitir ejecución de cadenas; cargar CSVs existentes")
    p.add_argument("--sensitivity", action="store_true",
                   help="Ejecutar análisis de sensibilidad a pesos del score compuesto")
    return p


def main():
    args   = build_parser().parse_args()
    base   = os.path.abspath(args.base_dir)

    # Cargar escenario
    if args.scenario_file:
        scenario = load_scenario(args.scenario_file)
    elif args.scenario in SCENARIOS:
        scenario = SCENARIOS[args.scenario]
    else:
        scenario = load_scenario(
            os.path.join(base, "scenarios", f"{args.scenario}.yml")
        )

    for region_code in args.regiones:
        print(f"\n{'#'*70}")
        print(f"  Región {region_code}  |  Escenario: {scenario.name}")
        print(f"  {args.n_chains} cadenas  |  {args.n_steps} pasos  |  seed base={args.base_seed}")
        print(f"{'#'*70}")

        chain_dir  = _chain_output_dir(base, region_code, scenario.name)
        output_dir = chain_dir  # diagnósticos van al directorio raíz de la región/escenario

        if not args.skip_run:
            n_dist = args.n_distritos
            if n_dist is None:
                try:
                    from chiledist.data import REGIONES_APC
                    n_dist = REGIONES_APC.get(region_code, {}).get("n_distritos", 8)
                except Exception:
                    n_dist = 8
                print(f"  n_distritos inferido: {n_dist}")

            run_chains(
                region_code=region_code,
                base_dir=base,
                scenario=scenario,
                n_chains=args.n_chains,
                base_seed=args.base_seed,
                n_steps=args.n_steps,
                pop_tol=args.pop_tol,
                n_distritos=n_dist,
            )

        cadenas = load_chain_metrics(chain_dir, args.n_chains, args.base_seed)
        if not cadenas:
            print("  [ERROR] No se encontraron métricas de cadena. "
                  "¿Ya corriste las cadenas? (omitir --skip-run si no)")
            sys.exit(1)

        run_convergence_diagnostics(cadenas, output_dir)

        if args.sensitivity:
            run_sensitivity_analysis(
                chain_dir=chain_dir,
                n_chains=args.n_chains,
                base_seed=args.base_seed,
                output_dir=output_dir,
            )

    print("\nListo.")


if __name__ == "__main__":
    main()
