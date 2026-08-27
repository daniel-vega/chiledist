"""
chiledist.engines.samplers.smc
======================
Bridge al paquete redist (R / ALARM Harvard) para simulación SMC,
y exportación básica de datos para análisis en R.

SMC (Sequential Monte Carlo) genera muestras más eficientes que ReCom
porque cada partícula es independiente — no requiere diagnósticos
multi-cadena para convergencia.

Flujo típico
------------
    from chiledist.engines.samplers.smc import generate_redist_script, load_redist_results

    # 1. Exportar datos y generar script R
    r_script = generate_redist_script(
        gdf, id_col="ID_DIST", pop_col="personas",
        n_districts=8, output_dir="datos/R13/redist", n_sims=1000
    )

    # 2. Ejecutar en R:  Rscript datos/R13/redist/chiledist_redist.R

    # 3. Importar resultados SMC de vuelta a Python
    planes = load_redist_results("datos/R13/redist/chiledist_smc_planes.csv",
                                  id_list=gdf["ID_DIST"].tolist())
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd
import scipy.sparse as sp


# ──────────────────────────────────────────────────────────────────────────────
# Exportación básica a R (objeto redist_map desde adyacencia CSV)
# ──────────────────────────────────────────────────────────────────────────────

def export_to_redist(
    gdf,
    id_col: str,
    pop_col: str,
    adj: sp.csr_matrix,
    id_list: list,
    output_file: str = "chiledist_redist.rds",
) -> str:
    """
    Exporta datos en formato compatible con el paquete redist (R / ALARM).

    Genera un script R mínimo que construye el objeto redist_map
    desde los archivos exportados (GPKG + edge list de adyacencia).

    Returns
    -------
    str  Ruta del script R generado.
    """
    base = output_file.replace(".rds", "")

    shp_path = f"{base}_units.gpkg"
    gdf_out  = gdf[[id_col, pop_col, "geometry"]].copy()
    gdf_out.to_file(shp_path, driver="GPKG")

    adj_coo = adj.tocoo()
    edges   = pd.DataFrame({
        "i": [id_list[i] for i in adj_coo.row],
        "j": [id_list[j] for j in adj_coo.col],
    })
    edges   = edges[edges["i"] < edges["j"]]
    adj_path = f"{base}_adj.csv"
    edges.to_csv(adj_path, index=False)

    r_script = f"""
# Script generado por chiledist
library(redist)
library(sf)
library(dplyr)

units     <- st_read("{shp_path}")
adj_edges <- read.csv("{adj_path}")
adj       <- adjacency_matrix(units)

map <- redist_map(
    units,
    pop    = {pop_col},
    adj    = adj,
    ndists = NULL,
    pop_tol = 0.05
)

plans <- redist_smc(map, nsims = 500)
summary(plans)
redist.plot.plans(plans, map)
"""

    r_path = f"{base}_redist.R"
    with open(r_path, "w") as f:
        f.write(r_script)

    print(f"Exportado para redist:")
    print(f"  {shp_path}")
    print(f"  {adj_path}")
    print(f"  {r_path}  ← ejecutar en R")

    return r_path


# ──────────────────────────────────────────────────────────────────────────────
# Script R completo para SMC con métricas y exportación
# ──────────────────────────────────────────────────────────────────────────────

def generate_redist_script(
    gdf,
    id_col: str,
    pop_col: str,
    n_districts: int,
    output_dir: str = ".",
    pop_tol: float = 0.05,
    n_sims: int = 500,
    scenario_name: str = "chiledist",
    extra_cols: Optional[list[str]] = None,
) -> str:
    """
    Exporta datos APC y genera un script R completo para redist SMC.

    Exporta:
        {output_dir}/{scenario_name}_units.gpkg
        {output_dir}/{scenario_name}_redist.R

    El script R:
        - Construye el objeto redist_map
        - Ejecuta redist_smc() con los parámetros dados
        - Calcula Polsby-Popper y desviación poblacional
        - Exporta planes y métricas a CSV para importar en Python

    Parameters
    ----------
    gdf : GeoDataFrame
        Capa APC con geometrías; se reproyecta a EPSG:4326 si es necesario.
    id_col, pop_col : str
        Columnas de ID y población.
    n_districts : int
        Número de distritos electorales.
    output_dir : str
        Directorio de salida.
    pop_tol : float
        Tolerancia de población para redist_map (0.05 = ±5%).
    n_sims : int
        Número de simulaciones SMC.
    scenario_name : str
        Prefijo para archivos generados.
    extra_cols : list[str], opcional
        Columnas adicionales a incluir en el GPKG (ej. 'CUT', 'N_COMUNA').

    Returns
    -------
    str  Ruta del script R generado.
    """
    if shutil.which("Rscript") is None:
        warnings.warn(
            "Rscript no encontrado en PATH. El script R y el GPKG se generarán "
            "correctamente, pero deberás ejecutarlos desde un entorno con R instalado.\n"
            "  Instalar R:     https://cran.r-project.org/\n"
            "  Instalar redist (en R):  install.packages('redist')\n"
            "  Ejecutar luego: Rscript {output_dir}/{scenario_name}_redist.R",
            UserWarning,
            stacklevel=2,
        )

    output_dir  = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gpkg_path   = output_dir / f"{scenario_name}_units.gpkg"
    r_path      = output_dir / f"{scenario_name}_redist.R"
    plans_csv   = output_dir / f"{scenario_name}_smc_planes.csv"
    metrics_csv = output_dir / f"{scenario_name}_smc_metricas.csv"

    cols = [id_col, pop_col, "geometry"]
    if extra_cols:
        cols = [id_col, pop_col] + [c for c in extra_cols
                                    if c in gdf.columns] + ["geometry"]

    gdf_out = gdf[list(dict.fromkeys(cols))].copy()
    if gdf_out.crs and gdf_out.crs.to_epsg() != 4326:
        gdf_out = gdf_out.to_crs(epsg=4326)

    gdf_out.to_file(str(gpkg_path), driver="GPKG")
    print(f"  Exportado: {gpkg_path.name}  ({len(gdf_out)} unidades)")

    r_script = f"""\
