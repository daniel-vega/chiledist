"""
chiledist.domain.data.servel
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
    import chiledist.domain.data.servel as sv

    padron = sv.load_padron_electoral("datos/padron_2024.csv")
    gdf    = sv.join_padron_to_apc(gdf, padron, proxy_col="viviendas")
    # gdf ahora tiene columna "inscritos"

    # Resultados electorales (para Fase 5 — D'Hondt)
    resultados = sv.load_resultados_electorales(
        "datos/diputados_2021.csv", tipo_eleccion="diputados"
    )
"""

from __future__ import annotations

import dataclasses
import glob
import re
import unicodedata
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd

from . import provenance
from ...hierarchy import normalize_cut
from ...utils import normalize_party_name


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
    import chiledist.domain.data.servel as sv
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


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas para resultados electorales por candidato
# (equivalente empaquetado de datos/scripts_extra/escanos.py::normalizar y
# ::ALIASES_COMUNA, verificado contra TRICEL 2025)
# ──────────────────────────────────────────────────────────────────────────────

def normalize_commune_name(s: str) -> str:
    """
    Normaliza nombre de comuna para matching.

    Equivalente a normalizar() en datos/scripts_extra/escanos.py:
    NFKD + fold a ASCII (sin tildes) + mayúsculas + strip. Tolera que los
    Excel de SERVEL y el shapefile APC2023 representen el mismo nombre de
    comuna con distinta capitalización o acentuación.

    Parameters
    ----------
    s : str

    Returns
    -------
    str
        Nombre normalizado: MAYÚSCULAS, sin tildes/caracteres no ASCII,
        sin espacios al inicio/final. "" si `s` no es un string.
    """
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().upper()


#: Aliases ortográficos conocidos entre nombres de comuna en los Excel de
#: SERVEL y N_COMUNA del shapefile APC2023. Fuente:
#: datos/scripts_extra/escanos.py::ALIASES_COMUNA, verificado contra
#: TRICEL 2025 (ver README.md § Datos externos, tabla de aliases).
#: Antártica (CUT 12202) deliberadamente NO tiene alias aquí: es un caso
#: genuino sin cobertura cartográfica en APC2023, no un problema de nombre.
COMMUNE_NAME_ALIASES: dict[str, str] = {
    "MARCHIGUE":                   "MARCHIHUE",
    "TREHUACO":                    "TREGUACO",
    "PAIHUANO":                    "PAIGUANO",
    "LLAY-LLAY":                   "LLAILLAY",
    "CABO DE HORNOS(EX-NAVARINO)": "CABO DE HORNOS",
}


def filter_administrative_rows(
    df: pd.DataFrame,
    candidate_col: str = "cod_candidato",
) -> tuple[pd.DataFrame, int]:
    """
    Filtra filas sin candidatura real (votos nulos, blancos, totales).

    Los Excel de SERVEL incluyen, por mesa, filas administrativas
    ("Votos Nulos", "Votos en Blanco", "Total Sufragios Validamente
    Emitidos", "Total Suma Calculada") que no representan un candidato:
    `candidate_col` viene NaN en esas filas. A diferencia de
    datos/scripts_extra/procesar_servel_cut.py (que las agrupa como
    partido "IND" vía `.fillna("IND")`, inflando ese partido — ver
    README.md § Datos externos), esta función las elimina — nunca las
    reetiqueta como ningún partido.

    Parameters
    ----------
    df : pd.DataFrame
    candidate_col : str
        Columna que identifica a un candidato real (default: "cod_candidato").
        Una fila es administrativa si esta columna es NaN/None.

    Returns
    -------
    (df_filtrado, n_filas_eliminadas)
    """
    if candidate_col not in df.columns:
        raise KeyError(
            f"Columna '{candidate_col}' no encontrada. "
            f"Columnas disponibles: {list(df.columns)}"
        )
    mask_real = df[candidate_col].notna()
    n_removed = int((~mask_real).sum())
    return df[mask_real].copy(), n_removed


