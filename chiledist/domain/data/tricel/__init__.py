"""
chiledist.domain.data.tricel
==============================
Carga de datos oficiales del Tribunal Calificador de Elecciones (TRICEL) —
proclamaciones finales y votación mesa a mesa del escrutinio oficial,
capa 0 (Domain).

Estos datos son la "verdad oficial" contra la cual se valida el motor
D'Hondt del paquete (ver chiledist.validation) — a diferencia de
domain.data.servel, que trae la votación *preliminar* (noche de la
elección), TRICEL trae el escrutinio *final* tras el proceso de
calificación. Los totales de ambas fuentes difieren candidato a
candidato (ver README.md § Datos externos).

Estructura del Excel oficial DISTRITO-XX.xlsx (una hoja de cálculo por
distrito, 28 en total), determinada por inspección directa (no
documentada por TRICEL):

    DETERMINACION   cálculo D'Hondt oficial por pacto (no se usa aquí)
    CANDIDATOS      roster completo del distrito: número de candidato
                    corto (`num_tricel`, columna "CANDIDATOS"), nombre,
                    partido, votos totales
    ELECTOS         lista ya resuelta de candidatos electos: nombre +
                    votos totales, sin `num_tricel` propio
    MESA A MESA     una fila por mesa + una fila final de totales
                    (identificada por NaN en todas las columnas de
                    identificación de mesa); candidatos como columnas
    BASEORIGINAL    no utilizada por este módulo

`num_tricel` (hoja CANDIDATOS) se relaciona con `candidate_id`
(cod_candidato de SERVEL, ver domain.data.servel.CandidateRecord) por
`num_tricel == candidate_id % 100` — verificado exhaustivamente sobre
Distrito 1 (25/25 candidatos, sin excepciones) durante la inspección
previa a esta implementación. Como la hoja ELECTOS no trae `num_tricel`
directamente, el cruce se hace en dos pasos dentro del mismo archivo:
ELECTOS → (nombre) → CANDIDATOS → num_tricel → SERVEL.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from .._paths import get_servel_dir, get_tricel_dir
from ..servel import import_candidates as _import_servel_candidates
from ..servel import normalize_commune_name
from ..servel.provenance import compute_provenance


@dataclasses.dataclass
class ProclamationRecord:
    """Una proclamación oficial TRICEL — schema canónico de import_proclamations()."""
    election_id: str
    district_id: int          # número de distrito (1-28)
    candidate_id: int          # cod_candidato SERVEL (cruzado vía num_tricel)
    candidate_name: str
    party_id: str               # tomado del registro SERVEL cruzado (ya normalizado)
    list_id: str                  # pacto — tomado del registro SERVEL cruzado
    votes_final: int                # escrutinio oficial (hoja ELECTOS, TOTALES)
    officially_elected: bool         # siempre True — viene de la hoja ELECTOS


_PROCLAMATION_RECORD_FIELDS: list[str] = [
    f.name for f in dataclasses.fields(ProclamationRecord)
]


#: Columnas de identificación de mesa en la hoja MESA A MESA — determinadas
#: por inspección directa de DISTRITO-01.xlsx. Usadas para EXCLUIR estas
#: columnas de la detección de candidatos (nunca son nombres de
#: candidato) — no para detectar la fila de totales, ver _MESA_GEO_COLS.
_MESA_ID_COLS = {
    "Número Región", "Región", "Número Provincia", "Provincia",
    "Número Comuna", "Comuna", "Número Distrito", "Número Distrito.1",
    "Número Circunscripción Electoral", "Circunscripción Electoral",
    "Tipo de mesa", "Mesa", "Fusionadas", "Local", "Dirección del local",
}

#: Columnas geográficas de MESA A MESA que están en NaN en la fila de
#: totales distritales en los 28 archivos reales — a diferencia de
#: "Tipo de mesa"/"Mesa"/"Fusionadas"/"Local"/"Dirección del local", que
#: en Distrito-15 y Distrito-16 NO están en NaN en esa fila (traen "0" o
#: sumas numéricas en vez de blanco), así que no son confiables para
#: detectar la fila de totales.
_MESA_GEO_COLS = [
    "Número Región", "Región",
    "Número Provincia", "Provincia",
    "Número Comuna", "Comuna",
    "Número Distrito", "Número Circunscripción Electoral",
    "Circunscripción Electoral",
]

#: Columnas administrativas al final de MESA A MESA (no son candidatos).
_MESA_ADMIN_COLS = {"Nulos", "Blancos", "Total votos", "Inscritos"}


def _safe_int(x) -> int:
    """
    int() tolerante a NaN — Distrito-08 trae Nulos/Blancos en NaN en su
    fila de totales real (el archivo oficial no los completó ahí,
    aunque sí en la fila de subtotal anterior); `int(x or 0)` no lo
    captura porque NaN es truthy en Python.
    """
    v = pd.to_numeric(x, errors="coerce")
    return 0 if pd.isna(v) else int(v)

def _district_id_from_filename(path: "str | Path") -> Optional[int]:
    """Extrae el número de distrito de un nombre tipo 'DISTRITO-01.xlsx'."""
    match = re.search(r"\d+", Path(path).stem)
    return int(match.group()) if match else None


def _list_tricel_files(source_dir: "str | Path") -> list[Path]:
    """
    Lista los DISTRITO-XX.xlsx de un directorio, ordenados por distrito.

    source_dir puede ser la carpeta raíz de datos (con un subdirectorio
    TRICEL_2025/) o ya ser la carpeta TRICEL misma — se prueba primero
    source_dir/TRICEL_2025 y se cae de vuelta a source_dir si no existe.
    Los archivos reales vienen como "Distrito-01.xlsx" (no "DISTRITO-"),
    así que se prueban ambos patrones de glob.
    """
    source_dir = Path(source_dir)
    tricel_dir = source_dir / "TRICEL_2025"
    if not tricel_dir.exists():
        # fallback: asumir que source_dir ya es el directorio TRICEL
        tricel_dir = source_dir
    if not tricel_dir.is_dir():
        raise FileNotFoundError(f"Directorio TRICEL no encontrado: {tricel_dir}")

    archivos = (list(tricel_dir.glob("DISTRITO-*.xlsx")) or
                list(tricel_dir.glob("Distrito-*.xlsx")))
    if not archivos:
        raise FileNotFoundError(
            f"No se encontraron archivos DISTRITO-*.xlsx en {tricel_dir}"
        )
    return sorted(archivos, key=lambda p: _district_id_from_filename(p) or 0)


def _read_candidatos_sheet(path: "str | Path") -> pd.DataFrame:
    """
    Lee la hoja CANDIDATOS: roster completo del distrito con num_tricel.

    El encabezado real está en la fila 6 (índice 5); las filas de
    encabezado de pacto ("B. VERDES, REGIONALISTAS...") y de subtotal
    ("TOTAL UNIDAD POR CHILE") tienen la columna `num_tricel` vacía y se
    descartan.
    """
    raw = pd.read_excel(path, sheet_name="CANDIDATOS", header=5)
    raw = raw.rename(columns={
        "CANDIDATOS": "num_tricel",
        "Unnamed: 2": "candidate_name",
        "PARTIDO POLÍTICO": "party_raw",
        "TOTALES": "votes_tricel",
    })
    real = raw[raw["num_tricel"].notna()].copy()
    real["num_tricel"] = real["num_tricel"].astype(int)
    real["candidate_name"] = real["candidate_name"].astype(str).str.strip()
    return real[["num_tricel", "candidate_name", "party_raw", "votes_tricel"]]


#: Etiquetas de la columna de votos en ELECTOS que no ameritan registrarse
#: como anomalía en provenance — variación normal entre distritos.
_EXPECTED_ELECTOS_VOTES_LABELS = {"TOTALES", "VOTOS"}


def _read_electos_sheet(path: "str | Path") -> "tuple[pd.DataFrame, str]":
    """
    Lee la hoja ELECTOS: lista ya resuelta de candidatos electos + votos.

    La estructura de 4 columnas es consistente en los 28 distritos
    (verificado por inspección directa), pero la etiqueta de la 4ta
    columna (votos) no lo es: "TOTALES" en 11 distritos, "VOTOS" en 16,
    y "VOCALES" en Distrito-10 — un error tipográfico del archivo
    oficial TRICEL, tratado igual como columna de votos. Un rename por
    nombre exacto solo capturaba "TOTALES" y fallaba con KeyError en
    los otros 17 distritos — se renombra por posición en su lugar.

    Returns
    -------
    (df, votes_col_label) — df con columnas candidate_name/votes_final,
    y la etiqueta original de la columna de votos (para que
    import_proclamations() registre la anomalía en provenance cuando no
    es "TOTALES" ni "VOTOS").
    """
    raw = pd.read_excel(path, sheet_name="ELECTOS", header=6)
    votes_col_label = str(raw.columns[3])

    # Renombrar por posición — robusto ante variaciones
    # de etiqueta entre distritos ("TOTALES"/"VOTOS"/"VOCALES")
    raw = raw.iloc[:, [2, 3]].copy()
    raw.columns = ["candidate_name", "votes_final"]

    real = raw[raw["candidate_name"].notna()].copy()
    real["candidate_name"] = real["candidate_name"].astype(str).str.strip()
    real["votes_final"] = pd.to_numeric(real["votes_final"], errors="coerce").fillna(0).astype(int)
    return real[["candidate_name", "votes_final"]], votes_col_label


def import_proclamations(
    source_dir: "str | Path | None" = None,
    election_id: str = "CL-2025-DIP",
    base_dir: Optional[str] = None,
    commune_cut_map: Optional[dict] = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Importa las proclamaciones oficiales TRICEL a schema canónico.

    RAW: lee la hoja ELECTOS (nombre + votos finales) y la hoja
        CANDIDATOS (num_tricel + nombre + partido) de cada
        DISTRITO-XX.xlsx en source_dir.
    NORMALIZED: cruza cada electo con SERVEL en dos pasos — (1) dentro
        del mismo archivo, empareja el nombre de ELECTOS con CANDIDATOS
        para obtener su num_tricel; (2) filtra domain.data.servel
        .import_candidates() al mismo district_id y busca
        candidate_id % 100 == num_tricel — para obtener candidate_id,
        party_id y list_id ya normalizados.
    CANONICAL: un registro por electo con el schema exacto de
        ProclamationRecord.

    Parameters
    ----------
    source_dir : str | Path, opcional
        Directorio con los DISTRITO-XX.xlsx de TRICEL. Si es None, usa
        chiledist.domain.data.get_tricel_dir() (variable de entorno
        CHILEDIST_DATA_DIR, ver .env.example).
    election_id : str
    base_dir : str, opcional
        Pasado a domain.data.servel.import_candidates() para resolver
        comuna → CUT (requerido solo si no se pasa `commune_cut_map`).
    commune_cut_map : dict, opcional
        Pasado a domain.data.servel.import_candidates() — permite
        testear sin shapefiles APC2023 reales. Igual que en
        import_candidates(), no pedido explícitamente en el encargo
        original; se agregó por la misma razón de testabilidad (ver
        "Deuda técnica" en el reporte de esta etapa).

    Returns
    -------
    (df_canonical, provenance) donde df_canonical tiene exactamente las
    columnas de ProclamationRecord y provenance es un dict con:
        source                  : "TRICEL"
        districts_loaded        : int
        candidates_matched      : int
        candidates_unmatched    : list[str]  # nombres de ELECTOS sin cruce
        sha256_by_district      : dict[int, str]
        votes_column_anomalies  : dict[str, str]  # {distrito: etiqueta}
            distritos donde la columna de votos de ELECTOS no se llama
            "TOTALES" ni "VOTOS" — ej. {"10": "VOCALES"} (columna
            etiquetada "VOCALES" en el archivo TRICEL oficial de
            Distrito-10, probablemente error tipográfico, tratada igual
            como votos — ver _read_electos_sheet()).
    """
    if source_dir is None:
        source_dir = get_tricel_dir()
    archivos = _list_tricel_files(source_dir)

    servel_df, _servel_provenance = _import_servel_candidates(
        get_servel_dir(),
        election_id=election_id,
        base_dir=base_dir,
        commune_cut_map=commune_cut_map,
    )
    servel_df = servel_df.copy()
    servel_df["_suffix"] = servel_df["candidate_id"] % 100

    filas = []
    unmatched: list[str] = []
    sha256_by_district: dict[int, str] = {}
    votes_column_anomalies: dict[str, str] = {}

    for path in archivos:
        district_id = _district_id_from_filename(path)
        prov = compute_provenance(path, election_id, authority="TRICEL")
        sha256_by_district[district_id] = prov.sha256

        candidatos = _read_candidatos_sheet(path)
        electos, votes_col_label = _read_electos_sheet(path)
        if votes_col_label not in _EXPECTED_ELECTOS_VOTES_LABELS:
            votes_column_anomalies[str(district_id)] = votes_col_label

        name_to_num = dict(zip(
            candidatos["candidate_name"].apply(normalize_commune_name),
            candidatos["num_tricel"],
        ))

        servel_distrito = servel_df[servel_df["district_id"] == district_id]

        for _, row in electos.iterrows():
            name_norm = normalize_commune_name(row["candidate_name"])
            num_tricel = name_to_num.get(name_norm)

            servel_row = None
            if num_tricel is not None:
                match = servel_distrito[servel_distrito["_suffix"] == num_tricel]
                if not match.empty:
                    servel_row = match.iloc[0]

            if servel_row is None:
                unmatched.append(row["candidate_name"])
                continue

            filas.append({
                "election_id": election_id,
                "district_id": district_id,
                "candidate_id": int(servel_row["candidate_id"]),
                "candidate_name": row["candidate_name"],
                "party_id": servel_row["party_id"],
                "list_id": servel_row["list_id"],
                "votes_final": int(row["votes_final"]),
                "officially_elected": True,
            })

    df_canonical = pd.DataFrame(filas, columns=_PROCLAMATION_RECORD_FIELDS)

    provenance_info = {
        "source": "TRICEL",
        "districts_loaded": len(archivos),
        "candidates_matched": len(filas),
        "candidates_unmatched": unmatched,
        "sha256_by_district": sha256_by_district,
        "votes_column_anomalies": votes_column_anomalies,
    }
    return df_canonical, provenance_info


