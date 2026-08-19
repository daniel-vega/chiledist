import argparse
import glob
import os
import sys
import unicodedata
import pandas as pd
# chiledist se importa dentro de __main__, después de insertar --base-dir en
# sys.path -- este script vive fuera del repo de chiledist, así que no basta
# con "import chiledist" a nivel de módulo salvo que ya esté instalado.

def normalizar(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8")
    return texto.strip().upper()

# 1. Definición de la validación matemática de invariantes
def validar_invariantes(df_electos: pd.DataFrame):
    MAGNITUDES_OFICIALES = {
        "DISTRITO 1": 3, "DISTRITO 2": 3, "DISTRITO 3": 5, "DISTRITO 4": 5,
        "DISTRITO 5": 7, "DISTRITO 6": 8, "DISTRITO 7": 8, "DISTRITO 8": 8,
        "DISTRITO 9": 7, "DISTRITO 10": 8, "DISTRITO 11": 6, "DISTRITO 12": 7,
        "DISTRITO 13": 5, "DISTRITO 14": 6, "DISTRITO 15": 5, "DISTRITO 16": 4,
        "DISTRITO 17": 7, "DISTRITO 18": 4, "DISTRITO 19": 5, "DISTRITO 20": 8,
        "DISTRITO 21": 5, "DISTRITO 22": 4, "DISTRITO 23": 7, "DISTRITO 24": 5,
        "DISTRITO 25": 4, "DISTRITO 26": 5, "DISTRITO 27": 3, "DISTRITO 28": 3
    }

    # Invariante 1: Total nacional de escaños == 155
    total_nacional = len(df_electos)
    assert total_nacional == 155, f"Error: Total nacional es {total_nacional}, esperado 155."

    # Invariante 2: Escaños por distrito == Magnitud legal
    conteo_distrital = df_electos.groupby("distrito_norm")["cod_candidato"].count().to_dict()
    for distrito, magnitud in MAGNITUDES_OFICIALES.items():
        escanos_distrito = conteo_distrital.get(distrito, 0)
        assert escanos_distrito == magnitud, f"Error en {distrito}: {escanos_distrito} != {magnitud}"

    print("Todos los invariantes matemáticos fueron verificados exitosamente.")

# 2. Extracción y procesamiento
def procesar_y_validar_escanos(patron_archivos: str, output_csv: str = "escanos_oficiales_2025.csv"):
    archivos = sorted(glob.glob(patron_archivos))
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos con el patrón: {patron_archivos}")

    candidatos_electos = []

    for archivo in archivos:
        df = pd.read_excel(archivo, engine="openpyxl")
        df.columns = [c.strip().lower() for c in df.columns]

        df["electo_nominado"] = pd.to_numeric(df["electo_nominado"], errors="coerce").fillna(0).astype(int)
        df_electos = df[df["electo_nominado"] == 1].copy()

        cols = ["distrito", "pacto", "partido", "cod_candidato", "nombre_candidato"]
        df_unicos = df_electos[cols].drop_duplicates(subset=["distrito", "cod_candidato"]).copy()
        df_unicos["distrito_norm"] = df_unicos["distrito"].apply(normalizar)

        candidatos_electos.append(df_unicos)

    df_total_electos = pd.concat(candidatos_electos, ignore_index=True)

    # --- INVOCACIÓN DE LA VALIDACIÓN AQUÍ ---
    validar_invariantes(df_total_electos)

    # Agrupar y exportar tabla de escaños por distrito y pacto
    tabla_escanos = (
        df_total_electos.groupby(["distrito", "pacto"], as_index=False)
        .agg(escanos=("cod_candidato", "count"))
        .sort_values(by=["distrito", "pacto"])
    )

    tabla_escanos.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Archivo de referencia generado: {output_csv}")

# 3. Mapeo comuna (nombre) -> CUT, vía la capa "comunal" de chiledist
def construir_mapa_comuna_cut(base_dir: str) -> dict:
    """
    {nombre_comuna_normalizado: CUT}, desde cd.load_layer("comunal", ...).
    Se normaliza con la misma función normalizar() usada para los nombres
    de comuna del Excel (strip tildes + upper), para que ambos lados
    calcen sin importar tildes/mayúsculas.
    """
    comunas = cd.load_layer("comunal", base_dir=base_dir)
    return dict(zip(comunas["N_COMUNA"].apply(normalizar), comunas["CUT"]))

# Alias de nombre de comuna: el Excel de SERVEL usa variantes ortográficas
# (G/H, con/sin guion) o sufijos que no calzan tal cual con N_COMUNA del
# shapefile APC2023, aunque se trata de la misma comuna. Antártica (CUT
# 12202) NO tiene alias: es un caso genuino sin cobertura cartográfica en
# APC2023 (no tiene polígono, no es un problema de nombre), así que sus
# ~968 votos quedan excluidos del CSV y se siguen reportando como
# ADVERTENCIA más abajo.
ALIASES_COMUNA = {
    "MARCHIGUE":                   "MARCHIHUE",
    "TREHUACO":                    "TREGUACO",
    "PAIHUANO":                    "PAIGUANO",
    "LLAY-LLAY":                   "LLAILLAY",
    "CABO DE HORNOS(EX-NAVARINO)": "CABO DE HORNOS",
}

# 4. Votos por candidato y CUT, para D'Hondt binivel con candidatos
#    independientes como entidades separadas (en vez de la bolsa "IND"
#    agregada de servel_2025_por_cut.csv).
def procesar_candidatos_por_cut(
    patron_archivos: str,
    nombre_cut_map: dict,
    output_csv: str = "datos/servel_2025_candidatos.csv",
):
    archivos = sorted(glob.glob(patron_archivos))
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos con el patrón: {patron_archivos}")

    bloques = []
    verificacion = []

    for archivo in archivos:
        df = pd.read_excel(archivo, engine="openpyxl")
        df.columns = [c.strip().lower() for c in df.columns]

        distrito = df["distrito"].iloc[0]

        # PASO 3 (parte 1): total oficial de sufragios válidos del distrito,
        # tal como viene reportado por mesa en el propio Excel.
        total_sufragios_validos = df.loc[
            df["nombre_candidato"] == "Total Sufragios Validamente Emitidos",
            "votos_preliminares",
        ].sum()

        nombre_norm = df["comuna"].apply(normalizar).map(
            lambda n: ALIASES_COMUNA.get(n, n)
        )
        df["cut"] = nombre_norm.map(nombre_cut_map)

        df_cand = df[df["cod_candidato"].notna()].copy()
        total_candidatos_excel = df_cand["votos_preliminares"].sum()

        # Comunas del Excel sin CUT mapeado (ej. territorios sin polígono en
        # el shapefile APC2023, o nombres con sufijos que no calzan tal cual
        # con N_COMUNA) -- se avisa explícitamente en vez de descartar en
        # silencio.
        sin_mapear = df_cand.loc[df_cand["cut"].isna(), "comuna"].unique()
        votos_sin_mapear = df_cand.loc[df_cand["cut"].isna(), "votos_preliminares"].sum()
        if len(sin_mapear):
            print(
                f"  ADVERTENCIA [{os.path.basename(archivo)}]: comunas sin CUT "
                f"mapeado: {sorted(sin_mapear)} ({votos_sin_mapear:.0f} votos de "
                f"candidatos quedan fuera de {output_csv})"
            )

        df_cand = df_cand.dropna(subset=["cut"])

        agrupado = (
            df_cand
            .groupby(
                ["cut", "cod_candidato", "nombre_candidato", "pacto", "partido"],
                dropna=False,
            )["votos_preliminares"]
            .sum()
            .reset_index()
            .rename(columns={"votos_preliminares": "votos", "cut": "CUT"})
        )
        bloques.append(agrupado)

        verificacion.append({
            "distrito": distrito,
            "total_candidatos_excel": total_candidatos_excel,
            "total_sufragios_validos": total_sufragios_validos,
            "diff_excel": total_candidatos_excel - total_sufragios_validos,
            "votos_sin_cut": votos_sin_mapear,
        })

    tabla_verificacion = pd.DataFrame(verificacion)
    print("\nVerificación por distrito (candidatos Excel vs Total Sufragios Válidamente Emitidos):")
    print(tabla_verificacion.to_string(index=False))

    df_candidatos = pd.concat(bloques, ignore_index=True)
    df_candidatos = df_candidatos[
        ["CUT", "cod_candidato", "nombre_candidato", "partido", "pacto", "votos"]
    ]
    df_candidatos["CUT"] = df_candidatos["CUT"].astype(int)
    df_candidatos["cod_candidato"] = df_candidatos["cod_candidato"].astype(int)

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    df_candidatos.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nArchivo de candidatos generado: {output_csv} ({len(df_candidatos)} filas)")

    return df_candidatos, tabla_verificacion

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-dir", default=".",
        help="Directorio raíz con SHP_APC2023_R* (para cd.load_layer('comunal', ...))",
    )
    args = parser.parse_args()

    sys.path.insert(0, os.path.abspath(args.base_dir))
    import chiledist as cd

    procesar_y_validar_escanos("PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx")

    nombre_cut_map = construir_mapa_comuna_cut(args.base_dir)
    procesar_candidatos_por_cut(
        "PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx", nombre_cut_map,
    )
