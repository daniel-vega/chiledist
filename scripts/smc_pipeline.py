"""
scripts/smc_pipeline.py
=======================
H5 — Robustez metodológica: pipeline SMC (R/redist) y comparación con ReCom.

Pasos:
    1. Carga la capa APC (unidades distritales o comunales) para la región.
    2. Construye el grafo de adyacencia.
    3. Exporta datos en formato redist (GPKG + edge list) y genera script R.
    4. Imprime instrucciones para ejecutar en R.
    5. (Si existe CSV de resultados SMC): importa planes y calcula métricas.
    6. (Si también existe ensemble ReCom): compara distribuciones con KS
       y concordancia de rankings.

Uso básico (solo generar script R):
    python scripts/smc_pipeline.py --regiones 13

Tras ejecutar el script R, comparar con ReCom:
    python scripts/smc_pipeline.py --regiones 13 --compare \\
        --recom-ensemble datos/RM/redistritaje/apc_soft/ensemble_stats.csv

Salidas en datos/<REGION>/smc/<SCENARIO>/:
    <scenario>_units.gpkg          geometrías exportadas para R
    <scenario>_redist.R            script R para redist_smc()
    (tras R) <scenario>_smc_planes.csv
    (tras R) <scenario>_smc_metricas.csv
    smc_vs_recom_ks.csv            (solo con --compare)
    smc_vs_recom_ranking.csv       (solo con --compare)
    smc_vs_recom_ks.png            (solo con --compare)
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
from chiledist.data import REGIONES_APC


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _smc_output_dir(base_dir: str, region_code: int, scenario_name: str) -> str:
    region_nombre = _region_nombre(region_code)
    return os.path.join(base_dir, "datos", region_nombre, "smc", scenario_name)


def _region_nombre(region_code: int) -> str:
    return REGIONES_APC.get(region_code, {}).get(
        "nombre_carpeta", f"R{region_code:02d}"
    )


def _resolve_scenario_n_districts(scenario_name: str, base_dir: str):
    """
    Resuelve scenario.n_districts para `scenario_name` reutilizando
    exclusivamente la infraestructura de escenarios ya existente (SCENARIOS,
    load_scenario + scenarios/<name>.yml) — el mismo mecanismo de resolución
    que ya usa run_chains.py. No introduce ninguna regla ni mapping nuevo.

    Devuelve None si `scenario_name` no puede resolverse inequívocamente a
    un ScenarioConfig con la arquitectura actual (caso que el caller debe
    tratar como configuración pendiente, no rellenar con un fallback).
    """
    if scenario_name in SCENARIOS:
        return SCENARIOS[scenario_name].n_districts
    yml_path = os.path.join(base_dir, "scenarios", f"{scenario_name}.yml")
    if os.path.exists(yml_path):
        return load_scenario(yml_path).n_districts
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Paso 1–2: carga de datos y grafo
# ──────────────────────────────────────────────────────────────────────────────

def load_region_data(
    region_code: int,
    base_dir: str,
    layer: str = "distrital",
    id_col: str = "ID_DIST",
    pop_col: str = "personas",
):
    """Carga GDF de la región y construye su grafo de adyacencia."""
    print(f"\n  Cargando capa '{layer}' para región {region_code}...")
    gdf = cd.load_layer(layer, base_dir=os.path.join(base_dir, "datos"),
                        regions=[region_code])

    if id_col not in gdf.columns:
        raise KeyError(
            f"Columna '{id_col}' no encontrada. "
            f"Columnas disponibles: {list(gdf.columns)}"
        )
    if pop_col not in gdf.columns:
        alt_cols = [c for c in gdf.columns if "pers" in c.lower() or "pob" in c.lower()]
        raise KeyError(
            f"Columna '{pop_col}' no encontrada. "
            f"Posibles alternativas: {alt_cols}"
        )

    print(f"  {len(gdf)} unidades cargadas  |  "
          f"población total: {gdf[pop_col].sum():,.0f}")

    print("  Construyendo grafo de adyacencia...")
    G, adj, id_list = cd.build_graph(gdf, id_col=id_col)
    print(f"  Grafo: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas")

    return gdf, G, adj, id_list


# ──────────────────────────────────────────────────────────────────────────────
# Paso 3: exportar para redist y generar script R
# ──────────────────────────────────────────────────────────────────────────────

def export_and_generate_script(
    gdf,
    adj,
    id_list: list,
    id_col: str,
    pop_col: str,
    n_districts: int,
    n_sims: int,
    output_dir: str,
    scenario_name: str,
    extra_cols: list = None,
) -> str:
    """
    Exporta los datos en formato redist y genera el script R.
    Retorna la ruta al script R generado.
    """
    os.makedirs(output_dir, exist_ok=True)

    # export_to_redist: genera GPKG + edge list + script R mínimo
    # (útil para depuración; generate_redist_script es el pipeline completo)
    r_path = cd.generate_redist_script(
        gdf,
        id_col=id_col,
        pop_col=pop_col,
        n_districts=n_districts,
        output_dir=output_dir,
        n_sims=n_sims,
        scenario_name=scenario_name,
        extra_cols=extra_cols,
    )

    return r_path


# ──────────────────────────────────────────────────────────────────────────────
# Paso 4: instrucciones R
# ──────────────────────────────────────────────────────────────────────────────

def print_r_instructions(r_path: str, output_dir: str, scenario_name: str):
    plans_csv   = os.path.join(output_dir, f"{scenario_name}_smc_planes.csv")
    metrics_csv = os.path.join(output_dir, f"{scenario_name}_smc_metricas.csv")

    print("\n" + "="*70)
    print("  INSTRUCCIONES PARA EJECUTAR EN R")
    print("="*70)
    print(f"""
  Requisitos (instalar en R si no están):
      install.packages(c("redist", "sf", "dplyr", "ggplot2"))

  Ejecutar el script generado:
      Rscript "{r_path}"

  O desde la consola R:
      source("{r_path}")

  Archivos que genera el script R:
      {plans_csv}
      {metrics_csv}

  Una vez generados, volver a correr este script con --compare:
      python scripts/smc_pipeline.py --regiones <N> \\
          --compare \\
          --plans-csv "{plans_csv}"
