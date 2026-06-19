"""
scripts/setup.py
================
Genera todos los datos base necesarios para los análisis posteriores.
Reemplaza al demo.py — este es el script de inicialización real del proyecto.

Outputs generados en datos/nacional/:
    matrices/
        matriz_distrital_matriz.npz
        matriz_distrital_indice.csv
        matriz_distrital_islas.csv
        matriz_comunal_matriz.npz
        matriz_comunal_indice.csv
        matriz_comunal_islas.csv
    figuras/
        equivalencia_usa_chile.png
        grafo_adyacencia_distrital.png
        grafo_adyacencia_comunal.png
        compacidad_distrital.png
        mapa_distritos_tipo.png

Uso:
    python scripts/setup.py --base-dir ./SHP_APC2023
    python scripts/setup.py --base-dir ./SHP_APC2023 --skip-viz
"""

import argparse
import os
import sys
import warnings
warnings.filterwarnings("ignore")

# Agregar raíz del proyecto al path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import chiledist as cd
import pandas as pd
import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Genera datos base de chiledist (matrices, índices, figuras)."
    )
    p.add_argument(
        "--base-dir", default=".",
        help="Directorio raíz con carpetas SHP_APC2023_R* (default: .)"
    )
    p.add_argument(
        "--output-dir", default=None,
        help="Directorio de salida (default: <base-dir>/datos/nacional)"
    )
    p.add_argument(
        "--skip-viz", action="store_true",
        help="Omitir generación de figuras (más rápido)"
    )
    p.add_argument(
        "--skip-manzanas", action="store_true",
        help="Omitir carga de manzanas urbanas/aldea (más rápido)"
    )
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────

