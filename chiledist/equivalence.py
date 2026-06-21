"""
equivalence.py
==============
Tabla de equivalencia entre unidades censales de EEUU (Census Bureau)
y Chile (INE / APC 2023), con utilidades de conversión y descripción.

Jerarquía defendible metodológicamente:
    USA                     Chile INE
    ─────────────────────────────────
    State                   Región
    County                  Provincia
    Municipality            Comuna
    Census Tract            Distrito
    Block Group             Zona
    Census Block            Manzana
"""

from __future__ import annotations
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Estructura de unidad censal
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CensusUnit:
    """Descriptor de una unidad censal en cualquiera de los dos sistemas."""

    level: int                    # nivel jerárquico (1 = más alto)
    country: str                  # "USA" o "CHL"
    name: str                     # nombre de la unidad
    code_field: str               # campo identificador en los datos
    shapefile: Optional[str]      # nombre del shapefile APC (Chile) o TIGER (USA)
    population_field: Optional[str]  # campo de población en los datos
    description: str              # descripción del rol estadístico
    typical_size: str             # rango típico de población
    redistricting_role: str       # rol en redistritaje


# ──────────────────────────────────────────────────────────────────────────────
# Definición de unidades
# ──────────────────────────────────────────────────────────────────────────────

USA_UNITS: list[CensusUnit] = [
    CensusUnit(
        level=1, country="USA", name="State",
        code_field="STATEFP",
        shapefile="tl_*_us_state.shp",
        population_field="POP20",
        description="Unidad político-administrativa principal. "
                    "Define los límites del redistritaje legislativo federal.",
        typical_size="500k–40M hab",
        redistricting_role="Jurisdicción del plan de redistritaje",
    ),
    CensusUnit(
        level=2, country="USA", name="County",
        code_field="COUNTYFP",
        shapefile="tl_*_us_county.shp",
        population_field="POP20",
        description="Subdivisión administrativa del estado. "
                    "Frecuentemente preservada como unidad en redistritaje.",
        typical_size="10k–10M hab",
        redistricting_role="Unidad de preservación (community of interest)",
    ),
    CensusUnit(
        level=3, country="USA", name="Municipality / Place",
        code_field="PLACEFP",
        shapefile="tl_*_*_place.shp",
        population_field="POP20",
        description="Ciudad, pueblo o área designada. "
                    "No siempre coincide con county boundaries.",
        typical_size="1k–8M hab",
        redistricting_role="Unidad de preservación secundaria",
    ),
    CensusUnit(
        level=4, country="USA", name="Census Tract",
        code_field="TRACTCE",
        shapefile="tl_*_*_tract.shp",
        population_field="POP20",
        description="Unidad estadística estable de ~4.000 hab diseñada "
                    "para comparaciones intercensales. Análogo funcional "
                    "del Distrito APC chileno.",
        typical_size="1.2k–8k hab",
        redistricting_role="Unidad básica de construcción de distritos",
    ),
    CensusUnit(
        level=5, country="USA", name="Block Group",
        code_field="BLKGRPCE",
        shapefile="tl_*_*_bg.shp",
        population_field="POP20",
        description="Subdivisión del Census Tract. ~600–3.000 hab. "
                    "Análogo funcional de la Zona censal chilena.",
        typical_size="600–3k hab",
        redistricting_role="Unidad de análisis demográfico fino",
    ),
    CensusUnit(
        level=6, country="USA", name="Census Block",
        code_field="BLOCKCE20",
        shapefile="tl_*_*_tabblock20.shp",
        population_field="POP20",
        description="Unidad más pequeña del censo. Delimitada por "
                    "calles, ríos y límites legales. Análogo de la Manzana.",
        typical_size="0–600 hab",
        redistricting_role="Unidad atómica indivisible en redistritaje",
    ),
]