# ──────────────────────────────────────────────────────────────────────────────
# Schema canónico de resultados electorales por candidato
# (equivalente empaquetado de datos/scripts_extra/escanos.py)
# ──────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class CandidateRecord:
    """
    Un registro por candidato en una elección, agregado sobre todas las
    mesas de su distrito — schema canónico de import_candidates().
    """
    election_id: str          # ej. "CL-2025-DIP"
    office: str                # "diputado" | "senador"
    district_id: int           # número de distrito (1-28)
    CUT: int                    # código único territorial
    list_id: str                # pacto
    party_id: str                # partido normalizado (normalize_party_name)
    candidate_id: int            # cod_candidato
    candidate_name: str           # nombre_candidato
    independent_status: bool       # True si el partido crudo contiene "IND"
    votes: int                      # Σ votos_preliminares sobre las mesas del distrito
    officially_elected: bool         # electo_nominado == 1 en alguna mesa


_CANDIDATE_RECORD_FIELDS: list[str] = [
    f.name for f in dataclasses.fields(CandidateRecord)
]


def _parse_district_id(raw_distrito) -> Optional[int]:
    """Extrae el número entero de un string tipo 'Distrito 1' / 'DISTRITO 1'."""
    match = re.search(r"\d+", str(raw_distrito))
    return int(match.group()) if match else None


def _read_raw_servel_diputados(
    source_path: "str | Path",
) -> list[tuple[Path, pd.DataFrame]]:
    """
    Lee los Excel crudos PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx.

    source_path puede ser un directorio que los contiene, o un patrón glob
    explícito (ej. "./PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx").

    Nota: hoy solo lee el patrón de diputados sin importar `office` — ver
    deuda técnica en el reporte de esta etapa (no se confirmó el schema
    crudo de PRELIMINARES_SENADORES_CIRCUNSCRIPCI*.xlsx).
    """
    source_path = Path(source_path)
    pattern = (
        str(source_path / "PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx")
        if source_path.is_dir() else str(source_path)
    )
    archivos = sorted(glob.glob(pattern))
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos con el patrón: {pattern}")
    return [(Path(a), pd.read_excel(a, engine="openpyxl")) for a in archivos]


def _build_commune_cut_map(base_dir: str) -> dict:
    """
    {nombre_comuna_normalizado: CUT}, desde cd.load_layer("comunal", ...).
    Reutiliza la misma estrategia que
    datos/scripts_extra/escanos.py::construir_mapa_comuna_cut.
    """
    from ...loader import load_layer

    comunas = load_layer("comunal", base_dir=base_dir)
    return dict(zip(comunas["N_COMUNA"].apply(normalize_commune_name), comunas["CUT"]))


