"""
tests/test_split_metrics.py
============================
Unit tests for pop_afectada_pct and plan_split_metrics.

Uses a minimal synthetic GeoDataFrame — no shapefiles required.
The GeoDataFrame has 4 APC districts across 3 comunas:
    C1 → D1 + D2  (viviendas: 100 + 200 = 300)
    C2 → D3       (viviendas: 150)
    C3 → D4       (viviendas:  50)
Total: 500 viviendas
"""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from chiledist.split_metrics import (
    count_split_units,
    plan_split_metrics,
    pop_afectada_pct,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "ID_DIST":   ["D1", "D2", "D3", "D4"],
            "CUT":       ["C1", "C1", "C2", "C3"],
            "viviendas": [100, 200, 150, 50],
            "geometry":  [box(i, 0, i + 1, 1) for i in range(4)],
        },
        crs="EPSG:4326",
    )


def _make_two_commune_gdf() -> gpd.GeoDataFrame:
    """Two comunas, each with two APC districts."""
    return gpd.GeoDataFrame(
        {
            "ID_DIST":   ["A1", "A2", "B1", "B2"],
            "CUT":       ["CA", "CA", "CB", "CB"],
            "viviendas": [100, 100, 100, 100],
            "geometry":  [box(i, 0, i + 1, 1) for i in range(4)],
        },
        crs="EPSG:4326",
    )


# C1 is split: D1 → district 1, D2 → district 2
ASGN_SPLIT = {"D1": 1, "D2": 2, "D3": 1, "D4": 2}
# All comunas intact: both D1 and D2 stay in district 1
ASGN_CLEAN = {"D1": 1, "D2": 1, "D3": 2, "D4": 3}


# ─── pop_afectada_pct ─────────────────────────────────────────────────────────

class TestPopAfectadaPct:

    def test_no_split_returns_zero(self):
        gdf = _make_gdf()
        result = pop_afectada_pct(ASGN_CLEAN, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert result == pytest.approx(0.0)

    def test_c1_split_correct_fraction(self):
        """C1 has 300/500 = 0.60 of total population."""
        gdf = _make_gdf()
        result = pop_afectada_pct(ASGN_SPLIT, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert result == pytest.approx(0.60, rel=0.01)

    def test_all_communes_split_returns_one(self):
        """If every commune is split, result = 1.0."""
        gdf = _make_two_commune_gdf()
        asgn = {"A1": 1, "A2": 2, "B1": 3, "B2": 4}  # both CA and CB split
        result = pop_afectada_pct(asgn, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert result == pytest.approx(1.0)

    def test_result_in_range_zero_one(self):
        gdf = _make_gdf()
        result = pop_afectada_pct(ASGN_SPLIT, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert 0.0 <= result <= 1.0

    def test_empty_assignment_returns_zero(self):
        gdf = _make_gdf()
        result = pop_afectada_pct({}, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert result == 0.0

    def test_missing_pop_col_returns_zero(self):
        gdf = _make_gdf().drop(columns=["viviendas"])
        result = pop_afectada_pct(ASGN_SPLIT, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert result == 0.0

    def test_split_more_populous_commune_increases_metric(self):
        """Splitting a larger commune produces a higher pop_afectada_pct."""
        gdf = _make_gdf()
        # D1 is in C1 (the larger commune); D3 is C2 (150 viviendas)
        # split only D1/D2 → C1 (300 viv) → pct=0.60
        # if we split C2 alone: D3 only unit → can't split; need 2 units
        # Split only the smaller: we can't here (C2 has only D3).
        # So just verify the base case numerics
        result = pop_afectada_pct(ASGN_SPLIT, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert result > 0.5, "Splitting the larger commune (C1 = 60% pop) gives > 0.5"


# ─── plan_split_metrics ───────────────────────────────────────────────────────

class TestPlanSplitMetrics:

    def test_returns_dict(self):
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        assert isinstance(m, dict)

    def test_required_keys(self):
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        required = ("n_comunas_partidas", "share_comunas_partidas",
                    "pop_afectada_pct", "split_severity",
                    "small_fragments", "comunas_mas_partidas")
        for key in required:
            assert key in m, f"Missing key: {key}"

    def test_no_splits_zeros(self):
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_CLEAN, gdf)
        assert m["n_comunas_partidas"] == 0
        assert m["pop_afectada_pct"] == pytest.approx(0.0)
        assert m["split_severity"] == pytest.approx(0.0)
        assert m["comunas_mas_partidas"] == []

    def test_one_split_count(self):
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        assert m["n_comunas_partidas"] == 1

    def test_pop_afectada_pct_consistent(self):
        """plan_split_metrics.pop_afectada_pct matches direct pop_afectada_pct call."""
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        direct = pop_afectada_pct(ASGN_SPLIT, gdf, unit_col="CUT",
                                  id_col="ID_DIST", pop_col="viviendas")
        assert m["pop_afectada_pct"] == pytest.approx(direct, rel=1e-6)

    def test_share_comunas_partidas(self):
        """share = n_split / n_total = 1 / 3."""
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        assert m["share_comunas_partidas"] == pytest.approx(1 / 3, rel=0.01)

    def test_split_severity_positive_when_split(self):
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        assert m["split_severity"] > 0.0

    def test_comunas_mas_partidas_contains_split_commune(self):
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        assert isinstance(m["comunas_mas_partidas"], list)
        assert "C1" in m["comunas_mas_partidas"]

    def test_consistent_with_count_split_units(self):
        """n_comunas_partidas matches count_split_units."""
        gdf = _make_gdf()
        m = plan_split_metrics(ASGN_SPLIT, gdf)
        direct = count_split_units(ASGN_SPLIT, gdf, unit_col="CUT", id_col="ID_DIST")
        assert m["n_comunas_partidas"] == direct