def make_dirs(output_dir: str) -> dict:
    """Crea estructura de carpetas y retorna rutas."""
    dirs = {
        "matrices": os.path.join(output_dir, "matrices"),
        "figuras":  os.path.join(output_dir, "figuras"),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    base_dir = args.base_dir

    output_dir = args.output_dir or os.path.join(base_dir, "datos", "nacional")
    dirs = make_dirs(output_dir)

    print(f"\nchiledist — Setup")
    print(f"  base_dir   : {base_dir}")
    print(f"  output_dir : {output_dir}")

    # ── 1. Equivalencia USA-Chile ─────────────────────────────────────────────
    section("1. EQUIVALENCIA CENSAL USA ↔ CHILE")
    cd.print_equivalence()
    cd.describe_hierarchy("CHL")

    if not args.skip_viz:
        cd.plot_equivalence_table(
            save_path=os.path.join(dirs["figuras"], "equivalencia_usa_chile.png")
        )
        import matplotlib.pyplot as plt
        plt.close("all")

    # ── 2. Verificar capas disponibles ───────────────────────────────────────
    section("2. CAPAS DISPONIBLES")
    capas = cd.list_available_layers(base_dir)
    print(capas.to_string(index=False))

    faltantes = capas[~capas["disponible"]]["capa"].tolist()
    if faltantes:
        print(f"\n⚠ Capas no encontradas: {faltantes}")
        print("  Verifica que --base-dir apunte a la carpeta con SHP_APC2023_R*")

    # ── 3. Cargar capas principales ───────────────────────────────────────────
    section("3. CARGA DE CAPAS")

    distritos = cd.load_layer("distrital", base_dir=base_dir)
    comunas   = cd.load_layer("comunal",   base_dir=base_dir)
    cd.summarize(distritos, "Distrital")
    cd.summarize(comunas,   "Comunal")

    if not args.skip_manzanas:
        mz_urb = cd.load_layer("manzana_urbana", base_dir=base_dir)
        mz_ald = cd.load_layer("manzana_aldea",  base_dir=base_dir)
    else:
        print("  (manzanas omitidas por --skip-manzanas)")
        mz_urb = None
        mz_ald = None

    # ── 4. Agregar población ──────────────────────────────────────────────────
    section("4. AGREGACIÓN DE POBLACIÓN")

    if mz_urb is not None and mz_ald is not None:
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
        print(f"  Viviendas totales asignadas: {distritos['viviendas'].sum():,}")
    else:
        distritos["viviendas"] = 0
        print("  Población no asignada (sin manzanas)")

    # ── 5. Grafos de adyacencia ───────────────────────────────────────────────
    section("5. GRAFOS DE ADYACENCIA")

    G_dist, adj_dist, ids_dist = cd.build_graph(
        distritos, id_col="ID_DIST",
        method="queen", connect_islands=True,
        attr_cols=["N_REGION","N_COMUNA","TIPO_DISTRITO","viviendas"],
    )
    print("\nEstadísticas — Distrital:")
    print(cd.graph_stats(G_dist, adj_dist).to_string())

    G_com, adj_com, ids_com = cd.build_graph(
        comunas, id_col="CUT",
        method="queen", connect_islands=True,
    )
    print("\nEstadísticas — Comunal:")
    print(cd.graph_stats(G_com, adj_com).to_string())

    # ── 6. Guardar matrices ───────────────────────────────────────────────────
    section("6. GUARDAR MATRICES")

    prefix_dist = os.path.join(dirs["matrices"], "matriz_distrital")
    prefix_com  = os.path.join(dirs["matrices"], "matriz_comunal")

    cd.save_graph(adj_dist, ids_dist, distritos, "ID_DIST", prefix=prefix_dist)
    cd.save_graph(adj_com,  ids_com,  comunas,   "CUT",     prefix=prefix_com)

    # Guardar población por distrito
    pop_out = distritos[[
        "ID_DIST","CUT","N_DISTRITO","N_COMUNA","N_REGION","viviendas"
    ]].copy()
    pop_out.to_csv(
        os.path.join(dirs["matrices"], "poblacion_distritos.csv"), index=False
    )
    print(f"  Guardado: poblacion_distritos.csv")

    # ── 7. Métricas de compacidad ─────────────────────────────────────────────
    section("7. MÉTRICAS DE COMPACIDAD")

    metricas = cd.all_compactness(distritos, id_col="ID_DIST")
    metricas.to_csv(
        os.path.join(dirs["matrices"], "compacidad_distritos.csv"), index=False
    )
    print("Top 5 distritos más compactos (Polsby-Popper):")
    top5 = (
        metricas.merge(distritos[["ID_DIST","N_DISTRITO","N_COMUNA"]], on="ID_DIST")
        .nlargest(5, "polsby_popper")[["N_DISTRITO","N_COMUNA","polsby_popper"]]
    )
    print(top5.to_string(index=False))

    resumen_reg = cd.spatial_summary(
        distritos, id_col="ID_DIST",
        pop_col="viviendas", group_col="N_REGION"
    )
    resumen_reg.to_csv(
        os.path.join(dirs["matrices"], "resumen_regional.csv"), index=False
    )
    print(f"\n  Guardado: compacidad_distritos.csv")
    print(f"  Guardado: resumen_regional.csv")

    # ── 8. Visualizaciones ────────────────────────────────────────────────────
    if not args.skip_viz:
        section("8. VISUALIZACIONES")
        import matplotlib.pyplot as plt

        indice_dist = distritos[[
            "ID_DIST","N_DISTRITO","N_COMUNA","N_REGION",
            "N_PROVINCIA","TIPO_DISTRITO","viviendas"
        ]].copy().reset_index(drop=True)
        indice_dist["fila_col"] = range(len(indice_dist))

        cd.plot_adjacency_graph(
            G_dist, adj_dist, indice_dist,
            color_by="tipo",
            title="APC 2023 — Red de adyacencia distrital",
            save_path=os.path.join(dirs["figuras"], "grafo_adyacencia_distrital.png"),
        )
        plt.close("all")

        indice_com = comunas[["CUT","N_COMUNA","N_REGION","N_PROVINCIA"]].copy()
        indice_com["fila_col"] = range(len(indice_com))

        cd.plot_adjacency_graph(
            G_com, adj_com, indice_com,
            color_by="region",
            title="APC 2023 — Red de adyacencia comunal",
            save_path=os.path.join(dirs["figuras"], "grafo_adyacencia_comunal.png"),
        )
        plt.close("all")

        cd.plot_compactness(
            distritos, metricas, id_col="ID_DIST",
            metric="polsby_popper",
            title="Compacidad distrital — Polsby-Popper",
            save_path=os.path.join(dirs["figuras"], "compacidad_distrital.png"),
        )
        plt.close("all")

        cd.plot_layer(
            distritos, color_col="TIPO_DISTRITO",
            title="APC 2023 — Distritos por tipo",
            save_path=os.path.join(dirs["figuras"], "mapa_distritos_tipo.png"),
        )
        plt.close("all")

    # ── 9. Restricciones electorales Chile ────────────────────────────────────
    section("9. RESTRICCIONES ELECTORALES CHILE")
    cd.chile_constraints(
        distritos, id_col="ID_DIST",
        adj=adj_dist, id_list=ids_dist,
        preserve_comunas=True,
    )

    # ── 10. Exportar a R/redist ───────────────────────────────────────────────
    section("10. EXPORTAR A R / REDIST (ALARM)")
    cd.export_to_redist(
        distritos, id_col="ID_DIST", pop_col="viviendas",
        adj=adj_dist, id_list=ids_dist,
        output_file=os.path.join(dirs["matrices"], "chiledist_redist.rds"),
    )

    # ── Resumen ───────────────────────────────────────────────────────────────
    section("SETUP COMPLETADO")
    print(f"\nArchivos en {output_dir}:")
    for root, _, files in os.walk(output_dir):
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), output_dir)
            print(f"  {rel}")

    print(f"""
Próximos pasos:
  python scripts/redistritaje.py   --base-dir {base_dir} --regiones 13
  python scripts/autocorrelacion.py --base-dir {base_dir} --regiones todas
""")


if __name__ == "__main__":
    main()