def import_candidates(
    source_path: "str | Path",
    election_id: str = "CL-2025-DIP",
    office: str = "diputado",
    base_dir: Optional[str] = None,
    commune_cut_map: Optional[dict] = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Importa resultados electorales por candidato a schema canónico.

    RAW: lee PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx desde source_path.
    NORMALIZED: aplica normalize_commune_name + COMMUNE_NAME_ALIASES para
        resolver comuna → CUT (vía commune_cut_map), normaliza el CUT
        resultante con chiledist.domain.hierarchy.normalize_cut, y
        normaliza party_id con chiledist.domain.utils.normalize_party_name.
    CANONICAL: filtra filas administrativas con filter_administrative_rows,
        agrega por candidato (Σ votos sobre las mesas de su distrito) y
        produce un DataFrame con el schema exacto de CandidateRecord.

    Parameters
    ----------
    source_path : str | Path
        Directorio con los 28 Excel de SERVEL, o un patrón glob explícito.
    election_id : str
    office : str
        "diputado" o "senador" — se guarda en el campo `office` de cada
        registro. No cambia qué archivos se leen (ver
        _read_raw_servel_diputados).
    base_dir : str, opcional
        Directorio con SHP_APC2023_R* para resolver comuna → CUT vía
        cd.load_layer("comunal", ...). Requerido solo si no se pasa
        `commune_cut_map`.
    commune_cut_map : dict, opcional
        {nombre_comuna_normalizado: CUT} ya construido. Si se provee, se
        usa directamente en vez de cargar el shapefile comunal — permite
        testear/reutilizar la función sin SHP_APC2023 real. Parámetro no
        pedido explícitamente en el encargo original; se agregó porque la
        función no era testeable sin alguna forma de inyectar el mapeo
        (ver "Deuda técnica" en el reporte de esta etapa).

    Returns
    -------
    (df_canonical, provenance) donde df_canonical tiene exactamente las
    columnas de CandidateRecord y provenance es un dict con:
        administrative_rows_removed : int
        commune_aliases_applied     : list[str]
        cut_normalizations          : int
        rows_without_party          : int
        unresolved_entities         : list[str]  # comunas sin CUT
        source_provenance           : list[dict]  # un ProvenanceRecord (asdict)
                                                    # por archivo fuente leído
    """
    if office not in ("diputado", "senador"):
        raise ValueError(f"office debe ser 'diputado' o 'senador', recibido: {office!r}")

    if commune_cut_map is None:
        if base_dir is None:
            raise ValueError(
                "Se requiere base_dir (para cd.load_layer('comunal', ...)) "
                "o commune_cut_map explícito."
            )
        commune_cut_map = _build_commune_cut_map(base_dir)

    archivos = _read_raw_servel_diputados(source_path)

    # Un ProvenanceRecord por archivo fuente (28 distritos = 28 registros):
    # cada Excel tiene su propio sha256/mtime, no hay un solo "source_path"
    # de donde calcular un único hash cuando source_path es un directorio.
    source_provenance = [
        dataclasses.asdict(provenance.compute_provenance(path, election_id))
        for path, _ in archivos
    ]

    bloques = []
    admin_removed_total = 0
    for _, df in archivos:
        df = df.copy()
        df.columns = [c.strip().lower() for c in df.columns]
        df_real, n_removed = filter_administrative_rows(df, candidate_col="cod_candidato")
        admin_removed_total += n_removed
        bloques.append(df_real)

    df_all = pd.concat(bloques, ignore_index=True)

    # NORMALIZED — comuna -> CUT
    nombre_norm = df_all["comuna"].apply(normalize_commune_name)
    aliases_applied = sorted(set(nombre_norm[nombre_norm.isin(COMMUNE_NAME_ALIASES)]))
    nombre_resuelto = nombre_norm.map(lambda n: COMMUNE_NAME_ALIASES.get(n, n))
    cut_raw = nombre_resuelto.map(commune_cut_map)

    unresolved_mask = cut_raw.isna()
    unresolved_entities = sorted(set(
        df_all.loc[unresolved_mask, "comuna"].dropna().astype(str).unique()
    ))
    if unresolved_entities:
        print(f"  ⚠ comunas sin CUT mapeado: {unresolved_entities}")

    df_all = df_all.loc[~unresolved_mask].copy()
    df_all["CUT"] = cut_raw[~unresolved_mask].apply(lambda v: int(normalize_cut(v)))
    cut_normalizations = len(df_all)

    # NORMALIZED — partido
    rows_without_party = int(df_all["partido"].isna().sum())
    df_all["party_id"] = df_all["partido"].apply(
        lambda p: normalize_party_name(str(p)) if pd.notna(p) else ""
    )
    df_all["independent_status"] = df_all["partido"].apply(
        lambda p: "IND" in str(p).upper() if pd.notna(p) else False
    )

    df_all["district_id"] = df_all["distrito"].apply(_parse_district_id)
    df_all["votos_preliminares"] = pd.to_numeric(
        df_all["votos_preliminares"], errors="coerce"
    ).fillna(0)
    df_all["electo_nominado"] = pd.to_numeric(
        df_all["electo_nominado"], errors="coerce"
    ).fillna(0)

    # CANONICAL — un registro por candidato, agregado sobre las mesas del distrito
    agrupado = (
        df_all.groupby(
            ["CUT", "cod_candidato", "nombre_candidato", "pacto", "party_id",
             "district_id", "independent_status"],
            dropna=False, as_index=False,
        )
        .agg(votes=("votos_preliminares", "sum"),
             officially_elected=("electo_nominado", "max"))
    )

    df_canonical = pd.DataFrame({
        "election_id":         election_id,
        "office":              office,
        "district_id":         agrupado["district_id"].astype(int),
        "CUT":                 agrupado["CUT"].astype(int),
        "list_id":             agrupado["pacto"].astype(str).str.strip(),
        "party_id":            agrupado["party_id"],
        "candidate_id":        agrupado["cod_candidato"].astype(int),
        "candidate_name":      agrupado["nombre_candidato"].astype(str).str.strip(),
        "independent_status":  agrupado["independent_status"].astype(bool),
        "votes":               agrupado["votes"].astype(int),
        "officially_elected":  agrupado["officially_elected"] == 1,
    })[_CANDIDATE_RECORD_FIELDS]

    provenance_info = {
        "administrative_rows_removed": admin_removed_total,
        "commune_aliases_applied":     aliases_applied,
        "cut_normalizations":          cut_normalizations,
        "rows_without_party":          rows_without_party,
        "unresolved_entities":         unresolved_entities,
        "source_provenance":           source_provenance,
    }
    return df_canonical, provenance_info


def import_results(
    source_path: "str | Path",
    election_id: str = "CL-2025-DIP",
) -> tuple[pd.DataFrame, dict]:
    """
    Importa escaños oficiales por distrito y pacto a schema canónico.

    Equivalente empaquetado de escanos_oficiales_2025.csv
    (datos/scripts_extra/escanos.py::procesar_y_validar_escanos, sin la
    validación de invariantes con `assert` — ver "Deuda técnica").

    Parameters
    ----------
    source_path : str | Path
        Directorio con los 28 Excel de SERVEL, o un patrón glob explícito.
    election_id : str

    Returns
    -------
    (df_canonical, provenance) donde df_canonical tiene columnas:
        election_id, district_id, list_id, seats_won
    y provenance es un dict con: total_seats, districts_covered.
    """
    archivos = _read_raw_servel_diputados(source_path)

    bloques = []
    for _, df in archivos:
        df = df.copy()
        df.columns = [c.strip().lower() for c in df.columns]
        df["electo_nominado"] = pd.to_numeric(
            df["electo_nominado"], errors="coerce"
        ).fillna(0).astype(int)
        df_electos = df[df["electo_nominado"] == 1]
        bloques.append(
            df_electos[["distrito", "pacto", "cod_candidato"]]
            .drop_duplicates(subset=["distrito", "cod_candidato"])
        )

    df_all = pd.concat(bloques, ignore_index=True)
    df_all["district_id"] = df_all["distrito"].apply(_parse_district_id)

    tabla = (
        df_all.groupby(["district_id", "pacto"], as_index=False)
        .agg(seats_won=("cod_candidato", "count"))
        .sort_values(["district_id", "pacto"])
        .reset_index(drop=True)
    )

    df_canonical = pd.DataFrame({
        "election_id": election_id,
        "district_id": tabla["district_id"].astype(int),
        "list_id":     tabla["pacto"].astype(str).str.strip(),
        "seats_won":   tabla["seats_won"].astype(int),
    })

    provenance_info = {
        "total_seats":       int(df_canonical["seats_won"].sum()),
        "districts_covered": int(df_canonical["district_id"].nunique()),
    }
    return df_canonical, provenance_info


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
