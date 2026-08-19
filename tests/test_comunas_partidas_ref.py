"""
tests/test_comunas_partidas_ref.py
====================================
Regression test for the comunas_partidas_ref=0 bug in
scripts/redistritaje.py::analizar_region().

Bug (fixed): the final resumen dict read n_split_ref from
df_ensemble["n_comunas_partidas"], a column only populated for a sparse
subsample of up to 50 plans (np.linspace over the ensemble). Whenever
ref_idx (chosen by heuristic score over the WHOLE ensemble) fell outside
that subsample, the lookup was NaN and the fallback silently returned 0 --
even though the actual reference plan (ref_plan_mapped) did split comunas,
as shown by the separately (and correctly) computed split_summary printed
to the log ("Comunas partidas en plan de referencia: N").

The fix makes n_split_ref = len(split_summary), reusing the exact
per-reference-plan computation instead of the sparse ensemble sample.

This test does not run the full gerrychain MCMC pipeline (no test in this
suite does -- analizar_region is always monkeypatched out elsewhere, see
test_redistritaje_n_distritos.py). Instead it:
  1. Reproduces the buggy lookup against a synthetic df_ensemble where
     ref_idx sits outside the sparse sample, and shows it yields NaN/0 --
     the wrong answer -- for a reference plan that actually splits comunas.
  2. Shows that cd.split_unit_summary (the function the fix reuses) gives
     the correct, exact count for that same reference plan.
  3. Structurally asserts that analizar_region's source now computes
     n_split_ref from split_summary and no longer contains the sparse
     df_ensemble["n_comunas_partidas"] lookup.
"""

import importlib.util
import inspect
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

import chiledist as cd


def _import_redistritaje():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(root, "scripts", "redistritaje.py")
    spec = importlib.util.spec_from_file_location(
        "redistritaje_comunas_partidas_ref", script_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def redistritaje():
    return _import_redistritaje()


def _make_gdf_dec():
    """8 APC units (ID_DIST) across 3 comunas (CUT), one of which (CUT=2)
    will be split across two districts in ref_plan_mapped below."""
    return gpd.GeoDataFrame(
        {
            "ID_DIST": [f"u{i}" for i in range(8)],
            "CUT":     [1, 1, 2, 2, 2, 2, 3, 3],
            "viviendas": [100, 100, 100, 100, 100, 100, 100, 100],
            "geometry": [box(i, 0, i + 1, 1) for i in range(8)],
        },
        crs="EPSG:4326",
    )


def _make_ref_plan_mapped():
    """CUT=2's four units are split 3-vs-1 across districts 0 and 1 --
    CUT=1 and CUT=3 stay whole. Exactly 1 comuna partida (CUT=2)."""
    return {
        "u0": 0, "u1": 0,          # CUT 1 -> distrito 0 (entero)
        "u2": 0, "u3": 0, "u4": 0, # CUT 2 -> mayormente distrito 0...
        "u5": 1,                  # ...pero u5 va a distrito 1 (partida)
        "u6": 1, "u7": 1,          # CUT 3 -> distrito 1 (entero)
    }


class TestSparseEnsembleLookupWasWrong:
    """Reproduces the buggy read path against a synthetic ensemble where
    ref_idx (the score-selected reference) falls outside the ~50-plan
    sparse sample -- the exact condition that produced comunas_partidas_ref=0
    for apc_free/apc_soft."""

    def test_ref_idx_outside_sparse_sample_yields_nan(self):
        n_planes = 200
        split_sample_size = min(50, n_planes)
        split_indices = np.linspace(0, n_planes - 1, split_sample_size, dtype=int)

        df_ensemble = pd.DataFrame({"plan_id": range(n_planes)})
        df_ensemble["n_comunas_partidas"] = np.nan
        for si in split_indices:
            df_ensemble.loc[si, "n_comunas_partidas"] = 0  # arbitrary sampled values

        # Pick a ref_idx deliberately NOT in the sparse sample.
        ref_idx = next(i for i in range(n_planes) if i not in set(split_indices))

        assert pd.isna(df_ensemble.loc[ref_idx, "n_comunas_partidas"])

        # This is exactly the old buggy computation -- confirms it silently
        # falls back to 0 regardless of how many comunas the reference plan
        # actually splits.
        n_split_ref_buggy = (
            int(df_ensemble.loc[ref_idx, "n_comunas_partidas"])
            if not pd.isna(df_ensemble.loc[ref_idx, "n_comunas_partidas"])
            else 0
        )
        assert n_split_ref_buggy == 0

    def test_split_unit_summary_gives_correct_count_for_that_same_plan(self):
        """The reference plan used above DOES split one comuna (CUT=2) --
        cd.split_unit_summary, which the fix now relies on, reports it
        correctly and exactly, independent of any ensemble subsample."""
        gdf_dec = _make_gdf_dec()
        ref_plan_mapped = _make_ref_plan_mapped()

        split_summary = cd.split_unit_summary(
            ref_plan_mapped, gdf_dec,
            unit_col="CUT", id_col="ID_DIST", pop_col="viviendas",
        )

        assert len(split_summary) == 1
        assert split_summary.iloc[0]["CUT"] == 2
        assert split_summary.iloc[0]["n_fragmentos"] == 2


class TestAnalizarRegionSourceComputesFromSplitSummary:
    """Structural regression guard: the fixed n_split_ref computation must
    come from split_summary (exact, per-reference-plan), never from the
    sparse df_ensemble["n_comunas_partidas"] lookup."""

    def test_n_split_ref_assigned_from_len_split_summary(self, redistritaje):
        source = inspect.getsource(redistritaje.analizar_region)
        assert "n_split_ref = len(split_summary)" in source

    def test_no_sparse_ensemble_lookup_remains(self, redistritaje):
        source = inspect.getsource(redistritaje.analizar_region)
        assert 'df_ensemble.loc[ref_idx, "n_comunas_partidas"]' not in source

    def test_n_split_ref_initialized_before_conditional_block(self, redistritaje):
        """n_split_ref must default to 0 before the id_col == 'ID_DIST'
        check, so non-APC scenarios (e.g. legal) still get a defined value."""
        source = inspect.getsource(redistritaje.analizar_region)
        init_pos = source.index("n_split_ref = 0")
        block_pos = source.index(
            'if id_col == "ID_DIST" and "CUT" in gdf_dec.columns:\n        split_summary'
        )
        assert init_pos < block_pos

    def test_return_dict_still_uses_n_split_ref_unchanged(self, redistritaje):
        source = inspect.getsource(redistritaje.analizar_region)
        assert '"comunas_partidas_ref": n_split_ref,' in source
