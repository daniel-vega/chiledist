"""
scripts/autocorrelacion.py
==========================
Análisis de autocorrelación espacial por región.
Equivalente al Camino 2, parametrizable por región.

Outputs generados en datos/<REGION>/autocorrelacion/:
    moran_scatter.png
    lisa_mapas.png
    getisord_mapas.png
    correlograma.png
    resultados.csv
    moran_global.csv

Uso:
    python scripts/autocorrelacion.py --base-dir . --regiones 13
    python scripts/autocorrelacion.py --base-dir . --regiones 5,8,13
    python scripts/autocorrelacion.py --base-dir . --regiones todas
"""

import argparse
import os
import sys
import warnings
warnings.filterwarnings("ignore", message=".*island.*")
warnings.filterwarnings("ignore", message=".*WARNING.*")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import scipy.sparse as sp

import chiledist as cd

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

LISA_COLORS = {
    "HH": "#D7191C", "LL": "#2C7BB6",
    "LH": "#ABD9E9", "HL": "#FDAE61",
    "ns": "#EEEEEE",
}

BG = "#F8F7F4"


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Autocorrelación espacial por región."
    )
    p.add_argument("--base-dir",    default=".",
                   help="Directorio raíz con SHP_APC2023_R*")
    p.add_argument("--output-dir",  default=None,
                   help="Directorio base de salida (default: <base-dir>/datos)")
    p.add_argument("--regiones",    default="13",
                   help="Regiones: número, lista (5,8,13) o 'todas'")
    p.add_argument("--variables",   default="viviendas,densidad_viv_km2,polsby_popper",
                   help="Variables a analizar (default: viviendas,densidad_viv_km2,polsby_popper)")
    p.add_argument("--max-order",   type=int, default=7,
                   help="Orden máximo del correlograma (default: 7)")
    p.add_argument("--permutaciones", type=int, default=999,
                   help="Permutaciones para Moran (default: 999)")
    p.add_argument("--skip-viz",    action="store_true",
                   help="Omitir visualizaciones")
    p.add_argument("--nacional",    action="store_true",
                   help="Usar matrices nacionales de datos/nacional/matrices/")
    return p.parse_args()


def parse_regiones(s: str) -> list[int] | str:
    """
    Parsea el argumento --regiones.
    Retorna lista de enteros, o la string 'nacional' para análisis conjunto.
    """
    s = s.strip().lower()
    if s == "todas":
        return list(range(1, 17))
    if s == "nacional":
        return "nacional"   # señal especial para analizar todo Chile junto
    return [int(r.strip()) for r in s.split(",")]


# ──────────────────────────────────────────────────────────────────────────────
# Funciones de análisis
# ──────────────────────────────────────────────────────────────────────────────

def spatial_correlogram(y, adj, max_order=7):
    """Correlograma espacial usando multiplicación de matrices sparse."""
    import scipy.sparse as sp_loc
    from libpysal.weights import WSP
    from esda.moran import Moran

    A   = (adj > 0).astype(np.float64)
    A_k = A.copy()
    seen = A.copy()

    results = []
    for k in range(1, max_order + 1):
        if k > 1:
            A_next = A_k.dot(A)
            A_next = (A_next > 0).astype(np.float64)
            A_next.setdiag(0)
            A_k  = A_next - (seen > 0).astype(np.float64)
            A_k.data[A_k.data < 0] = 0
            A_k.eliminate_zeros()
            seen = seen + A_k

        row_sums = np.array(A_k.sum(axis=1)).flatten()
        row_sums[row_sums == 0] = 1
        W_norm = sp_loc.diags(1.0 / row_sums).dot(A_k)

        try:
            w_k = WSP(W_norm).to_W()
            w_k.transform = "r"
            mi_k = Moran(y, w_k, permutations=199)
            results.append({
                "orden":   k,
                "moran_I": mi_k.I,
                "p_sim":   mi_k.p_sim,
                "sig":     mi_k.p_sim < 0.05,
            })
        except Exception:
            break

    return (pd.DataFrame(results) if results
            else pd.DataFrame(columns=["orden","moran_I","p_sim","sig"]))


