"""
scripts/redistritaje.py
=======================
Análisis de redistritaje con ReCom para una o más regiones de Chile.
Equivalente al Camino 3, parametrizable por región.

Outputs generados en datos/<REGION>/redistritaje/:
    rm_mejor_vs_peor.png
    rm_cadena_markov.png
    rm_ensemble_distribucion.png
    rm_mejor_balance.png
    rm_compacidad.png
    metricas_cadena.csv
    ensemble_stats.csv
    mejor_plan_detalle.csv

Uso:
    # Una región
    python scripts/redistritaje.py --base-dir . --regiones 13

    # Varias regiones
    python scripts/redistritaje.py --base-dir . --regiones 5,8,13

    # Todas las regiones
    python scripts/redistritaje.py --base-dir . --regiones todas

    # Con parámetros personalizados
    python scripts/redistritaje.py --base-dir . --regiones 13 \\
        --n-distritos 8 --pop-tol 0.15 --n-steps 10000
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

# Mapeo código región → nombre corto para carpetas
REGION_NOMBRES = {
    1:  "R01_TARAPACA",
    2:  "R02_ANTOFAGASTA",
    3:  "R03_ATACAMA",
    4:  "R04_COQUIMBO",
    5:  "R05_VALPARAISO",
    6:  "R06_OHIGGINS",
    7:  "R07_MAULE",
    8:  "R08_BIOBIO",
    9:  "R09_ARAUCANIA",
    10: "R10_LOS_LAGOS",
    11: "R11_AYSEN",
    12: "R12_MAGALLANES",
    13: "R13_METROPOLITANA",
    14: "R14_LOS_RIOS",
    15: "R15_ARICA",
    16: "R16_NUBLE",
}


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Redistritaje ReCom por región."
    )
    p.add_argument("--base-dir",   default=".",
                   help="Directorio raíz con SHP_APC2023_R*")
    p.add_argument("--output-dir", default=None,
                   help="Directorio base de salida (default: <base-dir>/datos)")
    p.add_argument("--regiones",   default="13",
                   help="Regiones a procesar: número, lista (5,8,13) o 'todas'")
    p.add_argument("--n-distritos", type=int, default=8,
                   help="Número de distritos electorales a generar (default: 8)")
    p.add_argument("--pop-tol",    type=float, default=0.15,
                   help="Tolerancia poblacional (default: 0.15 = ±15%%)")
    p.add_argument("--n-steps",    type=int, default=10000,
                   help="Pasos de la cadena ReCom (default: 10000)")
    p.add_argument("--seed",       type=int, default=42,
                   help="Semilla aleatoria (default: 42)")
    p.add_argument("--skip-viz",   action="store_true",
                   help="Omitir visualizaciones")
    return p.parse_args()


def parse_regiones(regiones_str: str) -> list[int]:
    """Parsea el argumento --regiones."""
    if regiones_str.strip().lower() == "todas":
        return list(range(1, 17))
    return [int(r.strip()) for r in regiones_str.split(",")]


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
) -> dict:
    """Ejecuta el análisis completo de redistritaje para una región."""

    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    out_dir     = os.path.join(output_base, region_name, "redistritaje")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"  Región {region_code:02d} — {region_name}")
    print(f"  Output: {out_dir}")
    print(f"{'#'*60}")

    # ── Cargar datos ──────────────────────────────────────────────────────────
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

    # Agregar población
    pop_urb = cd.aggregate_population(mz_urb, level="distrito", source="urbana")
    pop_ald = cd.aggregate_population(mz_ald, level="distrito", source="aldea")
    pop = (
        pop_urb.merge(pop_ald, on=["CUT","COD_DISTRITO"],
                      how="outer", suffixes=("_urb","_ald"))
        .fillna(0)
    )
    pop["viviendas"] = pop.get("viviendas_urb", 0) + pop.get("viviendas_ald", 0)
    distritos = distritos.merge(
        pop[["CUT","COD_DISTRITO","viviendas"]],
        on=["CUT","COD_DISTRITO"], how="left"
    ).fillna({"viviendas": 0})
    distritos["viviendas"] = distritos["viviendas"].astype(int)

    n_comunas  = distritos["CUT"].nunique()
    n_dist_apc = len(distritos)
    total_viv  = distritos["viviendas"].sum()
    ideal_pop  = total_viv / n_distritos

    print(f"\n  Distritos APC : {n_dist_apc}")
    print(f"  Comunas       : {n_comunas}")
    print(f"  Viviendas     : {total_viv:,}")
    print(f"  Ideal/distrito: {ideal_pop:,.0f}")

    if total_viv == 0:
        print("  ⚠ Sin datos de población — saltando redistritaje")
        return {"region": region_code, "status": "sin_poblacion"}

    # ── Grafo ─────────────────────────────────────────────────────────────────
    G, adj, ids = cd.build_graph(
        distritos, id_col="ID_DIST",
        method="queen", connect_islands=True,
        attr_cols=["N_COMUNA","N_DISTRITO","TIPO_DISTRITO","viviendas","CUT"],
    )

    ids_ordenados = distritos["ID_DIST"].tolist()

    def reconstruir_asignacion(plan_dict, graph, ids_list):
        result = {}
        for node, distrito in plan_dict.items():
            id_dist = graph.nodes[node].get("ID_DIST")
            if id_dist is None and isinstance(node, int) and node < len(ids_list):
                id_dist = ids_list[node]
            if id_dist is not None:
                result[id_dist] = distrito
        return result

    # ── ReCom ─────────────────────────────────────────────────────────────────
    try:
        import gerrychain as gc
        from gerrychain.proposals  import recom
        from gerrychain.constraints import contiguous
        from gerrychain.tree        import recursive_tree_part
        try:
            from gerrychain.accept import always_accept
        except ImportError:
            always_accept = gc.accept.always_accept
    except ImportError:
        print("  ⚠ gerrychain no instalado — omitiendo redistritaje")
        return {"region": region_code, "status": "sin_gerrychain"}

    np.random.seed(seed)

    distritos_gc = distritos.reset_index(drop=True).to_crs("EPSG:32719")
    graph = gc.Graph.from_geodataframe(
        distritos_gc, adjacency="queen",
        cols_to_add=["viviendas","CUT","N_COMUNA","TIPO_DISTRITO","ID_DIST"],
    )

    if not nx.is_connected(graph):
        print(f"  ⚠ Grafo no conexo ({nx.number_connected_components(graph)} componentes)")

    # Partición inicial
    print(f"\n  Buscando partición inicial...")
    best_assignment = None
    best_dev        = float("inf")

    for tol_init in [0.25, 0.35, 0.45, 0.60, 0.80]:
        for seed_try in range(5):
            try:
                np.random.seed(seed + seed_try)
                candidate = recursive_tree_part(
                    graph, parts=range(n_distritos),
                    pop_target=ideal_pop, pop_col="viviendas",
                    epsilon=tol_init, node_repeats=10,
                )
                pop_by_part = {}
                for node, part in candidate.items():
                    pop_by_part[part] = (pop_by_part.get(part, 0)
                                         + graph.nodes[node].get("viviendas", 0))
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
        return {"region": region_code, "status": "sin_particion"}

    print(f"  Partición inicial: tol=±{best_tol*100:.0f}%, desv={best_dev:.1f}%")

    updaters = {
        "population": gc.updaters.Tally("viviendas", alias="population"),
        "cut_edges":  gc.updaters.cut_edges,
    }
    partition = gc.Partition(graph=graph, assignment=best_assignment,
                              updaters=updaters)

    # Warm-up
    epsilon_warmup = max(best_dev / 100 + 0.05, pop_tol)
    N_WARMUP       = min(500, n_steps // 4)

    recom_warmup = partial(recom, pop_col="viviendas", pop_target=ideal_pop,
                            epsilon=epsilon_warmup, node_repeats=10)
    chain_warmup = gc.MarkovChain(
        proposal=recom_warmup, constraints=[contiguous],
        accept=always_accept, initial_state=partition,
        total_steps=N_WARMUP,
    )
    warmed_state = partition
    for step_w, state_w in enumerate(chain_warmup):
        warmed_state = state_w
        pop_w = list(state_w["population"].values())
        dev_w = max(abs(p - ideal_pop)/ideal_pop for p in pop_w) * 100
        if dev_w <= pop_tol * 100 * 1.5:
            break

    dev_warmed = max(
        abs(p - ideal_pop)/ideal_pop
        for p in warmed_state["population"].values()
    ) * 100

    # Cadena principal
    epsilon_recom  = max(dev_warmed / 100 + 0.02, pop_tol)
    pop_constraint = gc.constraints.within_percent_of_ideal_population(
        warmed_state, max(dev_warmed / 100 + 0.02, pop_tol)
    )
    recom_proposal = partial(recom, pop_col="viviendas", pop_target=ideal_pop,
                              epsilon=epsilon_recom, node_repeats=5)
    chain = gc.MarkovChain(
        proposal=recom_proposal, constraints=[contiguous, pop_constraint],
        accept=always_accept, initial_state=warmed_state,
        total_steps=n_steps,
    )

    print(f"\n  Iniciando ReCom: {n_steps:,} pasos · "
          f"{n_distritos} distritos · ±{pop_tol*100:.0f}%...")

    planes      = []
    metricas_mc = []
    for step, state in enumerate(chain):
        planes.append(dict(state.assignment))
        pop_vals = list(state["population"].values())
        max_dev  = max(abs(p - ideal_pop)/ideal_pop for p in pop_vals) * 100
        n_cuts   = len(state["cut_edges"])
        metricas_mc.append({
            "step": step, "cut_edges": n_cuts,
            "max_dev_pct": round(max_dev, 3),
        })
        if step % max(1, n_steps // 10) == 0:
            print(f"    Paso {step:6,} | cortes: {n_cuts:4d} | desv: {max_dev:.2f}%")

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

    print(f"  Planes válidos: {len(planes_validos)}/{n_steps}")
    planes = planes_validos

    # ── Métricas del ensemble ─────────────────────────────────────────────────
    df_ensemble = pd.DataFrame([
        {"plan_id": i, "max_dev_pob_pct": round(float(m["max_dev_pct"]), 3),
         "pp_promedio": np.nan, "cut_edges": int(m["cut_edges"])}
        for i, m in enumerate(metricas_mc[:len(planes)])
    ])

    # PP para muestra de 30 planes
    distritos_m = distritos.to_crs("EPSG:32719")
    for idx in df_ensemble.sample(min(30, len(df_ensemble)),
                                   random_state=seed).index:
        plan_id = int(df_ensemble.loc[idx, "plan_id"])
        a_m     = reconstruir_asignacion(planes[plan_id], graph, ids_ordenados)
        distritos_m["__d__"] = distritos_m["ID_DIST"].map(a_m)
        df_p = distritos_m[distritos_m["__d__"].notna()]
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

    # Score y mejor plan
    dev_norm = df_ensemble["max_dev_pob_pct"] / (df_ensemble["max_dev_pob_pct"].max() + 1e-10)
    cut_norm = df_ensemble["cut_edges"] / (df_ensemble["cut_edges"].max() + 1e-10)
    pp_col   = df_ensemble["pp_promedio"].fillna(df_ensemble["pp_promedio"].median())
    pp_range = pp_col.max() - pp_col.min() + 1e-10
    pp_norm  = (pp_col - pp_col.min()) / pp_range
    df_ensemble["score"] = -dev_norm + pp_norm.fillna(0) - cut_norm

    mejor_idx     = int(df_ensemble["score"].idxmax())
    mejor_plan_id = int(df_ensemble.loc[mejor_idx, "plan_id"])
    peor_idx      = int(df_ensemble["score"].idxmin())
    peor_plan_id  = int(df_ensemble.loc[peor_idx, "plan_id"])

    mejor_plan        = planes[mejor_plan_id]
    peor_plan         = planes[peor_plan_id]
    mejor_plan_mapped = reconstruir_asignacion(mejor_plan, graph, ids_ordenados)
    peor_plan_mapped  = reconstruir_asignacion(peor_plan,  graph, ids_ordenados)

    print(f"\n  Mejor plan (id={mejor_plan_id}): "
          f"desv={df_ensemble.loc[mejor_idx,'max_dev_pob_pct']:.2f}%, "
          f"cortes={df_ensemble.loc[mejor_idx,'cut_edges']}")

    # Resumen detallado del mejor plan
    distritos["__d__"] = distritos["ID_DIST"].map(mejor_plan_mapped)
    pop_summary = (
        distritos[distritos["__d__"].notna()]
        .groupby("__d__")
        .agg(viviendas=("viviendas","sum"),
             n_distritos_apc=("ID_DIST","count"),
             comunas=("CUT","nunique"))
        .reset_index()
    )
    pop_summary["desv_pct"] = (
        (pop_summary["viviendas"] - ideal_pop) / ideal_pop * 100
    ).round(2)
    pop_summary.columns = ["Distrito","Viviendas","N_dist_APC","N_comunas","Desv_%"]

    print(f"\n  Detalle del mejor plan:")
    print(pop_summary.to_string(index=False))

    # Guardar CSVs
    df_mc = pd.DataFrame(metricas_mc)
    df_mc.to_csv(os.path.join(out_dir, "metricas_cadena.csv"), index=False)
    df_ensemble.to_csv(os.path.join(out_dir, "ensemble_stats.csv"), index=False)
    pop_summary.to_csv(os.path.join(out_dir, "mejor_plan_detalle.csv"), index=False)

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not skip_viz:
        BG    = "#F8F7F4"
        pal_n = [plt.cm.Set2.colors[i % 8] for i in range(n_distritos)]

        def plot_single_plan(gdf, assignment, title, ax):
            gdf = gdf.copy().to_crs("EPSG:32719")
            gdf["__d__"] = gdf["ID_DIST"].map(assignment)
            gdf = gdf[gdf["__d__"].notna()]
            if gdf.empty:
                ax.text(0.5, 0.5, "sin datos", ha="center", va="center",
                        transform=ax.transAxes)
                ax.axis("off")
                return
            districts = sorted(gdf["__d__"].unique())
            cmap = {d: pal_n[i % len(pal_n)] for i, d in enumerate(districts)}
            for d in districts:
                gdf[gdf["__d__"] == d].plot(
                    ax=ax, color=cmap[d], edgecolor="#CCCCCC", linewidth=0.1
                )
            try:
                gdf.dissolve("__d__").boundary.plot(
                    ax=ax, color="#333333", linewidth=0.8
                )
            except Exception:
                pass
            ax.set_title(title, fontsize=9, fontweight="bold", color="#1a1a18")
            ax.axis("off")

        # Figura 1: mejor vs peor
        fig1, axes = plt.subplots(1, 2, figsize=(16, 10))
        fig1.patch.set_facecolor(BG)
        for ax in axes:
            ax.set_facecolor(BG)
        plot_single_plan(
            distritos, mejor_plan_mapped,
            f"Mejor (id={mejor_plan_id}) "
            f"desv={df_ensemble.loc[mejor_idx,'max_dev_pob_pct']:.1f}%",
            axes[0]
        )
        plot_single_plan(
            distritos, peor_plan_mapped,
            f"Peor (id={peor_plan_id}) "
            f"desv={df_ensemble.loc[peor_idx,'max_dev_pob_pct']:.1f}%",
            axes[1]
        )
        fig1.suptitle(
            f"{region_name} — Redistritaje ReCom  "
            f"({n_distritos} distritos · {n_steps:,} pasos · ±{pop_tol*100:.0f}%)",
            fontsize=12, fontweight="bold"
        )
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "mejor_vs_peor.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 2: cadena de Markov
        fig2, axes = plt.subplots(1, 2, figsize=(16, 5))
        fig2.patch.set_facecolor(BG)
        for ax in axes:
            ax.set_facecolor(BG)
            ax.spines[["top","right"]].set_visible(False)
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
        fig2.suptitle(f"Cadena de Markov ReCom — {region_name}",
                      fontsize=12, fontweight="bold")
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "cadena_markov.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 3: distribución ensemble
        fig3, axes = plt.subplots(1, 3, figsize=(18, 5))
        fig3.patch.set_facecolor(BG)
        for ax, col, color, label in zip(
            axes,
            ["pp_promedio","max_dev_pob_pct","cut_edges"],
            ["#1D9E75","#D85A30","#BA7517"],
            ["Polsby-Popper","Desv. pob. máx (%)","Aristas cortadas"],
        ):
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
            ax.spines[["top","right"]].set_visible(False)
        fig3.suptitle(f"Distribución ensemble — {region_name} ({len(planes)} planes)",
                      fontsize=12, fontweight="bold")
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "ensemble_distribucion.png"),
                    dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close()

        # Figura 4: balance poblacional
        cd.plot_plan(
            distritos, assignment=mejor_plan_mapped,
            id_col="ID_DIST", pop_col="viviendas",
            title=f"{region_name} — Mejor plan (id={mejor_plan_id})",
            show_pop_balance=True,
            save_path=os.path.join(out_dir, "mejor_balance.png"),
        )
        plt.close("all")

        # Figura 5: compacidad
        metricas_dist = cd.all_compactness(distritos, id_col="ID_DIST")
        cd.plot_compactness(
            distritos, metricas_dist, id_col="ID_DIST",
            metric="polsby_popper",
            title=f"{region_name} — Compacidad distrital",
            save_path=os.path.join(out_dir, "compacidad.png"),
        )
        plt.close("all")

        print(f"\n  Figuras guardadas en {out_dir}/")

    return {
        "region":       region_code,
        "region_name":  region_name,
        "status":       "ok",
        "n_distritos":  n_dist_apc,
        "n_planes":     len(planes),
        "mejor_plan_id": mejor_plan_id,
        "mejor_desv":   df_ensemble.loc[mejor_idx, "max_dev_pob_pct"],
        "out_dir":      out_dir,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args    = parse_args()
    base_dir = args.base_dir
    output_base = args.output_dir or os.path.join(base_dir, "datos")
    regiones    = parse_regiones(args.regiones)

    print(f"\nchiledist — Redistritaje")
    print(f"  base_dir    : {base_dir}")
    print(f"  output_base : {output_base}")
    print(f"  regiones    : {regiones}")
    print(f"  n_distritos : {args.n_distritos}")
    print(f"  pop_tol     : ±{args.pop_tol*100:.0f}%")
    print(f"  n_steps     : {args.n_steps:,}")

    resultados = []
    for r in regiones:
        try:
            res = analizar_region(
                region_code=r,
                base_dir=base_dir,
                output_base=output_base,
                n_distritos=args.n_distritos,
                pop_tol=args.pop_tol,
                n_steps=args.n_steps,
                seed=args.seed,
                skip_viz=args.skip_viz,
            )
            resultados.append(res)
        except Exception as e:
            import traceback
            print(f"\n  ⚠ Error en región {r}: {e}")
            traceback.print_exc()
            resultados.append({"region": r, "status": "error", "error": str(e)})

    # Resumen final
    print(f"\n{'='*60}")
    print(f" RESUMEN FINAL")
    print(f"{'='*60}")
    df_res = pd.DataFrame(resultados)
    print(df_res[["region","status","n_planes","mejor_desv"]
                 if "n_planes" in df_res.columns
                 else ["region","status"]].to_string(index=False))

    resumen_path = os.path.join(output_base, "redistritaje_resumen.csv")
    df_res.to_csv(resumen_path, index=False)
    print(f"\nResumen guardado: {resumen_path}")


if __name__ == "__main__":
    main()
