"""
chiledist/data/census2024.py
============================
Carga y preprocesamiento de datos del Censo 2024 (INE Chile).

Dos estrategias de unión disponibles:

1. **join directo por distrito** (recomendado): usa Base_manzana_entidad_CPV24.csv
   que tiene CUT + COD_DISTRITO + n_per exactos por manzana.
   No requiere distribución proporcional.

       mz = c24.load_manzana_censo2024("Base_manzana_entidad_CPV24.csv")
       gdf = c24.join_manzana_to_apc(gdf, mz)

2. **distribución proporcional por comuna** (fallback): usa tabla comunal
   agregada desde personas_censo2024.csv.

       census = c24.load_census2024("datos/censo2024_comunas.csv")
       gdf    = c24.join_census_to_apc(gdf, census, proxy_col="viviendas")

Fuente de datos
---------------
Portal del INE Censo 2024:
    https://www.ine.gob.cl/estadisticas/sociales/censos-de-poblacion-y-vivienda/censo-de-poblacion-y-vivienda

    · Base_manzana_entidad_CPV24.csv  (~24 MB) — fuente preferida
    · personas_censo2024.csv/parquet  (~416 MB) — para tabla comunal

Ver download_instructions() para el flujo completo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd


# ── Aliases de columnas aceptados ────────────────────────────────────────────

_CUT_ALIASES = [
    "CUT", "cod_cut", "COD_CUT", "CODIGO_COMUNA", "cod_comuna",
    "COD_COMUNA", "Cod_Comuna", "codigo_cut",
]
_POP_ALIASES = {
    "personas": [
        "PERSONAS", "personas", "TOTAL_PERSONAS", "total_personas",
        "POB_TOTAL", "pob_total", "POBLACION", "poblacion",
    ],
    "hogares": [
        "HOGARES", "hogares", "TOTAL_HOGARES", "total_hogares",
        "VIVIENDAS_HABITADAS", "viviendas_habitadas",
    ],
}
_NOMBRE_ALIASES = ["NOMBRE_COMUNA", "N_COMUNA", "COMUNA", "nombre_comuna", "nombre"]


# ──────────────────────────────────────────────────────────────────────────────
# Instrucciones de descarga
# ──────────────────────────────────────────────────────────────────────────────

def download_instructions() -> None:
    """Imprime instrucciones para obtener los datos del Censo 2024 (INE)."""
    print("""
Censo 2024 — INE Chile
======================
URL: https://www.ine.gob.cl/estadisticas/sociales/censos-de-poblacion-y-vivienda/censo-de-poblacion-y-vivienda

── OPCIÓN A: Join directo por distrito (recomendada) ─────────────────────────
Archivo: "Base_manzana_entidad_CPV24.csv"  (~24 MB, separado por tabulador)
Columnas clave: CUT, COD_DISTRITO, n_per, n_hog

    import chiledist.data.census2024 as c24
    mz  = c24.load_manzana_censo2024("Base_manzana_entidad_CPV24.csv")
    gdf = c24.join_manzana_to_apc(gdf, mz)
    # → columnas "personas" y "hogares" exactas por distrito APC

── OPCIÓN B: Distribución proporcional por comuna (fallback) ─────────────────
Generar tabla comunal desde personas_censo2024.csv (~416 MB) en R:

    library(arrow); library(dplyr)
    personas <- open_dataset("personas_censo2024.parquet")
    personas |>
      filter(tipo_operativo == 2) |>
      group_by(CUT = comuna) |>
      summarise(PERSONAS = n()) |>
      collect() |>
      write.csv("censo2024_comunas.csv", row.names = FALSE)

Formato CSV mínimo esperado:
    CUT,PERSONAS
    13101,404495
    ...

