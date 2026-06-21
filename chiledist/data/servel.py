"""
chiledist/data/servel.py
========================
Carga y preprocesamiento de datos del SERVEL (Servicio Electoral de Chile).

Provee:
    - Padrón electoral por comuna (inscritos, hombres, mujeres)
    - Resultados históricos de elecciones parlamentarias/presidenciales
    - Join proporcional del padrón a nivel de distrito APC

El padrón es la fuente más adecuada para redistritaje orientado a
representación política equitativa (una persona, un voto), mientras
que viviendas y personas del Censo son adecuadas para distribución
proporcional de servicios.

Fuente de datos
---------------
    Padrón:    https://www.servel.cl/padron-electoral/
    Resultados: https://www.servel.cl/estadisticas-electorales/

Ver download_instructions() para el formato esperado.

Flujo típico
------------
    import chiledist.data.servel as sv

    padron = sv.load_padron_electoral("datos/padron_2024.csv")
    gdf    = sv.join_padron_to_apc(gdf, padron, proxy_col="viviendas")
    # gdf ahora tiene columna "inscritos"

    # Resultados electorales (para Fase 5 — D'Hondt)
    resultados = sv.load_resultados_electorales(
        "datos/diputados_2021.csv", tipo_eleccion="diputados"
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd


# ── Aliases de columnas aceptados ────────────────────────────────────────────

_CUT_ALIASES = [
    "CUT", "COD_COMUNA", "CODIGO_COMUNA", "cod_comuna",
    "CÓD. COMUNA", "COD. COMUNA", "Cod_Comuna", "codigo_comuna",
]
_TOTAL_ALIASES  = ["TOTAL", "total", "INSCRITOS", "inscritos",
                   "TOTAL_INSCRITOS", "electores", "ELECTORES"]
_HOMBRES_ALIASES = ["HOMBRES", "hombres", "H", "VARONES", "varones"]
_MUJERES_ALIASES  = ["MUJERES", "mujeres", "M", "FEMENINO", "femenino"]
_NOMBRE_ALIASES   = ["NOMBRE_COMUNA", "COMUNA", "N_COMUNA",
                     "nombre_comuna", "nombre"]


# ──────────────────────────────────────────────────────────────────────────────
# Instrucciones de descarga
# ──────────────────────────────────────────────────────────────────────────────

def download_instructions() -> None:
    """Imprime instrucciones para obtener datos del SERVEL."""
    print("""
SERVEL — Padrón Electoral y Resultados
=======================================
Padrón electoral (inscritos por comuna):
  URL: https://www.servel.cl/padron-electoral/
  → Descargar "Padrón electoral vigente" (CSV o Excel).
  → Columnas esperadas:
      COD_COMUNA / CUT  — código único territorial (5 dígitos)
      HOMBRES           — electores hombres
      MUJERES           — electoras mujeres
      TOTAL             — total inscritos

