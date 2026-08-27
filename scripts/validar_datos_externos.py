"""
scripts/validar_datos_externos.py
===================================
Valida los 4 archivos de datos externos usados por scripts/malapportionment.py
y scripts/electoral_analysis.py (ver README.md § Datos externos):

    datos/poblacion_comunal_censo2024.csv
    datos/servel_2025_por_cut.csv
    datos/asignacion_vigente.json
    datos/pacto_map_2025.json

Para cada archivo: imprime shape/keys y una muestra de 3 filas, y corre un
conjunto de verificaciones específicas (columnas, nulos, formato de CUT,
cobertura), cada una etiquetada OK o WARNING. Termina con un resumen
agregado y código de salida != 0 si hubo alguna WARNING (para uso en CI).

Uso (sin argumentos, resuelve datos/ relativo a la raíz del proyecto):
    python scripts/validar_datos_externos.py

Nota sobre el número de comunas esperado
-----------------------------------------
Los archivos reales del repo (poblacion_comunal_censo2024.csv,
asignacion_vigente.json) tienen consistentemente 346 comunas, no 345 —
346 es también el número documentado en README.md § Datos externos
(346 comunas → 28 distritos, Ley 18.700/20.840). Si tu fuente de verdad
es distinta, ajusta EXPECTED_N_COMUNAS abajo.
"""

import json
import os
import sys
import unicodedata

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import chiledist as cd  # reutiliza cd.normalize_cut (chiledist/hierarchy.py)

DATOS_DIR = os.path.join(ROOT, "datos")

CENSUS_PATH     = os.path.join(DATOS_DIR, "poblacion_comunal_censo2024.csv")
SERVEL_PATH     = os.path.join(DATOS_DIR, "servel_2025_por_cut.csv")
ASSIGNMENT_PATH = os.path.join(DATOS_DIR, "asignacion_vigente.json")
PACTO_PATH      = os.path.join(DATOS_DIR, "pacto_map_2025.json")

EXPECTED_N_COMUNAS   = 346  # ver nota en el docstring
EXPECTED_N_DISTRITOS = 28
VALID_REGIONES       = set(range(1, 17))

CHECKS: list[tuple[str, str, str, str]] = []  # (archivo, verificación, status, detalle)


# ──────────────────────────────────────────────────────────────────────────────
# Registro de verificaciones
# ──────────────────────────────────────────────────────────────────────────────

def registrar(archivo: str, nombre: str, ok: bool, detalle: str = "") -> bool:
    status = "OK" if ok else "WARNING"
    CHECKS.append((archivo, nombre, status, detalle))
    icono = "✓" if ok else "⚠"
    linea = f"  [{status:7s}] {icono} {nombre}"
    if detalle:
        linea += f" — {detalle}"
    print(linea)
    return ok


