"""
chiledist/map.py
================
ChileDistMap: contenedor ligero del estado de datos cargados para un
análisis de redistritaje.

Resuelve el problema de que el usuario tenga que pasar el mismo GeoDataFrame,
pop_col efectivo y CRS a cada función por separado.  No contiene lógica de
algoritmos — solo agrupa los resultados de carga y preprocesamiento.

Uso
---
    map_data = ChileDistMap.from_apc(
        base_dir="./SHP_APC2023",
        region_code=13,
        scenario=cd.SCENARIO_LEGAL,
    )

    # Los campos ya están resueltos
    G, adj, ids = cd.build_graph(map_data.gdf_dec, id_col=map_data.id_col)
    planes = cd.run_recom(map_data.gdf_dec, id_col=map_data.id_col,
                          pop_col=map_data.pop_col, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChileDistMap:
    """
    Contenedor de estado de datos cargados para una corrida de redistritaje.

    Attributes
    ----------
    gdf_obs : gpd.GeoDataFrame
        Capa de observación original (APC/distrital).
    gdf_dec : gpd.GeoDataFrame
        Capa de decisión (contratada a CUT si decision_unit='CUT',
        igual a gdf_obs si decision_unit='ID_DIST').
    scenario : ScenarioConfig
        Configuración del escenario.
    id_col : str
        Columna identificadora efectiva ('ID_DIST' o 'CUT').
    pop_col : str
        Columna de población efectiva (resuelta post-enriquecimiento).
    crs_metric : str
        CRS métrico resuelto (ej. 'EPSG:32719').
    region_code : int
        Código de región.
    region_name : str
        Nombre legible de la región.
    """

    gdf_obs:     object                   # gpd.GeoDataFrame
    gdf_dec:     object                   # gpd.GeoDataFrame (contratada)
    scenario:    object                   # ScenarioConfig
    id_col:      str
    pop_col:     str
    crs_metric:  str
    region_code: int
    region_name: str = ""
    _extra:      dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_apc(
        cls,
        base_dir: str,
        region_code: int,
        scenario,
        pop_source: str = "viviendas",
        census_path: Optional[str] = None,
        padron_path: Optional[str] = None,
    ) -> "ChileDistMap":
        """
        Factory: carga datos APC, enriquece población y contrae si corresponde.

        Parameters
        ----------
        base_dir : str
            Directorio raíz con SHP_APC2023_R*.
        region_code : int
            Código de región (1-16).
        scenario : ScenarioConfig
            Escenario que define decision_unit, pop_col y crs_metric.
        pop_source : str
            'viviendas' | 'manzana' | 'censo2024' | 'padron'.
        census_path : str, opcional
            Ruta al CSV del Censo 2024 (para pop_source manzana/censo2024).
        padron_path : str, opcional
            Ruta al CSV del padrón SERVEL (para pop_source padron).

        Returns
        -------
        ChileDistMap con gdf_obs, gdf_dec, id_col, pop_col y crs_metric resueltos.
        """
        from .loader import load_layer, aggregate_population
        from .hierarchy import contract_to_decision_units
        from .equivalence import get_optimal_crs

        _REGION_NOMBRES = {
            1:  "R01_TARAPACA",    2:  "R02_ANTOFAGASTA",
            3:  "R03_ATACAMA",     4:  "R04_COQUIMBO",
            5:  "R05_VALPARAISO",  6:  "R06_OHIGGINS",
            7:  "R07_MAULE",       8:  "R08_BIOBIO",
            9:  "R09_ARAUCANIA",  10:  "R10_LOS_LAGOS",
            11: "R11_AYSEN",      12:  "R12_MAGALLANES",
            13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS",
            15: "R15_ARICA",      16:  "R16_NUBLE",
        }

        region_name = _REGION_NOMBRES.get(region_code, f"R{region_code:02d}")

        # Cargar capa distrital APC
        gdf_obs = load_layer("distrital", base_dir=base_dir,
                             regions=[region_code])

        # Agregar viviendas desde manzanas
        try:
            mz_urb = load_layer("manzana_urbana", base_dir=base_dir,
                                regions=[region_code])
            mz_ald = load_layer("manzana_aldea", base_dir=base_dir,
                                regions=[region_code])
            import pandas as pd
            pop_urb = aggregate_population(mz_urb, level="distrito",
                                           source="urbana")
            pop_ald = aggregate_population(mz_ald, level="distrito",
                                           source="aldea")
            pop = (pop_urb
                   .merge(pop_ald, on=["CUT", "COD_DISTRITO"],
                          how="outer", suffixes=("_urb", "_ald"))
                   .fillna(0))
            pop["viviendas"] = (pop.get("viviendas_urb", 0)
                                + pop.get("viviendas_ald", 0))
            gdf_obs = gdf_obs.merge(
                pop[["CUT", "COD_DISTRITO", "viviendas"]],
                on=["CUT", "COD_DISTRITO"], how="left"
            ).fillna({"viviendas": 0})
            gdf_obs["viviendas"] = gdf_obs["viviendas"].astype(int)
        except Exception:
            if "viviendas" not in gdf_obs.columns:
                gdf_obs["viviendas"] = 0

        # Enriquecer con fuente de población alternativa
        pop_col = "viviendas"
        if pop_source != "viviendas":
            try:
                from .data import census2024 as c24, servel as sv
                if pop_source == "manzana" and census_path:
                    mz   = c24.load_manzana_censo2024(census_path)
                    gdf_obs = c24.join_manzana_to_apc(gdf_obs, mz)
                    pop_col  = "personas"
                elif pop_source == "censo2024" and census_path:
                    census  = c24.load_census2024(census_path)
                    gdf_obs = c24.join_census_multilevel(gdf_obs, census,
                                                         proxy_col="viviendas")
                    pop_col  = "personas"
                elif pop_source == "padron" and padron_path:
                    padron  = sv.load_padron_electoral(padron_path)
                    gdf_obs = sv.join_padron_to_apc(gdf_obs, padron,
                                                    proxy_col="viviendas")
                    pop_col  = "inscritos"
            except Exception:
                pass

        # Respetar pop_col del escenario si ya está definido
        if (scenario.pop_col != "viviendas"
                and scenario.pop_col in gdf_obs.columns):
            pop_col = scenario.pop_col

        # Contraer a unidad de decisión
        decision_unit = scenario.decision_unit
        if decision_unit == "CUT":
            gdf_dec = contract_to_decision_units(
                gdf_obs, decision_unit="CUT",
                agg_spec={pop_col: "sum"},
            )
            id_col = "CUT"
        else:
            gdf_dec = gdf_obs.copy()
            id_col  = "ID_DIST"

        # Resolver CRS métrico
        crs_metric = scenario.crs_metric or get_optimal_crs(gdf_dec)

        return cls(
            gdf_obs=gdf_obs,
            gdf_dec=gdf_dec,
            scenario=scenario,
            id_col=id_col,
            pop_col=pop_col,
            crs_metric=crs_metric,
            region_code=region_code,
            region_name=region_name,
        )

    def to_dict(self) -> dict:
        """Serializable para incluir en run_manifest."""
        return {
            "region_code":   self.region_code,
            "region_name":   self.region_name,
            "id_col":        self.id_col,
            "pop_col":       self.pop_col,
            "crs_metric":    self.crs_metric,
            "n_obs_units":   len(self.gdf_obs),
            "n_dec_units":   len(self.gdf_dec),
            "scenario_name": self.scenario.name if self.scenario else None,
        }

    def __repr__(self) -> str:
        return (
            f"ChileDistMap("
            f"region={self.region_name}, "
            f"id_col={self.id_col!r}, "
            f"pop_col={self.pop_col!r}, "
            f"n_units={len(self.gdf_dec)})"
        )