Resultados electorales (para D'Hondt en Fase 5):
  URL: https://www.servel.cl/estadisticas-electorales/
  → Disponibles por tipo de elección (diputados, senadores, presidencial).

Formato CSV mínimo esperado (padrón):
    COD_COMUNA,NOMBRE_COMUNA,HOMBRES,MUJERES,TOTAL
    13101,Santiago,192203,212292,404495
    13102,Cerrillos,41843,42670,84513
    ...

Alias aceptados para CUT:      CUT, COD_COMUNA, CODIGO_COMUNA
Alias aceptados para TOTAL:    TOTAL, INSCRITOS, electores
Alias aceptados para HOMBRES:  HOMBRES, H, VARONES
Alias aceptados para MUJERES:  MUJERES, M, FEMENINO

Uso:
    import chiledist.data.servel as sv
    padron = sv.load_padron_electoral("datos/padron_2024.csv")
    gdf    = sv.join_padron_to_apc(gdf, padron, proxy_col="viviendas")
""")


# ──────────────────────────────────────────────────────────────────────────────
# Carga del padrón electoral
# ──────────────────────────────────────────────────────────────────────────────

def load_padron_electoral(
    path: str | Path,
    year: Optional[int] = None,
    cut_col: Optional[str] = None,
    sep: str = ",",
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """
    Lee el padrón electoral del SERVEL y normaliza columnas.

    Parameters
    ----------
    path : str | Path
        Ruta al CSV o Excel del padrón SERVEL.
    year : int, opcional
        Año del padrón (solo informativo).
    cut_col : str, opcional
        Nombre exacto de la columna CUT si no coincide con los alias.
    sep, encoding : str
        Parámetros de lectura CSV.

    Returns
    -------
    DataFrame con columnas:
        CUT (int), nombre_comuna (str, si existe),
        hombres (int), mujeres (int), inscritos (int).

    Raises
    ------
    FileNotFoundError : Si el archivo no existe.
    KeyError : Si no se detecta columna CUT o inscritos.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Archivo no encontrado: {path}\n"
            "Llama a download_instructions() para el enlace de descarga."
        )

    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=sep, encoding=encoding, dtype=str)

    # Columna CUT
    if cut_col:
        if cut_col not in df.columns:
            raise KeyError(f"Columna '{cut_col}' no encontrada. "
                           f"Columnas: {list(df.columns)}")
        df = df.rename(columns={cut_col: "CUT"})
    else:
        for alias in _CUT_ALIASES:
            if alias in df.columns:
                df = df.rename(columns={alias: "CUT"})
                break
        else:
            raise KeyError(
                f"No se encontró columna CUT.\n"
                f"Columnas: {list(df.columns)}\nAlias: {_CUT_ALIASES}"
            )

    df["CUT"] = pd.to_numeric(df["CUT"], errors="coerce")
    df = df[df["CUT"].notna()].copy()
    df["CUT"] = df["CUT"].astype(int)

    # Columnas de electores
    for target, aliases in [
        ("inscritos", _TOTAL_ALIASES),
        ("hombres",   _HOMBRES_ALIASES),
        ("mujeres",   _MUJERES_ALIASES),
    ]:
        if target not in df.columns:
            for alias in aliases:
                if alias in df.columns:
                    df = df.rename(columns={alias: target})
                    break

    # Calcular inscritos si no viene explícito
    if "inscritos" not in df.columns:
        if "hombres" in df.columns and "mujeres" in df.columns:
            df["hombres"] = pd.to_numeric(df["hombres"], errors="coerce").fillna(0)
            df["mujeres"] = pd.to_numeric(df["mujeres"], errors="coerce").fillna(0)
            df["inscritos"] = (df["hombres"] + df["mujeres"]).astype(int)
        else:
            raise KeyError(
                f"No se encontró columna de inscritos.\n"
                f"Columnas: {list(df.columns)}\nAlias: {_TOTAL_ALIASES}"
            )

    for alias in _NOMBRE_ALIASES:
        if alias in df.columns:
            df = df.rename(columns={alias: "nombre_comuna"})
            break

    for col in ["inscritos", "hombres", "mujeres"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if year is not None:
        df["año_padron"] = year

    keep = ["CUT"] + [c for c in ["nombre_comuna", "hombres", "mujeres",
                                   "inscritos", "año_padron"]
                      if c in df.columns]
    df = df[keep].reset_index(drop=True)

    print(f"  Padrón SERVEL: {len(df)} comunas · "
          f"total inscritos={df['inscritos'].sum():,}")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Join proporcional al APC
# ──────────────────────────────────────────────────────────────────────────────

def join_padron_to_apc(
    gdf_apc: gpd.GeoDataFrame,
    padron_df: pd.DataFrame,
    target_col: str = "inscritos",
    proxy_col: str = "viviendas",
    cut_col: str = "CUT",
    fill_missing: bool = True,
) -> gpd.GeoDataFrame:
    """
    Distribuye el padrón electoral a nivel de distrito APC proporcionalmente.

    El total de inscritos por comuna se reparte entre los distritos APC
    en proporción al valor del proxy (viviendas por defecto).

    Parameters
    ----------
    gdf_apc : GeoDataFrame
        Capa APC distrital con columnas CUT y proxy_col.
    padron_df : DataFrame
        Salida de load_padron_electoral().
    target_col : str
        Columna a distribuir: "inscritos", "hombres", o "mujeres".
    proxy_col : str
        Proxy de distribución en gdf_apc (default: "viviendas").
    cut_col : str
        Columna CUT en gdf_apc.
    fill_missing : bool
        Rellena comunas sin datos con 0 en lugar de NaN.

    Returns
    -------
    GeoDataFrame con columna target_col añadida (int).
    """
    if target_col not in padron_df.columns:
        raise KeyError(
            f"Columna '{target_col}' no encontrada en padron_df. "
            f"Disponibles: {list(padron_df.columns)}"
        )
    if proxy_col not in gdf_apc.columns:
        raise KeyError(
            f"Columna proxy '{proxy_col}' no encontrada en gdf_apc.\n"
            f"Disponibles: {[c for c in gdf_apc.columns if c != 'geometry']}"
        )
    if cut_col not in gdf_apc.columns:
        raise KeyError(f"Columna '{cut_col}' no encontrada en gdf_apc.")

    gdf_out = gdf_apc.copy()

    proxy_sum = (
        gdf_out.groupby(cut_col)[proxy_col]
        .transform("sum")
    )
    gdf_out["_proxy_total"] = proxy_sum.values

    merged = gdf_out.merge(
        padron_df[["CUT", target_col]].rename(
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
            print(f"  ⚠ {missing} distritos sin padrón SERVEL "
                  f"(CUT: {faltantes[:n_show]}{suffix}) → 0")
            merged["_src_val"] = merged["_src_val"].fillna(0)
        else:
            raise ValueError(
                f"{missing} distritos APC sin datos de padrón. "
                "Usa fill_missing=True para rellenar con 0."
            )

    proxy  = merged[proxy_col].fillna(0).astype(float)
    total  = merged["_proxy_total"].fillna(0).astype(float).replace(0, np.nan)
    src    = merged["_src_val"].fillna(0).astype(float)

    merged[target_col] = ((proxy / total).fillna(0) * src).round().astype(int)
    gdf_out = merged.drop(columns=["_proxy_total", "_src_val"], errors="ignore")

    print(f"  Padrón SERVEL → {target_col}: "
          f"{len(gdf_out)} distritos · total={gdf_out[target_col].sum():,}")
    return gdf_out


# ──────────────────────────────────────────────────────────────────────────────
# Carga de resultados electorales
# ──────────────────────────────────────────────────────────────────────────────

# Columnas que se intentan normalizar en resultados electorales
_RESULTADOS_RENAME = {
    # votos
    "votos": ["VOTOS", "votos", "TOTAL_VOTOS", "total_votos",
              "N_VOTOS", "TOTAL VOTOS"],
    # partido
    "partido": ["PARTIDO", "partido", "LISTA", "lista", "PACTO", "pacto"],
    # candidato
    "candidato": ["CANDIDATO", "candidato", "NOMBRE_CANDIDATO",
                  "CANDIDATO(A)", "nombre"],
    # circunscripción electoral
    "circunscripcion": ["DISTRITO", "distrito", "CIRCUNSCRIPCION",
                        "CIRCUNSCRIPCIÓN", "DISTRITO ELECTORAL",
                        "circunscripcion", "circunscripción"],
}


def load_resultados_electorales(
    path: str | Path,
    tipo_eleccion: str = "diputados",
    sep: str = ",",
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """
    Lee resultados electorales del SERVEL y normaliza columnas conocidas.

    El formato varía por elección y año; esta función realiza un best-effort
    de normalización de nombres de columnas.

    Parameters
    ----------
    path : str | Path
        Ruta al archivo de resultados (CSV o Excel).
    tipo_eleccion : str
        Tipo de elección: "diputados", "senadores", "presidencial", "municipales".
    sep, encoding : str
        Parámetros de lectura CSV.

    Returns
    -------
    DataFrame normalizado con columnas (cuando disponibles):
        circunscripcion, CUT, partido, candidato, votos, tipo_eleccion.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Archivo no encontrado: {path}\n"
            "Llama a download_instructions() para el enlace de descarga."
        )

    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=sep, encoding=encoding)

    # Normalizar columnas conocidas
    for target, aliases in _RESULTADOS_RENAME.items():
        if target not in df.columns:
            for alias in aliases:
                if alias in df.columns:
                    df = df.rename(columns={alias: target})
                    break

    # Columna CUT (si existe en resultados comunales)
    if "CUT" not in df.columns:
        for alias in _CUT_ALIASES:
            if alias in df.columns:
                df = df.rename(columns={alias: "CUT"})
                break

    if "votos" in df.columns:
        df["votos"] = pd.to_numeric(df["votos"], errors="coerce").fillna(0).astype(int)

    df["tipo_eleccion"] = tipo_eleccion
    print(f"  Resultados '{tipo_eleccion}': {len(df)} filas")
    return df.reset_index(drop=True)


def votos_por_comuna(
    resultados_df: pd.DataFrame,
    partido_col: str = "partido",
    votos_col: str = "votos",
    cut_col: str = "CUT",
) -> pd.DataFrame:
    """
    Agrega votos por partido a nivel de comuna.

    Solo funciona si el archivo de resultados contiene una columna CUT
    (datos a nivel comunal, no por circunscripción agregada).

    Returns
    -------
    DataFrame: CUT, partido, votos — ordenado por CUT y votos descendente.
    """
    if cut_col not in resultados_df.columns:
        raise KeyError(
            f"Columna '{cut_col}' no encontrada en resultados_df. "
            "Este archivo no tiene datos a nivel comunal."
        )
    return (
        resultados_df
        .groupby([cut_col, partido_col])[votos_col]
        .sum()
        .reset_index()
        .sort_values([cut_col, votos_col], ascending=[True, False])
        .reset_index(drop=True)
    )


def resumen_padron_regional(
    padron_df: pd.DataFrame,
    cut_col: str = "CUT",
) -> pd.DataFrame:
    """
    Agrega el padrón a nivel regional (primeros 2 dígitos del CUT).

    Returns
    -------
    DataFrame: COD_REGION, n_comunas, inscritos_total.
    """
    df = padron_df.copy()
    df["COD_REGION"] = (df[cut_col] // 1000).astype(int)
    return (
        df.groupby("COD_REGION")
        .agg(n_comunas=(cut_col, "count"),
             inscritos_total=("inscritos", "sum"))
        .reset_index()
        .sort_values("COD_REGION")
    )
