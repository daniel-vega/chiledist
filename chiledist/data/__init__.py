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
"""

from . import census2024, servel

__all__ = ["census2024", "servel"]
