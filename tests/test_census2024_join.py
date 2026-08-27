"""
tests/test_census2024_join.py
===============================
Regression test for the misleading diagnostic in
chiledist/data/census2024.py::_proportional_join() (used by
join_census_to_apc() / join_census_multilevel()).

Bug (fixed): the printed "fuente"/"diff" summed `target_col` over the
ENTIRE `source_df` passed in — for --pop-source censo2024 that's the full
national census table (346 comunas), regardless of how many comunas
`gdf_apc` actually covers. Running redistritaje.py for a single region
(e.g. R13, 52 comunas ≈ 40% of Chile's population) made the diagnostic
report something like "diff=-11,079,692", implying ~60% of the population
was silently lost in the proportional join — when in fact the join itself
was already correct: every distributed distrito sums back to its own
comuna's real census figure (confirmed manually against
datos/poblacion_comunal_censo2024.csv: R13's 52 comunas sum to 7,400,741;
the join produced 7,400,740 — off by 1 from rounding, not 11 million).

The fix restricts the diagnostic's "fuente" total to the comunas actually
present in `gdf_apc[cut_col]` before summing, so the printed diff reflects
the real (rounding-only) loss regardless of whether `gdf_apc` covers one
region or the whole country. This test builds a synthetic national
`source_df` spanning two "regions" and a `gdf_apc` covering only one of
them, and asserts the printed diff reflects only the covered comunas.
"""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from chiledist.domain.data import census2024 as c24


def _make_gdf_apc_single_region() -> gpd.GeoDataFrame:
    """3 distritos APC, all within region 13 (comunas 13101, 13102)."""
    return gpd.GeoDataFrame(
        {
            "ID_DIST":   ["13101_001", "13101_002", "13102_001"],
            "CUT":       [13101, 13101, 13102],
            "viviendas": [100, 100, 50],
            "geometry":  [box(i, 0, i + 1, 1) for i in range(3)],
        },
        crs="EPSG:4326",
    )


def _make_national_census_df() -> pd.DataFrame:
    """
    National census table spanning two regions:
        region 1:  CUT 1101 -> 5000 personas, CUT 1107 -> 3000 personas
        region 13: CUT 13101 -> 1000 personas, CUT 13102 -> 2000 personas
    Total nacional = 11000; total de las comunas de la región 13 = 3000.
    """
    return pd.DataFrame({
        "CUT":      [1101, 1107, 13101, 13102],
        "personas": [5000, 3000, 1000, 2000],
    })


class TestProportionalJoinDiagnostic:

    def test_diff_reflects_only_covered_comunas_not_national_total(self, capsys):
        gdf_apc = _make_gdf_apc_single_region()
        census_df = _make_national_census_df()

        gdf_out = c24.join_census_to_apc(
            gdf_apc, census_df, target_col="personas", proxy_col="viviendas",
        )
        printed = capsys.readouterr().out

        # La suma real distribuida SÍ debe ser correcta (13101: 1000, 13102: 2000 -> 3000)
        assert int(gdf_out["personas"].sum()) == 3000

        # El mensaje debe reportar "fuente" = 3000 (solo las 2 comunas cubiertas
        # por gdf_apc), NO 11000 (el total nacional de census_df completo).
        assert "fuente comunas cubiertas=3,000" in printed
        assert "11,000" not in printed

        # El diff reportado debe ser ~0 (solo rounding), no un salto de
        # miles por comparar contra el total nacional.
        assert "diff=+0" in printed or "diff=-0" in printed or "diff=0" in printed
        assert "-8,000" not in printed  # 3000 - 11000, el bug que se corrigió

        # El resumen debe indicar cuántas comunas cubre gdf_apc.
        assert "(2 comunas)" in printed

    def test_diff_is_not_national_scale_even_with_larger_mismatch(self, capsys):
        """
        Same idea with a bigger, more realistic national/regional gap (a
        region worth much less than the national total) — the diff must
        stay proportional to the covered comunas, not blow up to the
        national scale.
        """
        gdf_apc = gpd.GeoDataFrame(
            {
                "ID_DIST":   ["13101_001"],
                "CUT":       [13101],
                "viviendas": [10],
                "geometry":  [box(0, 0, 1, 1)],
            },
            crs="EPSG:4326",
        )
        census_df = pd.DataFrame({
            "CUT":      [1101, 1107, 1401, 13101],
            "personas": [199587, 142086, 16878, 438856],
        })

        gdf_out = c24.join_census_to_apc(
            gdf_apc, census_df, target_col="personas", proxy_col="viviendas",
        )
        printed = capsys.readouterr().out

        assert int(gdf_out["personas"].sum()) == 438856
        assert "fuente comunas cubiertas=438,856" in printed
        # El total nacional (358551 + 438856 = 797407) nunca debe aparecer
        # como si fuera la base de comparación.
        assert "797,407" not in printed
        diff = int(gdf_out["personas"].sum()) - 438856
        assert abs(diff) <= 1  # solo rounding, jamás una brecha de cientos de miles

    def test_multiple_communes_covered_sums_correctly(self, capsys):
        """gdf_apc covering >1 comuna: the diagnostic's covered-comuna
        total must be the sum over exactly those comunas, and the actual
        join must redistribute each comuna's population to its own
        distritos only (no cross-comuna leakage)."""
        gdf_apc = _make_gdf_apc_single_region()
        census_df = _make_national_census_df()

        gdf_out = c24.join_census_to_apc(
            gdf_apc, census_df, target_col="personas", proxy_col="viviendas",
        )

        # 13101 (1000 personas) is split 100/100 viviendas -> 500/500.
        d13101 = gdf_out[gdf_out["CUT"] == 13101]["personas"]
        assert sorted(d13101.tolist()) == [500, 500]

        # 13102 (2000 personas) has a single distrito -> gets it all.
        d13102 = gdf_out[gdf_out["CUT"] == 13102]["personas"]
        assert d13102.tolist() == [2000]

        printed = capsys.readouterr().out
        assert "(2 comunas)" in printed
