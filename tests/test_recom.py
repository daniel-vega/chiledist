"""
tests/test_recom.py
=====================
Regression tests for chiledist.engines.samplers.recom::run_recom() —
Etapa 3, BUGs 2 y 3: la función no era invocable (varios AttributeError
por API de gerrychain 0.3.2 no coincidente) y su parámetro random_seed
no controlaba la reproducibilidad real de la cadena (sembraba numpy;
gerrychain usa random.random() del stdlib).

run_recom_chain() (la función de bajo nivel que scripts/redistritaje.py
ejecuta en producción) nunca tuvo estos problemas — solo run_recom(), la
envoltura de conveniencia de alto nivel, no probada hasta ahora por
ningún test.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from chiledist.domain.equivalence import CRS_METRIC
from chiledist.engines.samplers.recom import run_recom


def _grid_gdf() -> gpd.GeoDataFrame:
    """Misma rejilla 3x3 sintética que tests/test_graph_contraction.py."""
    rows = []
    for r in range(3):
        for c in range(3):
            geom = Polygon([(c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1)])
            rows.append({
                "ID_DIST": f"D{r}{c}",
                "CUT": f"C{r}",
                "viviendas": 100,
                "geometry": geom,
            })
    return gpd.GeoDataFrame(rows, crs=CRS_METRIC)


class TestRunRecom:

    def test_instanciable_sin_error(self, tmp_path):
        gpd_module = pytest.importorskip("gerrychain")
        gdf = _grid_gdf()

        planes = run_recom(
            gdf, id_col="ID_DIST", pop_col="viviendas",
            n_districts=3, n_steps=3, pop_tolerance=0.5,
            random_seed=7, save_every=1,
            output_prefix=str(tmp_path / "plan"),
        )

        assert len(planes) == 3
        assert all(len(p) == 9 for p in planes)  # 9 unidades en la rejilla

    def test_misma_semilla_mismo_assignment(self, tmp_path):
        pytest.importorskip("gerrychain")
        gdf = _grid_gdf()

        planes1 = run_recom(
            gdf, id_col="ID_DIST", pop_col="viviendas",
            n_districts=3, n_steps=5, pop_tolerance=0.5,
            random_seed=99, save_every=1,
            output_prefix=str(tmp_path / "a"),
        )
        planes2 = run_recom(
            gdf, id_col="ID_DIST", pop_col="viviendas",
            n_districts=3, n_steps=5, pop_tolerance=0.5,
            random_seed=99, save_every=1,
            output_prefix=str(tmp_path / "b"),
        )

        assert planes1 == planes2, (
            "random_seed debe controlar la reproducibilidad real de la "
            "cadena (BUG 3): misma semilla -> misma secuencia de planes."
        )