""")
    print("="*70)


# ──────────────────────────────────────────────────────────────────────────────
# Paso 5: importar planes SMC y convertir a ensemble_stats
# ──────────────────────────────────────────────────────────────────────────────

def load_smc_ensemble(
    plans_csv: str,
    metrics_csv: str,
    id_list: list,
) -> pd.DataFrame:
    """
    Importa planes SMC desde R y retorna un DataFrame estilo ensemble_stats
    con las métricas exportadas por el script R.
    """
    plans = cd.load_redist_results(plans_csv=plans_csv, id_list=id_list)
    print(f"  {len(plans)} planes SMC importados")

    if os.path.exists(metrics_csv):
        df_metrics = pd.read_csv(metrics_csv)
        # El script R genera: draw, polsby_popper, pop_deviation
        # Renombrar para alinear con METRICAS_STD de chiledist
        rename_map = {
            "polsby_popper":  "pp_promedio",
            "pop_deviation":  "max_dev_pob_pct",
        }
        df_metrics = df_metrics.rename(columns=rename_map)
        # pop_deviation de redist es fracción (ej. 0.03); convertir a pct
        if "max_dev_pob_pct" in df_metrics.columns:
            if df_metrics["max_dev_pob_pct"].max() < 1.0:
                df_metrics["max_dev_pob_pct"] = df_metrics["max_dev_pob_pct"] * 100.0
        print(f"  Métricas SMC: {list(df_metrics.columns)}")
        return df_metrics
    else:
        print(f"  [INFO] Sin métricas CSV ({metrics_csv}) — retornando DataFrame vacío.")
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# Paso 6: comparar SMC vs ReCom
# ──────────────────────────────────────────────────────────────────────────────

def compare_smc_vs_recom(
    df_smc: pd.DataFrame,
    df_recom: pd.DataFrame,
    output_dir: str,
    scenario_name: str,
):
    """
    KS test entre distribuciones SMC y ReCom, y concordancia de rankings
    si hay suficientes métricas escalares comunes.
    """
    os.makedirs(output_dir, exist_ok=True)

    if df_smc.empty or df_recom.empty:
        print("  [WARN] Uno de los ensembles está vacío; comparación omitida.")
        return

    ensembles = {
        f"SMC_{scenario_name}":   df_smc,
        f"ReCom_{scenario_name}": df_recom,
    }

    # KS test por métrica
    print("\n--- KS test SMC vs ReCom ---")
    df_ks = cd.compare_sensitivity(ensembles)
    print(df_ks.to_string(index=False))

    ks_path = os.path.join(output_dir, "smc_vs_recom_ks.csv")
    df_ks.to_csv(ks_path, index=False)
    print(f"\n  Guardado: {ks_path}")

    # Figura KS
    _plot_ks_comparison(df_ks, output_dir)

    # Concordancia de rankings entre SMC y ReCom
    # Usamos mediana de cada métrica como score escalar por ensemble
    common_metrics = [c for c in df_smc.columns
                      if c in df_recom.columns
                      and pd.api.types.is_numeric_dtype(df_smc[c])]
    if len(common_metrics) >= 2:
        scores_smc   = {m: float(df_smc[m].median())   for m in common_metrics}
        scores_recom = {m: float(df_recom[m].median()) for m in common_metrics}

        conc = cd.ranking_concordance(scores_smc, scores_recom)
        print("\n--- Concordancia de ranking de métricas (SMC vs ReCom) ---")
        print(f"  τ de Kendall  : {conc['kendall_tau']:.4f}  (p={conc['kendall_pval']:.4f})")
        print(f"  ρ de Spearman : {conc['spearman_rho']:.4f}  (p={conc['spearman_pval']:.4f})")
        print(f"  Métricas comunes: {conc['n_comunes']}")
        if conc["discordantes"]:
            print(f"  Pares discordantes: {conc['discordantes']}")
        if conc.get("bajo_potencia_estadistica"):
            print("  [WARN] Pocos elementos comunes; p-valores no concluyentes.")

        df_conc = pd.DataFrame([{
            "par_a":           f"SMC_{scenario_name}",
            "par_b":           f"ReCom_{scenario_name}",
            "kendall_tau":     conc["kendall_tau"],
            "spearman_rho":    conc["spearman_rho"],
            "kendall_pval":    conc["kendall_pval"],
            "spearman_pval":   conc["spearman_pval"],
            "n_comunes":       conc["n_comunes"],
            "n_discordantes":  len(conc["discordantes"]),
        }])
        rank_path = os.path.join(output_dir, "smc_vs_recom_ranking.csv")
        df_conc.to_csv(rank_path, index=False)
        print(f"  Guardado: {rank_path}")
    else:
        print("  [INFO] Concordancia de ranking omitida: < 2 métricas comunes.")


def _plot_ks_comparison(df_ks: pd.DataFrame, output_dir: str):
    if df_ks.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = {"negligible": "#aec6cf", "pequeño": "#77c4a8",
              "moderado": "#f4a261", "grande": "#e76f51"}

    bar_colors = [colors.get(e, "#cccccc") for e in df_ks["efecto"]]
    ax.bar(range(len(df_ks)), df_ks["ks_stat"], color=bar_colors)
    ax.axhline(0.20, color="red",    linestyle="--", linewidth=1, label="Grande (0.20)")
    ax.axhline(0.10, color="orange", linestyle="--", linewidth=1, label="Moderado (0.10)")
    ax.axhline(0.05, color="green",  linestyle="--", linewidth=1, label="Pequeño (0.05)")
    ax.set_xticks(range(len(df_ks)))
    ax.set_xticklabels(df_ks["metrica"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Estadístico KS", fontsize=10)
    ax.set_title("Sensibilidad metodológica SMC vs ReCom (KS test por métrica)",
                 fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()

    fig_path = os.path.join(output_dir, "smc_vs_recom_ks.png")
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Guardado: {fig_path}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="H5 — Pipeline SMC (R/redist) y comparación con ReCom",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--base-dir", default=".", help="Directorio raíz del proyecto")
    p.add_argument("--regiones", type=int, nargs="+", default=[13],
                   help="Código(s) de región INE")
    p.add_argument("--scenario", default="apc_soft",
                   help="Nombre del escenario (prefijo para archivos)")
    p.add_argument("--layer", default="distrital",
                   help="Capa APC a cargar ('distrital' o 'apc')")
    p.add_argument("--id-col", default="ID_DIST",
                   help="Columna de ID de unidad")
    p.add_argument("--pop-col", default="personas",
                   help="Columna de población")
    p.add_argument("--n-districts", type=int, default=None,
                   help="Número de particiones territoriales a generar (NO "
                        "la magnitud electoral 3-8 de Ley 20.840). Default: "
                        "n_districts del escenario, si --scenario resuelve a "
                        "uno conocido en SCENARIOS o scenarios/<nombre>.yml.")
    p.add_argument("--n-sims", type=int, default=1_000,
                   help="Número de simulaciones SMC en el script R")
    p.add_argument("--extra-cols", nargs="*", default=None,
                   help="Columnas adicionales a incluir en el GPKG (ej. CUT N_COMUNA)")
    # Comparación con ReCom
    p.add_argument("--compare", action="store_true",
                   help="Comparar resultados SMC con ensemble ReCom")
    p.add_argument("--plans-csv", default=None,
                   help="Ruta al CSV de planes SMC exportado por R "
                        "(por defecto: <output_dir>/<scenario>_smc_planes.csv)")
    p.add_argument("--recom-ensemble", default=None,
                   help="Ruta a ensemble_stats.csv de ReCom para comparar")
    return p


def main():
    args  = build_parser().parse_args()
    base  = os.path.abspath(args.base_dir)

    for region_code in args.regiones:
        scenario_name = args.scenario
        output_dir    = _smc_output_dir(base, region_code, scenario_name)
        os.makedirs(output_dir, exist_ok=True)

        print(f"\n{'#'*70}")
        print(f"  Región {region_code} ({_region_nombre(region_code)})  |  SMC pipeline")
        print(f"  Escenario: {scenario_name}")
        print(f"  Salida: {output_dir}")
        print(f"{'#'*70}")

        # ── Pasos 1–2: datos y grafo ──────────────────────────────────────────
        gdf, G, adj, id_list = load_region_data(
            region_code=region_code,
            base_dir=base,
            layer=args.layer,
            id_col=args.id_col,
            pop_col=args.pop_col,
        )

        # ── Resolver n_districts: --n-districts explícito > scenario.n_districts ──
        n_districts = args.n_districts
        if n_districts is None:
            n_districts = _resolve_scenario_n_districts(scenario_name, base)
            if n_districts is None:
                raise ValueError(
                    f"No se pudo resolver n_districts: --n-districts no fue "
                    f"pasado y '{scenario_name}' no es un escenario conocido "
                    f"(SCENARIOS={list(SCENARIOS.keys())}) ni existe "
                    f"scenarios/{scenario_name}.yml. Pasa --n-districts "
                    f"explícitamente o usa un --scenario resoluble."
                )
            print(f"  n_districts desde escenario '{scenario_name}': {n_districts}")

        # ── Paso 3: exportar y generar script R ───────────────────────────────
        r_path = export_and_generate_script(
            gdf=gdf,
            adj=adj,
            id_list=id_list,
            id_col=args.id_col,
            pop_col=args.pop_col,
            n_districts=n_districts,
            n_sims=args.n_sims,
            output_dir=output_dir,
            scenario_name=scenario_name,
            extra_cols=args.extra_cols,
        )

        # ── Paso 4: instrucciones para R ──────────────────────────────────────
        print_r_instructions(r_path, output_dir, scenario_name)

        if not args.compare:
            print("\n  Listo. Ejecuta el script R y vuelve con --compare para comparar.")
            continue

        # ── Paso 5: importar planes SMC ───────────────────────────────────────
        plans_csv = args.plans_csv or os.path.join(
            output_dir, f"{scenario_name}_smc_planes.csv"
        )
        metrics_csv = os.path.join(output_dir, f"{scenario_name}_smc_metricas.csv")

        if not os.path.exists(plans_csv):
            print(f"\n  [WARN] No encontrado: {plans_csv}")
            print("  Ejecuta primero el script R generado y vuelve a correr con --compare.")
            continue

        df_smc = load_smc_ensemble(plans_csv, metrics_csv, id_list)

        # ── Paso 6: comparar con ReCom ────────────────────────────────────────
        if args.recom_ensemble:
            if not os.path.exists(args.recom_ensemble):
                print(f"\n  [WARN] No encontrado: {args.recom_ensemble}")
            else:
                df_recom = pd.read_csv(args.recom_ensemble)
                print(f"  Ensemble ReCom: {len(df_recom)} planes  ({args.recom_ensemble})")
                compare_smc_vs_recom(
                    df_smc=df_smc,
                    df_recom=df_recom,
                    output_dir=output_dir,
                    scenario_name=scenario_name,
                )
        else:
            print("\n  [INFO] Sin --recom-ensemble: comparación SMC vs ReCom omitida.")
            print("  Proporciona --recom-ensemble <ruta/ensemble_stats.csv> para comparar.")

    print("\nListo.")


if __name__ == "__main__":
    main()