def get_lisa_color(row, var_name):
    if not row[f"lisa_sig_{var_name}"]:
        return LISA_COLORS["ns"]
    q = row[f"lisa_q_{var_name}"]
    return LISA_COLORS.get({1:"HH",2:"LH",3:"LL",4:"HL"}.get(q,"ns"), LISA_COLORS["ns"])


# ──────────────────────────────────────────────────────────────────────────────
# Análisis por región
# ──────────────────────────────────────────────────────────────────────────────

def _generar_figuras_autocorr(
    distritos, adj, resultados_moran, lisa_results,
    vars_disponibles, w, max_order, out_dir, region_label
):
    """Genera las 4 figuras de autocorrelación. Compartida por analizar_region y analizar_nacional."""
    from libpysal.weights.spatial_lag import lag_spatial
    from shapely.geometry import box as shapely_box

    var_names = list(vars_disponibles.keys())

    # Figura 1: Moran scatter
    n_vars = len(var_names)
    fig1, axes = plt.subplots(1, n_vars, figsize=(6*n_vars, 6))
    fig1.patch.set_facecolor(BG)
    if n_vars == 1:
        axes = [axes]
    for ax, var_name in zip(axes, var_names):
        ax.set_facecolor(BG)
        mi  = resultados_moran[var_name]
        y   = vars_disponibles[var_name]
        y_s = (y - y.mean()) / (y.std() + 1e-10)
        lag = lag_spatial(w, y_s)
        ax.scatter(y_s, lag, color="#1D9E75", alpha=0.4, s=8, linewidths=0)
        ax.axhline(0, color="#888880", linewidth=0.8)
        ax.axvline(0, color="#888880", linewidth=0.8)
        x_line = np.linspace(y_s.min(), y_s.max(), 100)
        ax.plot(x_line, mi.I * x_line, color="#D85A30", linewidth=1.5,
                label=f"I={mi.I:.3f} (p={mi.p_sim:.3f})")
        sig = "***" if mi.p_sim<0.001 else "**" if mi.p_sim<0.01 else "*"
        ax.set_title(f"{var_name}\nI={mi.I:.4f} {sig}", fontsize=10, fontweight="bold")
        ax.set_xlabel("Variable estandarizada")
        ax.set_ylabel("Lag espacial")
        ax.legend(fontsize=8)
        ax.spines[["top","right"]].set_visible(False)
    fig1.suptitle(f"Diagramas de Moran — {region_label}", fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "moran_scatter.png"), dpi=150,
                bbox_inches="tight", facecolor=BG)
    plt.close()

    # Figura 2: LISA
    vars_lisa = var_names[:2]
    fig2, axes = plt.subplots(1, len(vars_lisa), figsize=(10*len(vars_lisa), 14))
    fig2.patch.set_facecolor(BG)
    if len(vars_lisa) == 1:
        axes = [axes]
    for ax, var_name in zip(axes, vars_lisa):
        ax.set_facecolor(BG)
        colors = distritos.apply(lambda r: get_lisa_color(r, var_name), axis=1)
        distritos.plot(ax=ax, color=colors, edgecolor="#AAAAAA", linewidth=0.1)
        handles = [
            mpatches.Patch(color=c, label=label)
            for label, c in LISA_COLORS.items() if label != "ns"
        ] + [mpatches.Patch(color=LISA_COLORS["ns"], label="No significativo")]
        ax.legend(handles=handles, loc="lower left", fontsize=8,
                  framealpha=0.9, edgecolor="none")
        ax.set_title(f"LISA — {var_name}\n(p < 0.05)", fontsize=11, fontweight="bold")
        ax.axis("off")
    fig2.suptitle(f"LISA — {region_label}", fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "lisa_mapas.png"), dpi=150,
                bbox_inches="tight", facecolor=BG)
    plt.close()

    # Figura 3: G* con zoom
    vars_gstar    = var_names[:2]
    tiene_hotspots = any(
        bool(((distritos[f"gstar_{v}"] > 1.96) &
               distritos[f"gstar_sig_{v}"]).any())
        for v in vars_gstar
        if f"gstar_{v}" in distritos.columns and f"gstar_sig_{v}" in distritos.columns
    )
    n_rows = 2 if tiene_hotspots else 1
    fig3, axes = plt.subplots(n_rows, len(vars_gstar),
                               figsize=(10*len(vars_gstar), 12*n_rows))
    fig3.patch.set_facecolor(BG)
    if n_rows == 1:
        axes = axes.reshape(1, -1)
    if len(vars_gstar) == 1:
        axes = axes.reshape(-1, 1)

    for col, var_name in enumerate(vars_gstar):
        if f"gstar_{var_name}" not in distritos.columns:
            continue
        hotspots  = distritos[(distritos[f"gstar_{var_name}"] > 1.96) &
                               distritos[f"gstar_sig_{var_name}"]]
        coldspots = distritos[(distritos[f"gstar_{var_name}"] < -1.96) &
                               distritos[f"gstar_sig_{var_name}"]]
        for row in range(n_rows):
            ax = axes[row, col]
            ax.set_facecolor(BG)
            distritos.plot(column=f"gstar_{var_name}", ax=ax,
                           cmap="RdBu_r", vmin=-4, vmax=4,
                           edgecolor="#CCCCCC", linewidth=0.05,
                           legend=(row == 0),
                           legend_kwds={"label": "Z-score G*", "shrink": 0.5})
            if len(hotspots):
                hotspots.plot(ax=ax, facecolor="none", edgecolor="#8B0000", linewidth=1.0)
            if len(coldspots):
                coldspots.plot(ax=ax, facecolor="none", edgecolor="#00008B", linewidth=1.0)
            if row == 1 and len(hotspots) > 0:
                hs_m = hotspots.to_crs("EPSG:32719")
                minx, miny, maxx, maxy = hs_m.total_bounds
                dx = (maxx - minx) * 0.3
                dy = (maxy - miny) * 0.3
                bbox_gdf = gpd.GeoDataFrame(
                    geometry=[shapely_box(minx-dx, miny-dy, maxx+dx, maxy+dy)],
                    crs="EPSG:32719"
                ).to_crs(distritos.crs)
                bx = bbox_gdf.total_bounds
                ax.set_xlim(bx[0], bx[2])
                ax.set_ylim(bx[1], bx[3])
                ax.set_title(f"G* zoom — {var_name}\nHotspots: {len(hotspots)} Coldspots: {len(coldspots)}",
                             fontsize=9, fontweight="bold")
            else:
                ax.set_title(f"G* — {var_name}\nHotspots: {len(hotspots)} Coldspots: {len(coldspots)}",
                             fontsize=9, fontweight="bold")
            ax.axis("off")
    fig3.suptitle(f"Getis-Ord G* — {region_label}", fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "getisord_mapas.png"), dpi=150,
                bbox_inches="tight", facecolor=BG)
    plt.close()

    # Figura 4: Correlograma
    print(f"  Calculando correlograma (orden 1-{max_order})...")
    vars_correl = var_names[:2]
    fig4, axes  = plt.subplots(1, len(vars_correl), figsize=(7*len(vars_correl), 5))
    fig4.patch.set_facecolor(BG)
    if len(vars_correl) == 1:
        axes = [axes]
    for ax, var_name in zip(axes, vars_correl):
        ax.set_facecolor(BG)
        y   = vars_disponibles[var_name]
        y_s = (y - y.mean()) / (y.std() + 1e-10)
        corr = spatial_correlogram(y_s, adj, max_order=max_order)
        if corr.empty:
            ax.text(0.5, 0.5, "no disponible", ha="center", va="center",
                    transform=ax.transAxes)
            ax.axis("off")
            continue
        colors_bar = ["#D85A30" if s else "#AAAAAA" for s in corr["sig"]]
        ax.bar(corr["orden"], corr["moran_I"], color=colors_bar,
               edgecolor="white", linewidth=0.5)
        ax.axhline(0, color="#333333", linewidth=0.8)
        ax.set_xlabel("Orden de vecindad")
        ax.set_ylabel("I de Moran")
        ax.set_title(f"Correlograma — {var_name}\n(rojo = p<0.05)",
                     fontsize=10, fontweight="bold")
        ax.spines[["top","right"]].set_visible(False)
        ax.set_xticks(corr["orden"])
    fig4.suptitle(f"Correlograma espacial — {region_label}",
                  fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "correlograma.png"), dpi=150,
                bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"  Figuras guardadas en {out_dir}/")