CHILE_UNITS: list[CensusUnit] = [
    CensusUnit(
        level=1, country="CHL", name="Región",
        code_field="COD_REGION",  # primeros 2 dígitos del CUT
        shapefile="Comunal.shp",  # se deriva del campo N_REGION
        population_field=None,
        description="Unidad político-administrativa principal. "
                    "Chile tiene 16 regiones. Define límites de "
                    "gobernaciones regionales.",
        typical_size="100k–8M hab",
        redistricting_role="Jurisdicción del plan de redistritaje",
    ),
    CensusUnit(
        level=2, country="CHL", name="Provincia",
        code_field="COD_PROVINCIA",  # primeros 3 dígitos del CUT
        shapefile="Comunal.shp",
        population_field=None,
        description="Subdivisión de la región. 56 provincias en Chile. "
                    "Administrada por un gobernador provincial.",
        typical_size="20k–2M hab",
        redistricting_role="Unidad de preservación administrativa",
    ),
    CensusUnit(
        level=3, country="CHL", name="Comuna",
        code_field="CUT",
        shapefile="Comunal.shp",
        population_field=None,
        description="Unidad municipal. 346 comunas. Administrada por "
                    "un alcalde electo. Unidad mínima indivisible en "
                    "el sistema electoral chileno (Ley 18.700).",
        typical_size="1k–500k hab",
        redistricting_role="Restricción dura: los distritos no pueden "
                           "partir comunas",
    ),
    CensusUnit(
        level=4, country="CHL", name="Distrito APC",
        code_field="ID_DIST",   # CUT_5 + '_' + COD_DISTRITO_3
        shapefile="Distrital.shp",
        population_field="VIVIENDA",   # proxy de población en APC 2023
        description="División del territorio comunal para organizar el "
                    "trabajo censal. ~2.768 distritos. Puede ser urbano, "
                    "rural o mixto. ANÁLOGO FUNCIONAL del Census Tract.",
        typical_size="200–5k viviendas",
        redistricting_role="Unidad básica de construcción de distritos. "
                           "Nivel recomendado para redistritaje en Chile.",
    ),
    CensusUnit(
        level=5, country="CHL", name="Zona Censal",
        code_field="COD_ZONA",
        shapefile="Manzana_Urbana.shp",  # se infiere del campo COD_ZONA
        population_field="VIVIENDA",
        description="Subdivisión del distrito. Agrupación de manzanas "
                    "contiguas. ANÁLOGO FUNCIONAL del Block Group.",
        typical_size="50–500 viviendas",
        redistricting_role="Unidad de análisis demográfico fino",
    ),
    CensusUnit(
        level=6, country="CHL", name="Manzana",
        code_field="MANZENT",
        shapefile="Manzana_Urbana.shp",  # también Manzana_Aldea.shp
        population_field="VIVIENDA",
        description="Polígono delimitado por calles o límites naturales. "
                    "Unidad de enumeración de viviendas en el APC 2023. "
                    "ANÁLOGO FUNCIONAL del Census Block.",
        typical_size="0–200 viviendas",
        redistricting_role="Unidad atómica. Solo usable en análisis "
                           "intraurbano por ciudad.",
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# Tabla de equivalencia
# ──────────────────────────────────────────────────────────────────────────────

def _analogy_strength(level: int) -> str:
    strengths = {
        1: "Fuerte — equivalencia político-administrativa directa",
        2: "Fuerte — equivalencia político-administrativa directa",
        3: "Fuerte — equivalencia municipal directa",
        4: "Fuerte — unidad estadística estable, diseño análogo",
        5: "Moderada — zona no siempre está materializada en shapefile propio",
        6: "Fuerte — unidad de enumeración atómica en ambos sistemas",
    }
    return strengths.get(level, "Desconocida")


EQUIVALENCE_TABLE = pd.DataFrame([
    {
        "nivel":               u.level,
        "usa_unit":            u_usa.name,
        "usa_code_field":      u_usa.code_field,
        "usa_shapefile":       u_usa.shapefile,
        "usa_typical_size":    u_usa.typical_size,
        "chl_unit":            u.name,
        "chl_code_field":      u.code_field,
        "chl_shapefile":       u.shapefile,
        "chl_typical_size":    u.typical_size,
        "redistricting_role":  u.redistricting_role,
        "analogy_strength":    _analogy_strength(u.level),
    }
    for u_usa, u in zip(USA_UNITS, CHILE_UNITS)
])


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────

def get_equivalence_table(style: str = "full") -> pd.DataFrame:
    """
    Retorna la tabla de equivalencia USA-Chile.

    Parameters
    ----------
    style : str
        "full"    → todas las columnas
        "compact" → solo nivel, unidades y rol
        "redist"  → solo columnas relevantes para redistritaje

    Returns
    -------
    pd.DataFrame
    """
    if style == "compact":
        return EQUIVALENCE_TABLE[[
            "nivel", "usa_unit", "chl_unit",
            "usa_typical_size", "chl_typical_size"
        ]]
    if style == "redist":
        return EQUIVALENCE_TABLE[[
            "nivel", "usa_unit", "chl_unit",
            "chl_code_field", "chl_shapefile",
            "redistricting_role", "analogy_strength"
        ]]
    return EQUIVALENCE_TABLE.copy()


def get_unit(country: str, level: int) -> CensusUnit:
    """
    Retorna el descriptor de una unidad censal.

    Parameters
    ----------
    country : str  "USA" o "CHL"
    level   : int  1–6

    Returns
    -------
    CensusUnit
    """
    units = USA_UNITS if country.upper() == "USA" else CHILE_UNITS
    for u in units:
        if u.level == level:
            return u
    raise ValueError(f"No existe unidad nivel {level} para {country}")


def get_analog(country: str, level: int) -> CensusUnit:
    """
    Dado un nivel en un país, retorna la unidad análoga en el otro.

    Examples
    --------
    >>> get_analog("USA", 4)   # Census Tract → Distrito APC
    >>> get_analog("CHL", 6)   # Manzana → Census Block
    """
    other = "CHL" if country.upper() == "USA" else "USA"
    return get_unit(other, level)


def describe_hierarchy(country: str = "CHL") -> None:
    """Imprime la jerarquía de unidades de un país."""
    units = CHILE_UNITS if country.upper() == "CHL" else USA_UNITS
    print(f"\n{'─'*60}")
    print(f"  Jerarquía censal — {country.upper()}")
    print(f"{'─'*60}")
    for u in units:
        print(f"  Nivel {u.level}  {u.name:<22} [{u.code_field}]")
        print(f"         {u.typical_size}")
        print(f"         {u.description[:70]}{'...' if len(u.description)>70 else ''}")
        print()


def print_equivalence(style: str = "compact") -> None:
    """Imprime la tabla de equivalencia formateada."""
    df = get_equivalence_table(style)
    print(f"\n{'─'*70}")
    print(f"  Tabla de equivalencia censal USA ↔ Chile")
    print(f"{'─'*70}")
    print(df.to_string(index=False))
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Mapeo de columnas APC → nombres canónicos
# ──────────────────────────────────────────────────────────────────────────────

# Columnas truncadas por el formato DBF (10 chars) y sus nombres completos
DBF_COLUMN_MAP = {
    "N_PROVINCI": "N_PROVINCIA",
    "COD_DISTRI": "COD_DISTRITO",
    "TIPO_DISTR": "TIPO_DISTRITO",
    "VIV_COLECT": "VIV_COLECTIVA",
    "COD_LOCAL":  "COD_LOCALIDAD",
    "COD_ENTIDA": "COD_ENTIDAD",
    "COD_MANZAN": "COD_MANZANA_ALDEA",
    "USO_EDIFIC": "USO_EDIFICACION",
}

# Campos de población por capa
POPULATION_FIELDS = {
    "Manzana_Urbana": {
        "viviendas":   "VIVIENDA",
        "colectivas":  "VIV_COLECTIVA",
        "otros_usos":  "OTRO_USO",
        "id":          "MANZENT",
    },
    "Manzana_Aldea": {
        "viviendas":   "VIVIENDA",
        "colectivas":  "VIV_COLECTIVAS",
        "otros_usos":  "O_USO",
        "id":          "MANZENT",
    },
    "Distrital": {
        "viviendas":   None,   # no tiene conteo directo, se agrega desde manzanas
        "id":          "ID_DIST",
    },
    "Comunal": {
        "viviendas":   None,
        "id":          "CUT",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Constantes CRS (importables desde cualquier módulo)
# ──────────────────────────────────────────────────────────────────────────────

CRS_METRIC = "EPSG:32719"   # UTM zona 19S — cubre todo Chile continental
CRS_GEO    = "EPSG:4326"    # WGS84 geográfico


def get_optimal_crs(gdf) -> str:
    """
    Devuelve el CRS métrico (UTM) óptimo para un GeoDataFrame chileno.

    Determina la zona UTM desde el centroide longitudinal de los datos.
    Para Chile continental (incluye todas las regiones 1-16) devuelve
    EPSG:32719 (UTM 19S). Para Isla de Pascua (lon ≈ -109°) devuelve
    EPSG:32712 (UTM 12S).

    Parameters
    ----------
    gdf : GeoDataFrame
        Puede estar en cualquier CRS; se convierte internamente a EPSG:4326
        solo para leer las coordenadas del bounding box.

    Returns
    -------
    str  Cadena de CRS, ej. "EPSG:32719".

    Examples
    --------
    >>> crs = get_optimal_crs(gdf_magallanes)
    'EPSG:32719'
    >>> crs = get_optimal_crs(gdf_easter_island)
    'EPSG:32712'
    """
    import geopandas as gpd

    if gdf.crs is None:
        # Sin CRS asumimos geográfico; usamos bounds directamente
        bounds = gdf.total_bounds          # (minx, miny, maxx, maxy)
    elif gdf.crs.is_geographic:
        bounds = gdf.total_bounds
    else:
        bounds = gdf.to_crs(CRS_GEO).total_bounds

    center_lon = (bounds[0] + bounds[2]) / 2.0

    # UTM zone = floor((lon + 180) / 6) + 1  (hemisferio sur: 326xx)
    utm_zone = int((center_lon + 180.0) / 6.0) + 1
    return f"EPSG:{32700 + utm_zone}"