def import_votes(
    source_dir: "str | Path | None" = None,
    election_id: str = "CL-2025-DIP",
) -> tuple[pd.DataFrame, dict]:
    """
    Importa la votación mesa a mesa (totales distritales) de TRICEL.

    RAW: lee la hoja MESA A MESA de cada DISTRITO-XX.xlsx en source_dir.
    NORMALIZED: identifica la fila de totales distritales por NaN en las
        columnas geográficas (Región, Provincia, Comuna, Distrito,
        Circunscripción Electoral — ver _MESA_GEO_COLS; las columnas de
        mesa en sí, "Tipo de mesa"/"Mesa"/"Fusionadas"/"Local"/
        "Dirección del local", no son confiables para esto en todos los
        distritos); filtra las columnas de candidato (excluye columnas
        de identificación, columnas administrativas y columnas de
        pacto, cruzando contra los nombres de la hoja CANDIDATOS);
        convierte valores numéricos con _safe_int() (tolerante a NaN).
    CANONICAL: un registro por (distrito, candidato) con los totales
        distritales.

    Parameters
    ----------
    source_dir : str | Path, opcional
        Directorio con los DISTRITO-XX.xlsx de TRICEL. Si es None, usa
        chiledist.domain.data.get_tricel_dir().
    election_id : str

    Returns
    -------
    (df_canonical, provenance) donde df_canonical tiene columnas:
        election_id, district_id, candidate_name,
        votes_final, votes_null, votes_blank, total_votes
    y provenance es un dict con: source, districts_loaded,
    sha256_by_district.
    """
    if source_dir is None:
        source_dir = get_tricel_dir()
    archivos = _list_tricel_files(source_dir)

    filas = []
    sha256_by_district: dict[int, str] = {}

    for path in archivos:
        district_id = _district_id_from_filename(path)
        prov = compute_provenance(path, election_id, authority="TRICEL")
        sha256_by_district[district_id] = prov.sha256

        mesa = pd.read_excel(path, sheet_name="MESA A MESA", header=0)
        geo_cols_present = [c for c in _MESA_GEO_COLS if c in mesa.columns]
        totales_mask = mesa[geo_cols_present].isna().all(axis=1)
        totales = mesa.loc[totales_mask]
        if totales.empty:
            raise ValueError(f"No se encontró fila de totales en MESA A MESA de {path}")
        totales_row = totales.iloc[-1]

        candidatos = _read_candidatos_sheet(path)
        nombres_candidatos = set(candidatos["candidate_name"])

        votes_null = _safe_int(totales_row.get("Nulos"))
        votes_blank = _safe_int(totales_row.get("Blancos"))
        total_votes = _safe_int(totales_row.get("Total votos"))

        candidate_cols = [
            c for c in mesa.columns
            if c not in _MESA_ID_COLS
            and c not in _MESA_ADMIN_COLS
            and c in nombres_candidatos
        ]
        for col in candidate_cols:
            filas.append({
                "election_id": election_id,
                "district_id": district_id,
                "candidate_name": col,
                "votes_final": _safe_int(totales_row[col]),
                "votes_null": votes_null,
                "votes_blank": votes_blank,
                "total_votes": total_votes,
            })

    df_canonical = pd.DataFrame(filas, columns=[
        "election_id", "district_id", "candidate_name",
        "votes_final", "votes_null", "votes_blank", "total_votes",
    ])
    provenance_info = {
        "source": "TRICEL",
        "districts_loaded": len(archivos),
        "sha256_by_district": sha256_by_district,
    }
    return df_canonical, provenance_info


__all__ = ["import_proclamations", "import_votes", "ProclamationRecord"]