def analizar_region(
    region_code: int,
    base_dir: str,
    output_base: str,
    variables_list: list[str],
    max_order: int,
    permutaciones: int,
    skip_viz: bool,
    usar_nacional: bool,
) -> dict:
    """Ejecuta el análisis de autocorrelación para una región."""
    try:
        from libpysal.weights import WSP
        from libpysal.weights.spatial_lag import lag_spatial
        from esda.moran import Moran, Moran_Local
        from esda.getisord import G_Local
    except ImportError as e:
        print(f"  ⚠ Dependencia faltante: {e}")
        print("  Instala con: pip install esda")
        return {"region": region_code, "status": "sin_esda"}

    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    out_dir     = os.path.join(output_base, region_name, "autocorrelacion")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"  Región {region_code:02d} — {region_name}")
    print(f"  Output: {out_dir}")
    print(f"{'#'*60}")

    # ── Cargar datos ──────────────────────────────────────────────────────────
    if usar_nacional:
        # Usar matrices nacionales y filtrar por región
        mat_dir = os.path.join(output_base, "nacional", "matrices")
        try:
            adj    = sp.load_npz(os.path.join(mat_dir, "matriz_distrital_matriz.npz"))
            indice = pd.read_csv(os.path.join(mat_dir, "matriz_distrital_indice.csv"))
            pop    = pd.read_csv(os.path.join(mat_dir, "poblacion_distritos.csv"))
        except FileNotFoundError:
            print("  ⚠ Matrices nacionales no encontradas — ejecuta setup.py primero")
            return {"region": region_code, "status": "sin_matrices"}

        # Filtrar por región
        mask_reg = indice["N_REGION"].str.contains(
            str(region_code), na=False
        ) if "N_REGION" in indice.columns else pd.Series(True, index=indice.index)

        # Cargar geometrías de la región
        distritos = cd.load_layer("distrital", base_dir=base_dir,
                                   regions=[region_code])
    else:
        # Construir grafo regional
        distritos = cd.load_layer("distrital", base_dir=base_dir,
                                   regions=[region_code])
        mz_urb    = cd.load_layer("manzana_urbana", base_dir=base_dir,
                                   regions=[region_code])
        mz_ald    = cd.load_layer("manzana_aldea",  base_dir=base_dir,
                                   regions=[region_code])

        pop_urb = cd.aggregate_population(mz_urb, level="distrito", source="urbana")
        pop_ald = cd.aggregate_population(mz_ald, level="distrito", source="aldea")
        pop_df  = (
            pop_urb.merge(pop_ald, on=["CUT","COD_DISTRITO"],
                          how="outer", suffixes=("_urb","_ald"))
            .fillna(0)
        )
        pop_df["viviendas"] = (pop_df.get("viviendas_urb", 0)
                                + pop_df.get("viviendas_ald", 0))
        distritos = distritos.merge(
            pop_df[["CUT","COD_DISTRITO","viviendas"]],
            on=["CUT","COD_DISTRITO"], how="left"
        ).fillna({"viviendas": 0})
        distritos["viviendas"] = distritos["viviendas"].astype(int)

        _, adj, ids = cd.build_graph(distritos, id_col="ID_DIST",
                                      connect_islands=True)
        indice = distritos[["ID_DIST","N_DISTRITO","N_COMUNA",
                             "N_REGION","TIPO_DISTRITO","viviendas"]].copy()
        indice["fila_col"] = range(len(indice))

    # Área y densidad
    distritos_m = distritos.to_crs("EPSG:32719")
    distritos["area_km2"] = distritos_m.geometry.area / 1e6
    distritos["densidad_viv_km2"] = (
        distritos["viviendas"] /
        distritos["area_km2"].replace(0, np.nan)
    ).fillna(0)

    # Compacidad
    metricas = cd.all_compactness(distritos, id_col="ID_DIST")
    distritos = distritos.merge(
        metricas[["ID_DIST","polsby_popper"]], on="ID_DIST", how="left"
    )

    # Asegurar orden alineado con la matriz
    distritos = distritos.set_index("ID_DIST").loc[
        indice["ID_DIST"]
    ].reset_index()

    # ── Pesos espaciales ─────────────────────────────────────────────────────
    w = WSP(adj).to_W()
    w.transform = "r"
    print(f"  Pesos: {w.n} unidades · islas: {len(w.islands)}")

    # ── Variables disponibles ─────────────────────────────────────────────────
    vars_disponibles = {
        v: distritos[v].values.astype(float)
        for v in variables_list
        if v in distritos.columns
    }
    if not vars_disponibles:
        print(f"  ⚠ Ninguna variable disponible: {variables_list}")
        return {"region": region_code, "status": "sin_variables"}

    # ── Moran Global ─────────────────────────────────────────────────────────
    print(f"\n  Índice de Moran Global:")
    resultados_moran = {}
    for var_name, y in vars_disponibles.items():
        mi = Moran(y, w, permutations=permutaciones)
        resultados_moran[var_name] = mi
        sig  = "***" if mi.p_sim<0.001 else "**" if mi.p_sim<0.01 else "*" if mi.p_sim<0.05 else "ns"
        tipo = "CLUSTERING" if mi.I > 0 else "DISPERSIÓN"
        print(f"    {var_name:25s}: I={mi.I:.4f} {sig}  p={mi.p_sim:.4f}  → {tipo}")

    # ── LISA ──────────────────────────────────────────────────────────────────
    print(f"\n  LISA (p < 0.05):")
    lisa_results = {}
    for var_name, y in vars_disponibles.items():
        lisa = Moran_Local(y, w, permutations=permutaciones, seed=42)
        lisa_results[var_name] = lisa
        sig_mask = lisa.p_sim < 0.05
        quad_labels = {1:"HH",2:"LH",3:"LL",4:"HL"}
        counts = {l: ((lisa.q == q) & sig_mask).sum() for q, l in quad_labels.items()}
        print(f"    {var_name:25s}: HH={counts['HH']:4d} LL={counts['LL']:4d} "
              f"LH={counts['LH']:4d} HL={counts['HL']:4d} "
              f"ns={(~sig_mask).sum():4d}")
        distritos[f"lisa_q_{var_name}"]   = lisa.q
        distritos[f"lisa_p_{var_name}"]   = lisa.p_sim
        distritos[f"lisa_sig_{var_name}"] = sig_mask

    # ── Getis-Ord G* ─────────────────────────────────────────────────────────
    print(f"\n  Getis-Ord G*:")
    w_b = WSP(adj).to_W()
    for var_name, y in vars_disponibles.items():
        g = G_Local(y, w_b, transform="b", permutations=permutaciones, seed=42)
        distritos[f"gstar_{var_name}"]     = g.Zs
        distritos[f"gstar_sig_{var_name}"] = g.p_sim < 0.05
        hotspots  = (g.Zs > 1.96)  & (g.p_sim < 0.05)
        coldspots = (g.Zs < -1.96) & (g.p_sim < 0.05)
        print(f"    {var_name:25s}: hotspots={hotspots.sum():4d} coldspots={coldspots.sum():4d}")

    # ── Guardar resultados ────────────────────────────────────────────────────
    cols_export = ["ID_DIST","CUT","N_DISTRITO","N_COMUNA","N_REGION",
                   "TIPO_DISTRITO","viviendas","area_km2","densidad_viv_km2"]
    for v in vars_disponibles:
        for suffix in [f"lisa_q_{v}",f"lisa_p_{v}",f"lisa_sig_{v}",
                       f"gstar_{v}",f"gstar_sig_{v}"]:
            if suffix in distritos.columns:
                cols_export.append(suffix)

    distritos[[c for c in cols_export if c in distritos.columns]].to_csv(
        os.path.join(out_dir, "resultados.csv"), index=False
    )

    pd.DataFrame([
        {"variable": k, "moran_I": v.I, "p_sim": v.p_sim,
         "z_norm": v.z_norm, "significativo": v.p_sim < 0.05,
         "tipo": "clustering" if v.I > 0 else "dispersión"}
        for k, v in resultados_moran.items()
    ]).to_csv(os.path.join(out_dir, "moran_global.csv"), index=False)

    print(f"  Guardado: resultados.csv, moran_global.csv")

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not skip_viz:
        _generar_figuras_autocorr(
            distritos, adj, resultados_moran, lisa_results,
            vars_disponibles, w, max_order, out_dir,
            region_label=region_name
        )

    return {
        "region":      region_code,
        "region_name": region_name,
        "status":      "ok",
        "n_distritos": len(distritos),
        "moran_viviendas": resultados_moran.get(
            "viviendas", type("", (), {"I": np.nan})()
        ).I,
        "out_dir": out_dir,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Análisis nacional (todas las regiones juntas)
# ──────────────────────────────────────────────────────────────────────────────

def analizar_nacional(
    base_dir: str,
    output_base: str,
    variables_list: list,
    max_order: int,
    permutaciones: int,
    skip_viz: bool,
) -> dict:
    """
    Carga todas las regiones juntas y ejecuta el análisis de
    autocorrelación sobre el territorio nacional completo.
    Equivalente al camino2_autocorrelacion.py original.
    """
    try:
        from libpysal.weights import WSP
        from libpysal.weights.spatial_lag import lag_spatial
        from esda.moran import Moran, Moran_Local
        from esda.getisord import G_Local
    except ImportError as e:
        print(f"  ⚠ Dependencia faltante: {e}")
        return {"region": "nacional", "status": "sin_esda"}

    out_dir = os.path.join(output_base, "nacional", "autocorrelacion")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"  Análisis NACIONAL — todas las regiones")
    print(f"  Output: {out_dir}")
    print(f"{'#'*60}")

    # Cargar todas las regiones
    print("\n  Cargando capas nacionales...")
    distritos = cd.load_layer("distrital", base_dir=base_dir)
    mz_urb    = cd.load_layer("manzana_urbana", base_dir=base_dir)
    mz_ald    = cd.load_layer("manzana_aldea",  base_dir=base_dir)

    pop_urb = cd.aggregate_population(mz_urb, level="distrito", source="urbana")
    pop_ald = cd.aggregate_population(mz_ald, level="distrito", source="aldea")
    pop_df  = (
        pop_urb.merge(pop_ald, on=["CUT","COD_DISTRITO"],
                      how="outer", suffixes=("_urb","_ald"))
        .fillna(0)
    )
    pop_df["viviendas"] = (pop_df.get("viviendas_urb", 0)
                            + pop_df.get("viviendas_ald", 0))
    distritos = distritos.merge(
        pop_df[["CUT","COD_DISTRITO","viviendas"]],
        on=["CUT","COD_DISTRITO"], how="left"
    ).fillna({"viviendas": 0})
    distritos["viviendas"] = distritos["viviendas"].astype(int)

    # Área y densidad
    distritos_m = distritos.to_crs("EPSG:32719")
    distritos["area_km2"] = distritos_m.geometry.area / 1e6
    distritos["densidad_viv_km2"] = (
        distritos["viviendas"] /
        distritos["area_km2"].replace(0, np.nan)
    ).fillna(0)

    # Compacidad
    metricas  = cd.all_compactness(distritos, id_col="ID_DIST")
    distritos = distritos.merge(
        metricas[["ID_DIST","polsby_popper"]], on="ID_DIST", how="left"
    )

    print(f"  Distritos  : {len(distritos):,}")
    print(f"  Viviendas  : {distritos['viviendas'].sum():,}")

    # Construir grafo nacional
    print("  Construyendo grafo...")
    _, adj, ids = cd.build_graph(distritos, id_col="ID_DIST",
                                  connect_islands=True)
    indice = distritos[["ID_DIST","N_DISTRITO","N_COMUNA",
                         "N_REGION","TIPO_DISTRITO","viviendas"]].copy()
    indice["fila_col"] = range(len(indice))

    # Alinear orden con la matriz
    distritos = distritos.set_index("ID_DIST").loc[
        indice["ID_DIST"]
    ].reset_index()

    # Pesos
    w = WSP(adj).to_W()
    w.transform = "r"
    print(f"  Pesos: {w.n} unidades · islas: {len(w.islands)}")

    # Variables disponibles
    vars_disponibles = {
        v: distritos[v].values.astype(float)
        for v in variables_list
        if v in distritos.columns
    }

    # Moran Global
    print(f"\n  Índice de Moran Global:")
    resultados_moran = {}
    for var_name, y in vars_disponibles.items():
        mi  = Moran(y, w, permutations=permutaciones)
        resultados_moran[var_name] = mi
        sig = "***" if mi.p_sim<0.001 else "**" if mi.p_sim<0.01 else "*" if mi.p_sim<0.05 else "ns"
        print(f"    {var_name:25s}: I={mi.I:.4f} {sig}  p={mi.p_sim:.4f}")

    # LISA
    print(f"\n  LISA (p < 0.05):")
    lisa_results = {}
    for var_name, y in vars_disponibles.items():
        lisa = Moran_Local(y, w, permutations=permutaciones, seed=42)
        lisa_results[var_name] = lisa
        sig_mask = lisa.p_sim < 0.05
        ql = {1:"HH",2:"LH",3:"LL",4:"HL"}
        counts = {l: ((lisa.q == q) & sig_mask).sum() for q, l in ql.items()}
        print(f"    {var_name:25s}: HH={counts['HH']:4d} LL={counts['LL']:4d} "
              f"LH={counts['LH']:4d} HL={counts['HL']:4d}")
        distritos[f"lisa_q_{var_name}"]   = lisa.q
        distritos[f"lisa_p_{var_name}"]   = lisa.p_sim
        distritos[f"lisa_sig_{var_name}"] = sig_mask

    # G*
    print(f"\n  Getis-Ord G*:")
    w_b = WSP(adj).to_W()
    for var_name, y in vars_disponibles.items():
        g = G_Local(y, w_b, transform="b", permutations=permutaciones, seed=42)
        distritos[f"gstar_{var_name}"]     = g.Zs
        distritos[f"gstar_sig_{var_name}"] = g.p_sim < 0.05
        hs = (g.Zs > 1.96) & (g.p_sim < 0.05)
        cs = (g.Zs < -1.96) & (g.p_sim < 0.05)
        print(f"    {var_name:25s}: hotspots={hs.sum():4d} coldspots={cs.sum():4d}")

    # Guardar resultados
    cols_export = ["ID_DIST","CUT","N_DISTRITO","N_COMUNA","N_REGION",
                   "TIPO_DISTRITO","viviendas","area_km2","densidad_viv_km2"]
    for v in vars_disponibles:
        for s in [f"lisa_q_{v}",f"lisa_p_{v}",f"lisa_sig_{v}",
                  f"gstar_{v}",f"gstar_sig_{v}"]:
            if s in distritos.columns:
                cols_export.append(s)
    distritos[[c for c in cols_export if c in distritos.columns]].to_csv(
        os.path.join(out_dir, "resultados.csv"), index=False
    )
    pd.DataFrame([
        {"variable": k, "moran_I": v.I, "p_sim": v.p_sim,
         "z_norm": v.z_norm, "significativo": v.p_sim < 0.05,
         "tipo": "clustering" if v.I > 0 else "dispersión"}
        for k, v in resultados_moran.items()
    ]).to_csv(os.path.join(out_dir, "moran_global.csv"), index=False)
    print(f"  Guardado: resultados.csv, moran_global.csv")

    # Visualizaciones
    if not skip_viz:
        _generar_figuras_autocorr(
            distritos, adj, resultados_moran, lisa_results,
            vars_disponibles, w, max_order, out_dir,
            region_label="Chile nacional"
        )

    return {
        "region": "nacional", "region_name": "nacional",
        "status": "ok", "n_distritos": len(distritos),
        "moran_viviendas": resultados_moran.get(
            "viviendas", type("",(),{"I":np.nan})()).I,
        "out_dir": out_dir,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args        = parse_args()
    base_dir    = args.base_dir
    output_base = args.output_dir or os.path.join(base_dir, "datos")
    regiones    = parse_regiones(args.regiones)
    variables   = [v.strip() for v in args.variables.split(",")]

    print(f"\nchiledist — Autocorrelación espacial")
    print(f"  base_dir    : {base_dir}")
    print(f"  output_base : {output_base}")
    print(f"  regiones    : {regiones}")
    print(f"  variables   : {variables}")
    print(f"  max_order   : {args.max_order}")

    resultados = []

    # ── Modo nacional ─────────────────────────────────────────────────────────
    if regiones == "nacional":
        try:
            res = analizar_nacional(
                base_dir=base_dir,
                output_base=output_base,
                variables_list=variables,
                max_order=args.max_order,
                permutaciones=args.permutaciones,
                skip_viz=args.skip_viz,
            )
            resultados.append(res)
        except Exception as e:
            import traceback
            print(f"\n  ⚠ Error en análisis nacional: {e}")
            traceback.print_exc()
            resultados.append({"region": "nacional", "status": "error",
                                "error": str(e)})

    # ── Modo por región ───────────────────────────────────────────────────────
    else:
        for r in regiones:
            try:
                res = analizar_region(
                    region_code=r,
                    base_dir=base_dir,
                    output_base=output_base,
                    variables_list=variables,
                    max_order=args.max_order,
                    permutaciones=args.permutaciones,
                    skip_viz=args.skip_viz,
                    usar_nacional=args.nacional,
                )
                resultados.append(res)
            except Exception as e:
                import traceback
                print(f"\n  ⚠ Error en región {r}: {e}")
                traceback.print_exc()
                resultados.append({"region": r, "status": "error",
                                    "error": str(e)})

    # Resumen final
    print(f"\n{'='*60}")
    print(f" RESUMEN FINAL")
    print(f"{'='*60}")
    df_res = pd.DataFrame(resultados)
    cols_show = [c for c in ["region","region_name","status",
                              "n_distritos","moran_viviendas"]
                 if c in df_res.columns]
    print(df_res[cols_show].to_string(index=False))

    resumen_path = os.path.join(output_base, "autocorrelacion_resumen.csv")
    df_res.to_csv(resumen_path, index=False)
    print(f"\nResumen guardado: {resumen_path}")


if __name__ == "__main__":
    main()
