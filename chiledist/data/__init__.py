"""
chiledist.data
==============
Subpaquete para carga de fuentes de población externas al APC 2023.

Módulos disponibles
-------------------
    census2024  — INE Censo 2024: personas y hogares por distrito/comuna
    servel      — SERVEL: padrón electoral e inscritos por comuna

Flujo típico — Censo 2024 (join exacto por distrito, recomendado)
-----------------------------------------------------------------
    import chiledist.data.census2024 as c24

    mz  = c24.load_manzana_censo2024("Base_manzana_entidad_CPV24.csv")
    gdf = c24.join_manzana_to_apc(gdf, mz)
    # → agrega columnas "personas" y "hogares" exactas por distrito APC

Flujo alternativo — distribución proporcional por comuna
--------------------------------------------------------
    census = c24.load_census2024("datos/censo2024_comunas.csv")
    gdf    = c24.join_census_to_apc(gdf, census, proxy_col="viviendas")
    # → agrega columna "personas"

Flujo típico — padrón SERVEL
-----------------------------
    import chiledist.data.servel as sv

    padron = sv.load_padron_electoral("datos/padron_2024.csv")
    gdf    = sv.join_padron_to_apc(gdf, padron, proxy_col="viviendas")
    # → agrega columna "inscritos"

    # Usar pop_col alternativo en ScenarioConfig
    import dataclasses, chiledist as cd
    sc = dataclasses.replace(cd.SCENARIO_LEGAL, pop_col="personas")

REGIONES_APC
------------
Diccionario {region_code: {"nombre", "nombre_carpeta"}} con las 16 regiones
de Chile. `nombre_carpeta` sigue el patrón de subcarpeta usado en
datos/<REGION>/... por scripts/redistritaje.py y scripts/compare_scenarios.py.

    from chiledist.data import REGIONES_APC
    REGIONES_APC[13]  # {"nombre": "Región Metropolitana",
                       #  "nombre_carpeta": "R13_METROPOLITANA"}
"""

from . import census2024, servel

REGIONES_APC = {
    1:  {"nombre": "Región de Tarapacá",                                  "nombre_carpeta": "R01_TARAPACA"},
    2:  {"nombre": "Región de Antofagasta",                               "nombre_carpeta": "R02_ANTOFAGASTA"},
    3:  {"nombre": "Región de Atacama",                                   "nombre_carpeta": "R03_ATACAMA"},
    4:  {"nombre": "Región de Coquimbo",                                  "nombre_carpeta": "R04_COQUIMBO"},
    5:  {"nombre": "Región de Valparaíso",                                "nombre_carpeta": "R05_VALPARAISO"},
    6:  {"nombre": "Región del Libertador General Bernardo O'Higgins",    "nombre_carpeta": "R06_OHIGGINS"},
    7:  {"nombre": "Región del Maule",                                   "nombre_carpeta": "R07_MAULE"},
    8:  {"nombre": "Región del Biobío",                                  "nombre_carpeta": "R08_BIOBIO"},
    9:  {"nombre": "Región de la Araucanía",                             "nombre_carpeta": "R09_ARAUCANIA"},
    10: {"nombre": "Región de Los Lagos",                                "nombre_carpeta": "R10_LOS_LAGOS"},
    11: {"nombre": "Región de Aysén del General Carlos Ibáñez del Campo", "nombre_carpeta": "R11_AYSEN"},
    12: {"nombre": "Región de Magallanes y de la Antártica Chilena",      "nombre_carpeta": "R12_MAGALLANES"},
    13: {"nombre": "Región Metropolitana",                                "nombre_carpeta": "R13_METROPOLITANA"},
    14: {"nombre": "Región de Los Ríos",                                  "nombre_carpeta": "R14_LOS_RIOS"},
    15: {"nombre": "Región de Arica y Parinacota",                        "nombre_carpeta": "R15_ARICA"},
    16: {"nombre": "Región de Ñuble",                                     "nombre_carpeta": "R16_NUBLE"},
}

__all__ = ["census2024", "servel", "REGIONES_APC"]