Alias aceptados para CUT:      CUT, COD_CUT, CODIGO_COMUNA, COD_COMUNA
Alias aceptados para PERSONAS: PERSONAS, TOTAL_PERSONAS, POB_TOTAL, POBLACION
Alias aceptados para HOGARES:  HOGARES, TOTAL_HOGARES, VIVIENDAS_HABITADAS
""")


# ──────────────────────────────────────────────────────────────────────────────
# Carga del archivo de Censo 2024
# ──────────────────────────────────────────────────────────────────────────────

def load_census2024(
    path: str | Path,
    cut_col: Optional[str] = None,
    sep: str = ",",
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """
    Lee el archivo del Censo 2024 (CSV o Excel) y normaliza columnas.

    Parameters
    ----------
    path : str | Path
        Ruta al archivo comunal del Censo 2024.
    cut_col : str, opcional
        Nombre exacto de la columna CUT si no coincide con los alias conocidos.
    sep : str
        Separador CSV (default: ","  — usar ";" para archivos con punto y coma).
    encoding : str
        Codificación del archivo (default: "utf-8-sig" para archivos INE).

    Returns
    -------
    DataFrame con columnas normalizadas:
        CUT (int), personas (int), hogares (int, si existe), nombre_comuna (str).

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe.
    KeyError
        Si no se detecta columna CUT o la columna de personas obligatoria.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Archivo no encontrado: {path}\n"
            "Llama a download_instructions() para obtener el enlace de descarga."
        )

    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=sep, encoding=encoding, dtype=str)

    # Columna CUT
    if cut_col:
        if cut_col not in df.columns:
            raise KeyError(
                f"Columna CUT '{cut_col}' no encontrada. "
                f"Columnas disponibles: {list(df.columns)}"
            )
        df = df.rename(columns={cut_col: "CUT"})
    else:
        for alias in _CUT_ALIASES:
            if alias in df.columns:
                df = df.rename(columns={alias: "CUT"})
                break
        else:
            raise KeyError(
                f"No se encontró columna CUT.\n"
                f"Columnas del archivo: {list(df.columns)}\n"
                f"Alias conocidos: {_CUT_ALIASES}"
            )

    df["CUT"] = pd.to_numeric(df["CUT"], errors="coerce")
    df = df[df["CUT"].notna()].copy()
    df["CUT"] = df["CUT"].astype(int)

    # Columnas de población
    for target, aliases in _POP_ALIASES.items():
        if target not in df.columns:
            for alias in aliases:
                if alias in df.columns:
                    df = df.rename(columns={alias: target})
                    break

    if "personas" not in df.columns:
        raise KeyError(
            f"No se encontró columna de personas.\n"
            f"Alias conocidos: {_POP_ALIASES['personas']}\n"
            f"Columnas disponibles: {list(df.columns)}"
        )

    # Nombre de comuna (opcional)
    for alias in _NOMBRE_ALIASES:
        if alias in df.columns:
            df = df.rename(columns={alias: "nombre_comuna"})
            break

    for col in ["personas", "hogares"]:
        if col in df.columns:
            df[col] = (pd.to_numeric(df[col], errors="coerce")
                       .fillna(0).astype(int))

    keep = ["CUT"] + [c for c in ["nombre_comuna", "personas", "hogares"]
                      if c in df.columns]
    df = df[keep].reset_index(drop=True)

    print(f"  Censo 2024: {len(df)} comunas · "
          f"total personas={df['personas'].sum():,}")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Join proporcional: datos comunales → distritos APC
# ──────────────────────────────────────────────────────────────────────────────

def _proportional_join(
    gdf_apc: gpd.GeoDataFrame,
    source_df: pd.DataFrame,
    target_col: str,
    proxy_col: str,
    cut_col: str,
    fill_missing: bool,
    source_name: str,
) -> gpd.GeoDataFrame:
    """Núcleo del join proporcional, reutilizado por join_census_to_apc y join_census_multilevel."""
    if proxy_col not in gdf_apc.columns:
        raise KeyError(
            f"Columna proxy '{proxy_col}' no encontrada en gdf_apc.\n"
            f"Columnas disponibles: "
            f"{[c for c in gdf_apc.columns if c != 'geometry']}"
        )
    if cut_col not in gdf_apc.columns:
        raise KeyError(f"Columna '{cut_col}' no encontrada en gdf_apc.")

    gdf_out = gdf_apc.copy()

    # Total del proxy por comuna
    proxy_sum = (
        gdf_out.groupby(cut_col)[proxy_col]
        .transform("sum")
        .rename("_proxy_total")
    )
    gdf_out["_proxy_total"] = proxy_sum.values

    # Merge con la fuente
    merged = gdf_out.merge(
        source_df[["CUT", target_col]].rename(
            columns={target_col: "_src_val", "CUT": "_src_cut"}
        ),
        left_on=cut_col, right_on="_src_cut", how="left",
    ).drop(columns=["_src_cut"], errors="ignore")

    missing = merged["_src_val"].isna().sum()
    if missing > 0:
        if fill_missing:
            faltantes = sorted(
                merged.loc[merged["_src_val"].isna(), cut_col].unique()
            )
            n_show = 5
            suffix = "..." if len(faltantes) > n_show else ""
            print(f"  ⚠ {missing} distritos sin datos de {source_name} "
                  f"(CUT: {faltantes[:n_show]}{suffix}) → 0")
            merged["_src_val"] = merged["_src_val"].fillna(0)
        else:
            raise ValueError(
                f"{missing} distritos APC no tienen datos de {source_name}. "
                "Usa fill_missing=True para rellenar con 0."
            )

    proxy  = merged[proxy_col].fillna(0).astype(float)
    total  = merged["_proxy_total"].fillna(0).astype(float).replace(0, np.nan)
    src    = merged["_src_val"].fillna(0).astype(float)

    merged[target_col] = ((proxy / total).fillna(0) * src).round().astype(int)
    gdf_out = merged.drop(columns=["_proxy_total", "_src_val"], errors="ignore")

    cuts_cubiertos = gdf_out[cut_col].unique()
    total_assigned = int(gdf_out[target_col].sum())
    total_source   = int(
        source_df.loc[source_df["CUT"].isin(cuts_cubiertos), target_col].sum()
    )
    print(f"  {source_name} → {target_col}: "
          f"{len(gdf_out)} distritos ({len(cuts_cubiertos)} comunas) · "
          f"total={total_assigned:,} "
          f"(fuente comunas cubiertas={total_source:,} · diff={total_assigned - total_source:+,})")
    return gdf_out