# Script generado por chiledist — {scenario_name}
# Ejecutar en R: source("{r_path.name}")
# Requiere: install.packages(c("redist", "sf", "dplyr", "ggplot2"))

library(redist)
library(sf)
library(dplyr)
library(ggplot2)

# ── 1. Cargar datos ─────────────────────────────────────────────────────────
units <- st_read("{gpkg_path}", quiet = TRUE)
cat("Unidades cargadas:", nrow(units), "\\n")
cat("Población total:", sum(units${pop_col}), "\\n")

# ── 2. Construir objeto redist_map ───────────────────────────────────────────
map <- redist_map(
    units,
    pop      = {pop_col},
    ndists   = {n_districts},
    pop_tol  = {pop_tol},
    adj      = st_relate(units, units, pattern = "F***T****")
)
cat("redist_map construido:", ndists(map), "distritos\\n")

# ── 3. Simulación SMC ────────────────────────────────────────────────────────
set.seed(42)
plans_smc <- redist_smc(
    map,
    nsims   = {n_sims},
    verbose = TRUE
)
cat("SMC:", nsims(plans_smc), "planes generados\\n")

# ── 4. Métricas ──────────────────────────────────────────────────────────────
plans_smc <- plans_smc |>
    mutate(
        polsby_popper = distr_polsby_popper(map),
        pop_deviation = abs(total_pop / get_target_pop(map) - 1)
    )

# ── 5. Resumen y gráfico ─────────────────────────────────────────────────────
summary(plans_smc)
redist.plot.distr_qtys(plans_smc, polsby_popper) +
    labs(title = "Distribución Polsby-Popper — SMC ({scenario_name})")

# ── 6. Exportar para chiledist (Python) ──────────────────────────────────────
plans_matrix <- get_plans_matrix(plans_smc)
write.csv(as.data.frame(plans_matrix), "{plans_csv}", row.names = FALSE)

metrics_df <- plans_smc |>
    select(draw, polsby_popper, pop_deviation) |>
    as.data.frame()
write.csv(metrics_df, "{metrics_csv}", row.names = FALSE)

cat("\\nExportado para chiledist:")
cat("\\n  Planes:   {plans_csv}")
cat("\\n  Metricas: {metrics_csv}\\n")
"""

    with open(r_path, "w", encoding="utf-8") as f:
        f.write(r_script)

    print(f"  Script R: {r_path.name}")
    print(f"  → Ejecutar en R: source('{r_path.name}')")
    print(f"  → Requiere: redist >= 4.1, sf, dplyr, ggplot2")
    return str(r_path)


# ──────────────────────────────────────────────────────────────────────────────
# Importar resultados SMC desde R
# ──────────────────────────────────────────────────────────────────────────────

def load_redist_results(
    plans_csv: str,
    id_list: list,
) -> list[dict]:
    """
    Importa planes SMC exportados desde R a formato chiledist.

    Parameters
    ----------
    plans_csv : str
        CSV de planes generado por generate_redist_script().
    id_list : list
        IDs de unidades en el mismo orden que el GDF exportado.

    Returns
    -------
    list[dict]  Lista de planes en formato {unit_id: district_num}.
    """
    df = pd.read_csv(plans_csv)
    plans = [
        {id_list[i]: int(df[col].iloc[i]) for i in range(len(id_list))}
        for col in df.columns
    ]
    print(f"  Importados {len(plans)} planes SMC desde {plans_csv}")
    return plans