def _normalizar_texto(s: str) -> str:
    """Mayúsculas + sin acentos, para comparar nombres de partido con
    tolerancia a diferencias de formato (no de contenido)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.strip().upper()


# ──────────────────────────────────────────────────────────────────────────────
# 1. Carga + shape/keys + muestra
# ──────────────────────────────────────────────────────────────────────────────

def cargar_csv(path: str, nombre: str) -> pd.DataFrame | None:
    print(f"\n{'='*70}\n{nombre}\n{'='*70}")
    print(f"  Ruta: {path}")
    if not os.path.exists(path):
        print("  ✗ Archivo no encontrado.")
        return None
    # CUT como string al leer: preserva el cero a la izquierda si el archivo
    # lo trae (ej. servel_2025_por_cut.csv), en vez de que pandas lo infiera
    # como int y lo pierda silenciosamente.
    df = pd.read_csv(path, dtype={"CUT": str})
    print(f"  Shape: {df.shape[0]} filas × {df.shape[1]} columnas")
    print(f"  Columnas: {list(df.columns)}")
    print("  Muestra (3 filas):")
    print(df.head(3).to_string(index=False))
    return df


def cargar_json(path: str, nombre: str) -> dict | None:
    print(f"\n{'='*70}\n{nombre}\n{'='*70}")
    print(f"  Ruta: {path}")
    if not os.path.exists(path):
        print("  ✗ Archivo no encontrado.")
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"  N keys: {len(data)}")
    print("  Muestra (3 keys):")
    for k, v in list(data.items())[:3]:
        print(f"    {k!r}: {v!r}")
    return data


# ──────────────────────────────────────────────────────────────────────────────
# 2. poblacion_comunal_censo2024.csv
# ──────────────────────────────────────────────────────────────────────────────

def validar_censo(df: pd.DataFrame | None) -> None:
    archivo = "poblacion_comunal_censo2024.csv"
    print(f"\n--- Verificaciones: {archivo} ---")
    if df is None:
        registrar(archivo, "archivo cargado", False, "no se pudo cargar")
        return

    cols_ok = {"CUT", "personas"}.issubset(df.columns)
    registrar(archivo, "columnas CUT y personas presentes", cols_ok,
               "" if cols_ok else f"columnas encontradas: {list(df.columns)}")
    if not cols_ok:
        return

    n_nulos = int(df[["CUT", "personas"]].isna().sum().sum())
    registrar(archivo, "sin nulos en CUT/personas", n_nulos == 0,
               f"{n_nulos} valores nulos" if n_nulos else "")

    # CUT válido: al normalizar a 5 dígitos, todo dígitos y con región 1-16.
    invalidos = []
    for v in df["CUT"].dropna():
        try:
            norm = cd.normalize_cut(v)
            region = int(norm[:2])
            if len(norm) != 5 or not norm.isdigit() or region not in VALID_REGIONES:
                invalidos.append(v)
        except (ValueError, TypeError):
            invalidos.append(v)
    registrar(archivo, "CUT válido (entero de 5 dígitos tras normalizar, región 1-16)",
               len(invalidos) == 0,
               f"{len(invalidos)} valores inválidos: {invalidos[:5]}" if invalidos else "")

    n_comunas = df["CUT"].nunique()
    registrar(archivo, f"cubre las {EXPECTED_N_COMUNAS} comunas esperadas",
               n_comunas == EXPECTED_N_COMUNAS,
               f"{n_comunas} comunas encontradas (esperadas: {EXPECTED_N_COMUNAS})"
               if n_comunas != EXPECTED_N_COMUNAS else "")

    n_dup = int(df["CUT"].duplicated().sum())
    registrar(archivo, "sin CUT duplicados", n_dup == 0,
               f"{n_dup} duplicados" if n_dup else "")

    personas_num = pd.to_numeric(df["personas"], errors="coerce")
    n_no_positivas = int((personas_num.fillna(0) <= 0).sum())
    registrar(archivo, "personas > 0 en todas las comunas", n_no_positivas == 0,
               f"{n_no_positivas} filas con personas <= 0" if n_no_positivas else "")


# ──────────────────────────────────────────────────────────────────────────────
# 3. servel_2025_por_cut.csv
# ──────────────────────────────────────────────────────────────────────────────

def validar_servel(df: pd.DataFrame | None) -> None:
    archivo = "servel_2025_por_cut.csv"
    print(f"\n--- Verificaciones: {archivo} ---")
    if df is None:
        registrar(archivo, "archivo cargado", False, "no se pudo cargar")
        return

    cols_ok = {"CUT", "partido", "votos"}.issubset(df.columns)
    registrar(archivo, "columnas CUT, partido y votos presentes", cols_ok,
               "" if cols_ok else f"columnas encontradas: {list(df.columns)}")
    if not cols_ok:
        return

    n_nulos = int(df[["CUT", "partido", "votos"]].isna().sum().sum())
    registrar(archivo, "sin nulos en CUT/partido/votos", n_nulos == 0,
               f"{n_nulos} valores nulos" if n_nulos else "")

    votos_num = pd.to_numeric(df["votos"], errors="coerce").fillna(0)
    cut_norm = df["CUT"].map(cd.normalize_cut)
    votos_por_cut = votos_num.groupby(cut_norm).sum()
    n_cut_sin_votos = int((votos_por_cut <= 0).sum())
    total_nacional = int(votos_num.sum())
    registrar(archivo, "suma de votos por CUT es razonable (> 0)",
               n_cut_sin_votos == 0 and total_nacional > 0,
               f"{n_cut_sin_votos} CUT con suma de votos <= 0 de "
               f"{len(votos_por_cut)}; total nacional: {total_nacional:,}")


# ──────────────────────────────────────────────────────────────────────────────
# 4. asignacion_vigente.json
# ──────────────────────────────────────────────────────────────────────────────

def validar_asignacion(data: dict | None) -> None:
    archivo = "asignacion_vigente.json"
    print(f"\n--- Verificaciones: {archivo} ---")
    if data is None:
        registrar(archivo, "archivo cargado", False, "no se pudo cargar")
        return

    n = len(data)
    registrar(archivo, f"exactamente {EXPECTED_N_COMUNAS} keys", n == EXPECTED_N_COMUNAS,
               f"{n} keys encontradas (esperadas: {EXPECTED_N_COMUNAS})"
               if n != EXPECTED_N_COMUNAS else "")

    keys_str_ok = all(isinstance(k, str) for k in data)
    registrar(archivo, "CUTs son strings", keys_str_ok)

    fuera_de_rango = [v for v in data.values()
                       if not (isinstance(v, int) and 1 <= v <= EXPECTED_N_DISTRITOS)]
    registrar(archivo, f"valores enteros entre 1 y {EXPECTED_N_DISTRITOS}",
               len(fuera_de_rango) == 0,
               f"{len(fuera_de_rango)} valores fuera de rango: {fuera_de_rango[:5]}"
               if fuera_de_rango else "")

    distritos_presentes = set(data.values())
    distritos_esperados = set(range(1, EXPECTED_N_DISTRITOS + 1))
    faltantes = distritos_esperados - distritos_presentes
    registrar(archivo, f"los {EXPECTED_N_DISTRITOS} distritos aparecen",
               len(faltantes) == 0,
               f"faltan: {sorted(faltantes)}" if faltantes else "")


# ──────────────────────────────────────────────────────────────────────────────
# 5. pacto_map_2025.json vs partidos en servel_2025_por_cut.csv
# ──────────────────────────────────────────────────────────────────────────────

def validar_pacto_map(pacto_map: dict | None, servel_df: pd.DataFrame | None) -> None:
    archivo = "pacto_map_2025.json"
    print(f"\n--- Verificaciones: {archivo} ---")
    if pacto_map is None:
        registrar(archivo, "archivo cargado", False, "no se pudo cargar")
        return
    if servel_df is None or "partido" not in servel_df.columns:
        registrar(archivo, "cobertura de partidos SERVEL", False,
                   "no se pudo leer la columna partido de servel_2025_por_cut.csv")
        return

    partidos = sorted(servel_df["partido"].dropna().unique())
    faltantes_exacto = [p for p in partidos if p not in pacto_map]

    registrar(
        archivo,
        "cobertura de partidos SERVEL (match exacto de texto)",
        len(faltantes_exacto) == 0,
        f"{len(partidos) - len(faltantes_exacto)}/{len(partidos)} cubiertos; "
        f"faltan: {faltantes_exacto[:5]}{'…' if len(faltantes_exacto) > 5 else ''}"
        if faltantes_exacto else "",
    )

    if not faltantes_exacto:
        return

    # Diagnóstico: ¿es solo un problema de mayúsculas/acentos, o hay
    # partidos genuinamente ausentes de pacto_map_2025.json? El código real
    # (.map(pacto_map) en chiledist/electoral/dhondt.py y en los bloques
    # B1/B4 de scripts/electoral_analysis.py) hace un lookup EXACTO — si el
    # problema es solo de formato, esto degrada en silencio el D'Hondt
    # binivel a uninivel para esos partidos, sin ningún error.
    pacto_map_norm = {_normalizar_texto(k) for k in pacto_map}
    faltantes_tras_normalizar = [p for p in faltantes_exacto
                                  if _normalizar_texto(p) not in pacto_map_norm]

    if not faltantes_tras_normalizar:
        detalle = (
            f"los {len(faltantes_exacto)} partidos no cubiertos SÍ están en "
            "pacto_map_2025.json con otra capitalización/acentuación (ej. "
            "'EVOLUCION POLITICA' en SERVEL vs 'Evolución Política' en "
            "pacto_map). El lookup real es case/acento-sensible: normaliza "
            "un lado o el otro antes de hacer .map(pacto_map)."
        )
    else:
        detalle = (
            f"{len(faltantes_tras_normalizar)} partido(s) no están en "
            f"pacto_map_2025.json ni siquiera normalizando mayúsculas/acentos: "
            f"{faltantes_tras_normalizar[:5]}"
        )
    registrar(archivo, "diagnóstico de la brecha de cobertura", False, detalle)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Resumen
# ──────────────────────────────────────────────────────────────────────────────

def imprimir_resumen() -> int:
    print(f"\n{'='*70}\nRESUMEN\n{'='*70}")
    for archivo, nombre, status, detalle in CHECKS:
        icono = "✓" if status == "OK" else "⚠"
        linea = f"  [{status:7s}] {icono} [{archivo}] {nombre}"
        if detalle:
            linea += f" — {detalle}"
        print(linea)

    n_ok = sum(1 for *_, status, _ in CHECKS if status == "OK")
    n_warn = len(CHECKS) - n_ok
    print(f"\n  Total: {len(CHECKS)} verificaciones — {n_ok} OK, {n_warn} WARNING")
    return n_warn


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("chiledist — Validación de datos externos")
    print(f"  Directorio: {DATOS_DIR}")

    df_censo  = cargar_csv(CENSUS_PATH, "poblacion_comunal_censo2024.csv")
    df_servel = cargar_csv(SERVEL_PATH, "servel_2025_por_cut.csv")
    asignacion = cargar_json(ASSIGNMENT_PATH, "asignacion_vigente.json")
    pacto_map  = cargar_json(PACTO_PATH, "pacto_map_2025.json")

    print(f"\n{'='*70}\nVERIFICACIONES\n{'='*70}")
    validar_censo(df_censo)
    validar_servel(df_servel)
    validar_asignacion(asignacion)
    validar_pacto_map(pacto_map, df_servel)

    n_warn = imprimir_resumen()
    sys.exit(1 if n_warn > 0 else 0)


if __name__ == "__main__":
    main()