def join_census_to_apc(
    gdf_apc: gpd.GeoDataFrame,
    census_df: pd.DataFrame,
    target_col: str = "personas",
    proxy_col: str = "viviendas",
    cut_col: str = "CUT",
    fill_missing: bool = True,
) -> gpd.GeoDataFrame:
    """
    Distribuye datos del Censo 2024 a nivel de distrito APC.

    El total de personas (u hogares) por comuna se reparte entre los
    distritos APC de esa comuna en proporción al valor del proxy.

    Parameters
    ----------
    gdf_apc : GeoDataFrame
        Capa APC distrital con columnas CUT y proxy_col.
    census_df : DataFrame
        Salida de load_census2024().
    target_col : str
        Columna del censo a distribuir (default: "personas").
    proxy_col : str
        Columna de gdf_apc usada como proxy de distribución (default: "viviendas").
    cut_col : str
        Nombre de la columna CUT en gdf_apc.
    fill_missing : bool
        Si True, comunas sin datos en el censo reciben 0 en lugar de NaN.

    Returns
    -------
    GeoDataFrame con columna target_col añadida (int).
    """
    if target_col not in census_df.columns:
        raise KeyError(
            f"Columna '{target_col}' no encontrada en census_df. "
            f"Disponibles: {list(census_df.columns)}"
        )
    return _proportional_join(
        gdf_apc, census_df, target_col, proxy_col, cut_col,
        fill_missing, "Censo 2024",
    )


def join_census_multilevel(
    gdf_apc: gpd.GeoDataFrame,
    census_df: pd.DataFrame,
    proxy_col: str = "viviendas",
    cut_col: str = "CUT",
) -> gpd.GeoDataFrame:
    """
    Une personas y hogares (si disponibles) en una sola llamada.

    Returns
    -------
    GeoDataFrame con columnas "personas" y "hogares" añadidas.
    """
    gdf_out = gdf_apc.copy()
    for col in ["personas", "hogares"]:
        if col in census_df.columns:
            gdf_out = join_census_to_apc(
                gdf_out, census_df,
                target_col=col, proxy_col=proxy_col, cut_col=cut_col,
            )
    return gdf_out


# ──────────────────────────────────────────────────────────────────────────────
# Resumen estadístico
# ──────────────────────────────────────────────────────────────────────────────

def census_summary(
    gdf_apc: gpd.GeoDataFrame,
    pop_col: str = "personas",
    cut_col: str = "CUT",
) -> pd.DataFrame:
    """
    Resumen de población por comuna para el GDF enriquecido con Censo 2024.

    Returns
    -------
    DataFrame: CUT, n_distritos, total_<pop_col>, media_<pop_col>, ordenado desc.
    """
    if pop_col not in gdf_apc.columns:
        raise KeyError(
            f"Columna '{pop_col}' no encontrada. "
            "¿Ya ejecutaste join_census_to_apc()?"
        )
    return (
        gdf_apc.groupby(cut_col)
        .agg(n_distritos=(pop_col, "count"), total=(pop_col, "sum"))
        .assign(media=lambda d: (d["total"] / d["n_distritos"]).round(1))
        .rename(columns={"total": f"total_{pop_col}", "media": f"media_{pop_col}"})
        .reset_index()
        .sort_values(f"total_{pop_col}", ascending=False)
        .reset_index(drop=True)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Join directo desde Base_manzana_entidad_CPV24.csv
# ──────────────────────────────────────────────────────────────────────────────

def load_manzana_censo2024(
    path: str | Path,
    sep: str = "\t",
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """
    Lee Base_manzana_entidad_CPV24.csv y retorna conteos por manzana-entidad.

    La tabla del Censo 2024 incluye CUT + COD_DISTRITO, lo que permite
    construir el identificador de distrito APC (ID_DIST) sin distribución
    proporcional.

    Parameters
    ----------
    path : str | Path
        Ruta al archivo Base_manzana_entidad_CPV24.csv (separado por tabulador).
    sep : str
        Separador de columnas (default: "\\t" para tabulador).
    encoding : str
        Codificación del archivo (default: "utf-8-sig").

    Returns
    -------
    DataFrame con columnas: CUT (int), COD_DISTRITO (int), n_per (int), n_hog (int).

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe.
    KeyError
        Si faltan columnas obligatorias.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Archivo no encontrado: {path}\n"
            "Llama a download_instructions() para instrucciones de descarga."
        )

    cols_needed = {"CUT", "COD_DISTRITO", "n_per", "n_hog"}
    df = pd.read_csv(path, sep=sep, encoding=encoding, dtype=str,
                     usecols=lambda c: c in cols_needed | {"COD_REGION", "REGION"})

    missing = cols_needed - set(df.columns)
    if missing:
        raise KeyError(
            f"Columnas faltantes en {path.name}: {missing}\n"
            f"Columnas encontradas: {list(df.columns)}"
        )

    for col in ["CUT", "COD_DISTRITO", "n_per", "n_hog"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df = df[df["CUT"] > 0].copy()

    total_manzanas = len(df)
    total_personas = int(df["n_per"].sum())
    print(f"  Base manzana Censo 2024: {total_manzanas:,} manzanas-entidad · "
          f"total n_per={total_personas:,}")
    return df[["CUT", "COD_DISTRITO", "n_per", "n_hog"]].reset_index(drop=True)


def join_manzana_to_apc(
    gdf_apc: gpd.GeoDataFrame,
    manzana_df: pd.DataFrame,
    id_dist_col: str = "ID_DIST",
    cut_col: str = "CUT",
    fill_missing: bool = True,
) -> gpd.GeoDataFrame:
    """
    Une conteos exactos del Censo 2024 a nivel de distrito APC.

    Agrega n_per y n_hog por CUT + COD_DISTRITO y hace join directo al GDF
    usando el identificador ID_DIST = '{CUT:05d}_{COD_DISTRITO:03d}'.

    No requiere distribución proporcional: los conteos son exactos para
    cada distrito APC tal como fueron censados.

    Parameters
    ----------
    gdf_apc : GeoDataFrame
        Capa distrital APC con columna ID_DIST (ej. "13101_021").
    manzana_df : DataFrame
        Salida de load_manzana_censo2024().
    id_dist_col : str
        Nombre de la columna ID_DIST en gdf_apc (default: "ID_DIST").
    cut_col : str
        Nombre de la columna CUT en gdf_apc (default: "CUT").
    fill_missing : bool
        Si True, distritos sin datos del censo reciben 0.

    Returns
    -------
    GeoDataFrame con columnas "personas" y "hogares" añadidas (int).
    """
    if id_dist_col not in gdf_apc.columns:
        raise KeyError(
            f"Columna '{id_dist_col}' no encontrada en gdf_apc.\n"
            f"Columnas disponibles: {[c for c in gdf_apc.columns if c != 'geometry']}"
        )

    # Agregar manzanas a nivel de distrito
    dist_pop = (
        manzana_df
        .groupby(["CUT", "COD_DISTRITO"], as_index=False)
        .agg(personas=("n_per", "sum"), hogares=("n_hog", "sum"))
    )

    # Construir ID_DIST en el mismo formato que el APC: "CCCCC_DDD"
    dist_pop["_id_dist"] = (
        dist_pop["CUT"].apply(lambda x: f"{x:05d}") + "_" +
        dist_pop["COD_DISTRITO"].apply(lambda x: f"{x:03d}")
    )

    n_dist_censo = len(dist_pop)
    n_dist_apc   = len(gdf_apc)

    gdf_out = gdf_apc.merge(
        dist_pop[["_id_dist", "personas", "hogares"]],
        left_on=id_dist_col, right_on="_id_dist", how="left",
    ).drop(columns=["_id_dist"], errors="ignore")

    for col in ["personas", "hogares"]:
        missing = gdf_out[col].isna().sum()
        if missing > 0:
            if fill_missing:
                faltantes = sorted(
                    gdf_out.loc[gdf_out[col].isna(), id_dist_col].unique()
                )
                n_show = 5
                suffix = "..." if len(faltantes) > n_show else ""
                print(f"  ⚠ {missing} distritos sin {col} en Censo 2024 "
                      f"({faltantes[:n_show]}{suffix}) → 0")
                gdf_out[col] = gdf_out[col].fillna(0)
            else:
                raise ValueError(
                    f"{missing} distritos APC no tienen {col} en Base manzana. "
                    "Usa fill_missing=True para rellenar con 0."
                )
        gdf_out[col] = gdf_out[col].astype(int)

    print(f"  Censo 2024 (manzana) → {n_dist_apc} distritos APC · "
          f"personas={int(gdf_out['personas'].sum()):,} · "
          f"hogares={int(gdf_out['hogares'].sum()):,} "
          f"(Censo: {n_dist_censo} distritos)")
    return gdf_out
