"""
tests/test_compare_scenarios_incomplete.py
============================================
Tests for making infeasible_population / sin_particion scenarios visible
in scenario comparison, excluded from scoring, and marking the overall
comparison as INCOMPLETE.

Where the scenario used to disappear
-------------------------------------
chiledist.scenario_comparison.compare.load_ensembles_from_disk() only ever
returns scenarios that have a real ensemble_stats.csv on disk. A scenario
whose analizar_region() call returned early (infeasible_population,
sin_particion, ...) never writes that file, so it was silently absent from
the `ensembles` dict — and scripts/compare_scenarios.py's main() didn't
even capture analizar_region()'s return value, so the status/reason were
lost the moment they were printed.

Where the scoring input is built
----------------------------------
scripts/compare_scenarios.py::compare_and_export() feeds `ensembles`
straight into cd.compare_ensembles() -> cd.rank_scenarios() — those two
functions are untouched by this change and only ever see whatever is in
`ensembles`, which already excludes anything without a real
ensemble_stats.csv. So scoring was (and remains) naturally scoped to valid
ensembles; the actual gap was pure *visibility*: nothing surfaced the
missing scenario's status, and nothing flagged the comparison as partial.

This change adds:
    - scripts/compare_scenarios.py: persists scenario_status.json for any
      analizar_region() result with status != "ok".
    - chiledist.scenario_comparison.compare: load_scenario_statuses_from_disk,
      build_scenario_overview, assess_comparison_completeness.
    - compare_and_export() returns {"ranking", "overview", "completeness"}
      instead of a bare DataFrame; `ranking` is untouched/identical to the
      old return value when every scenario has a valid ensemble.
"""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import chiledist as cd

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _import_compare_scenarios():
    spec = importlib.util.spec_from_file_location(
        "compare_scenarios_incomplete_test", str(SCRIPTS_DIR / "compare_scenarios.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_ensemble_df(seed: int, base_dev: float, base_pp: float,
                       base_cuts: float, base_splits: float, n: int = 20) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "plan_id":             np.arange(n),
        "max_dev_pob_pct":     base_dev + rng.normal(0, 0.3, n),
        "pp_promedio":         base_pp + rng.normal(0, 0.02, n),
        "cut_edges":           base_cuts + rng.integers(-2, 3, n),
        "n_comunas_partidas":  np.maximum(0, base_splits + rng.integers(-1, 2, n)),
    })


INFEASIBLE_RESULT = {
    "region": 13,
    "region_name": "R13_METROPOLITANA",
    "scenario": "legal_comunas",
    "status": "infeasible_population",
    "reason": "indivisible_unit_exceeds_population_bound",
    "total_population": 267629,
    "n_districts": 8,
    "ideal_population": 33453.625,
    "largest_indivisible_unit": 66697,
    "largest_indivisible_unit_id": "13101",
    "minimum_required_tolerance": 0.9937,
    "requested_tolerance": 0.05,
}

SIN_PARTICION_RESULT = {
    "region": 13,
    "region_name": "R13_METROPOLITANA",
    "scenario": "apc_free",
    "status": "sin_particion",
    "reason": "initialization_search_exhausted",
}


def _write_ensemble(output_base, region_name, scenario_name, df):
    sc_dir = Path(output_base) / region_name / "redistritaje" / scenario_name
    sc_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(sc_dir / "ensemble_stats.csv", index=False)


def _write_status(output_base, region_name, scenario_name, result):
    sc_dir = Path(output_base) / region_name / "redistritaje" / scenario_name
    sc_dir.mkdir(parents=True, exist_ok=True)
    with open(sc_dir / "scenario_status.json", "w", encoding="utf-8") as f:
        json.dump(result, f)


REGION_NAME = "R13_METROPOLITANA"
REGION_CODE = 13


# ─── Unit-level: assess_comparison_completeness ────────────────────────────

class TestAssessComparisonCompleteness:

    def test_all_valid_is_complete(self):
        names = ["legal_comunas", "apc_soft", "apc_free"]
        ensembles = {n: pd.DataFrame({"x": [1]}) for n in names}
        result = cd.assess_comparison_completeness(names, ensembles)
        assert result["comparison_status"]  == "COMPLETE"
        assert result["expected_scenarios"] == 3
        assert result["valid_ensembles"]    == 3
        assert result["missing_baseline"]   is None
        assert result["ranking_scope"]      == "full"

    def test_missing_baseline_is_incomplete(self):
        names = ["legal_comunas", "apc_soft", "apc_free"]
        ensembles = {"apc_soft": pd.DataFrame({"x": [1]}),
                     "apc_free": pd.DataFrame({"x": [1]})}
        result = cd.assess_comparison_completeness(names, ensembles, baseline="legal_comunas")
        assert result["comparison_status"]  == "INCOMPLETE"
        assert result["expected_scenarios"] == 3
        assert result["valid_ensembles"]    == 2
        assert result["missing_baseline"]   == "legal_comunas"
        assert result["ranking_scope"]      == "partial"

    def test_missing_non_baseline_is_incomplete_without_missing_baseline(self):
        """sin_particion on a non-baseline scenario: still INCOMPLETE, but
        missing_baseline is None since the baseline itself is fine."""
        names = ["legal_comunas", "apc_soft", "apc_free"]
        ensembles = {"legal_comunas": pd.DataFrame({"x": [1]}),
                     "apc_soft": pd.DataFrame({"x": [1]})}
        result = cd.assess_comparison_completeness(names, ensembles, baseline="legal_comunas")
        assert result["comparison_status"] == "INCOMPLETE"
        assert result["missing_baseline"]  is None
        assert result["ranking_scope"]     == "partial"


# ─── Unit-level: build_scenario_overview ───────────────────────────────────

class TestBuildScenarioOverview:

    def test_all_valid_all_included(self):
        names = ["legal_comunas", "apc_soft"]
        ensembles = {n: pd.DataFrame({"x": [1, 2, 3]}) for n in names}
        overview = cd.build_scenario_overview(names, ensembles)
        assert set(overview["status"]) == {"ok"}
        assert overview["included_in_scoring"].all()
        assert overview["reason"].isna().all()

    def test_infeasible_scenario_visible_but_excluded(self):
        names = ["legal_comunas", "apc_soft", "apc_free"]
        ensembles = {"apc_soft": pd.DataFrame({"x": [1]}),
                     "apc_free": pd.DataFrame({"x": [1]})}
        statuses = {"legal_comunas": INFEASIBLE_RESULT}
        overview = cd.build_scenario_overview(names, ensembles, statuses)

        row = overview[overview["escenario"] == "legal_comunas"].iloc[0]
        assert row["status"] == "infeasible_population"
        assert row["reason"] == "indivisible_unit_exceeds_population_bound"
        assert row["included_in_scoring"] == False
        # still present — never dropped from the overview
        assert "legal_comunas" in overview["escenario"].values

    def test_sin_particion_distinct_from_infeasible(self):
        names = ["legal_comunas", "apc_soft", "apc_free"]
        ensembles = {"legal_comunas": pd.DataFrame({"x": [1]}),
                     "apc_soft": pd.DataFrame({"x": [1]})}
        statuses = {"apc_free": SIN_PARTICION_RESULT}
        overview = cd.build_scenario_overview(names, ensembles, statuses)

        row = overview[overview["escenario"] == "apc_free"].iloc[0]
        assert row["status"] == "sin_particion"
        assert row["reason"] == "initialization_search_exhausted"
        assert row["status"] != "infeasible_population"
        assert row["included_in_scoring"] == False

    def test_no_artificial_score_or_nan_fill_columns(self):
        """Overview never carries score/rank columns for excluded scenarios
        — those only ever exist in the ranking table, which never contains
        the excluded scenario at all."""
        names = ["legal_comunas", "apc_soft"]
        ensembles = {"apc_soft": pd.DataFrame({"x": [1]})}
        statuses = {"legal_comunas": INFEASIBLE_RESULT}
        overview = cd.build_scenario_overview(names, ensembles, statuses)
        assert "composite_score" not in overview.columns
        assert "rank" not in overview.columns


# ─── Unit-level: load_scenario_statuses_from_disk ──────────────────────────

class TestLoadScenarioStatusesFromDisk:

    def test_reads_persisted_status(self, tmp_path):
        _write_status(tmp_path, REGION_NAME, "legal_comunas", INFEASIBLE_RESULT)
        statuses = cd.load_scenario_statuses_from_disk(
            str(tmp_path), REGION_CODE, ["legal_comunas", "apc_soft"]
        )
        assert statuses["legal_comunas"]["status"] == "infeasible_population"
        assert statuses["legal_comunas"]["reason"] == "indivisible_unit_exceeds_population_bound"
        assert "apc_soft" not in statuses

    def test_missing_file_simply_absent(self, tmp_path):
        statuses = cd.load_scenario_statuses_from_disk(
            str(tmp_path), REGION_CODE, ["legal_comunas"]
        )
        assert statuses == {}


# ─── Ranking invariance: presence of an infeasible scenario must not affect
#     the ranking of the valid ones ──────────────────────────────────────────

class TestRankingUnaffectedByInfeasibleScenario:

    def test_ranking_identical_with_or_without_infeasible_scenario_listed(self):
        """
        rank_scenarios only ever sees `ensembles` — scenario_names/overview/
        completeness are computed separately and never feed into scoring.
        Confirm the ranking is byte-identical whether or not a third,
        infeasible scenario is part of the *expected* scenario list.
        """
        ensembles = {
            "apc_soft": _make_ensemble_df(1, base_dev=3.0, base_pp=0.55, base_cuts=40, base_splits=2),
            "apc_free": _make_ensemble_df(2, base_dev=5.0, base_pp=0.60, base_cuts=35, base_splits=4),
        }

        df_a = cd.rank_scenarios(cd.compare_ensembles(dict(ensembles)))

        # Simulate the "3 expected, 1 infeasible" bookkeeping happening
        # alongside — it must not leak into the scoring input.
        _names = ["legal_comunas", "apc_soft", "apc_free"]
        _ = cd.assess_comparison_completeness(_names, ensembles)
        _ = cd.build_scenario_overview(_names, ensembles, {"legal_comunas": INFEASIBLE_RESULT})

        df_b = cd.rank_scenarios(cd.compare_ensembles(dict(ensembles)))

        pd.testing.assert_frame_equal(df_a, df_b)
        assert "legal_comunas" not in df_a["escenario"].values
        assert set(df_a["escenario"]) == {"apc_soft", "apc_free"}


# ─── End-to-end: compare_and_export() ──────────────────────────────────────

class TestCompareAndExportIntegration:

    def test_all_valid_scenarios_complete_and_previous_behavior_preserved(self, tmp_path):
        mod = _import_compare_scenarios()
        scenarios = [SimpleNamespace(name=n) for n in
                     ("legal_comunas", "apc_soft", "apc_free")]

        _write_ensemble(tmp_path, REGION_NAME, "legal_comunas",
                         _make_ensemble_df(0, 2.0, 0.50, 45, 0))
        _write_ensemble(tmp_path, REGION_NAME, "apc_soft",
                         _make_ensemble_df(1, 3.0, 0.55, 40, 2))
        _write_ensemble(tmp_path, REGION_NAME, "apc_free",
                         _make_ensemble_df(2, 5.0, 0.60, 35, 4))

        result = mod.compare_and_export(
            region_code=REGION_CODE, output_base=str(tmp_path),
            scenarios=scenarios, skip_viz=True,
        )

        assert result["completeness"]["comparison_status"]  == "COMPLETE"
        assert result["completeness"]["ranking_scope"]       == "full"
        assert result["completeness"]["missing_baseline"]    is None
        assert result["completeness"]["valid_ensembles"]     == 3
        assert len(result["ranking"]) == 3
        assert result["overview"]["included_in_scoring"].all()

        # Previous behavior preserved: ranking CSV written with all 3, ranked.
        comp_csv = tmp_path / REGION_NAME / "comparacion" / "comparacion_escenarios.csv"
        assert comp_csv.exists()
        df_saved = pd.read_csv(comp_csv)
        assert set(df_saved["escenario"]) == {"legal_comunas", "apc_soft", "apc_free"}
        assert set(df_saved["rank"]) == {1, 2, 3}
        # Baseline was present, so deltas vs legal_comunas must be computed.
        assert any(c.startswith("delta_") for c in df_saved.columns)

    def test_infeasible_baseline_marks_incomplete_but_stays_visible(self, tmp_path):
        mod = _import_compare_scenarios()
        scenarios = [SimpleNamespace(name=n) for n in
                     ("legal_comunas", "apc_soft", "apc_free")]

        _write_status(tmp_path, REGION_NAME, "legal_comunas", INFEASIBLE_RESULT)
        _write_ensemble(tmp_path, REGION_NAME, "apc_soft",
                         _make_ensemble_df(1, 3.0, 0.55, 40, 2))
        _write_ensemble(tmp_path, REGION_NAME, "apc_free",
                         _make_ensemble_df(2, 5.0, 0.60, 35, 4))

        result = mod.compare_and_export(
            region_code=REGION_CODE, output_base=str(tmp_path),
            scenarios=scenarios, skip_viz=True,
        )
        completeness, overview, ranking = (
            result["completeness"], result["overview"], result["ranking"]
        )

        assert completeness["comparison_status"]  == "INCOMPLETE"
        assert completeness["expected_scenarios"] == 3
        assert completeness["valid_ensembles"]    == 2
        assert completeness["missing_baseline"]   == "legal_comunas"
        assert completeness["ranking_scope"]      == "partial"

        # Still visible, with real status/reason, excluded from scoring.
        row = overview[overview["escenario"] == "legal_comunas"].iloc[0]
        assert row["status"] == "infeasible_population"
        assert row["reason"] == "indivisible_unit_exceeds_population_bound"
        assert row["included_in_scoring"] == False

        # Never entered the ranking: no row, no artificial score, no rank.
        assert "legal_comunas" not in ranking["escenario"].values
        assert len(ranking) == 2
        assert set(ranking["escenario"]) == {"apc_soft", "apc_free"}
        assert ranking["composite_score"].notna().all()

        # Ranking of the 2 valid scenarios matches computing them in isolation.
        direct = cd.rank_scenarios(cd.compare_ensembles({
            "apc_soft": pd.read_csv(tmp_path / REGION_NAME / "redistritaje" / "apc_soft" / "ensemble_stats.csv"),
            "apc_free": pd.read_csv(tmp_path / REGION_NAME / "redistritaje" / "apc_free" / "ensemble_stats.csv"),
        }))
        pd.testing.assert_frame_equal(
            ranking.reset_index(drop=True), direct.reset_index(drop=True)
        )

        # No baseline present -> no delta_* columns (no fabricated
        # "APC improves over the legal regime" comparison).
        assert not any(c.startswith("delta_") for c in ranking.columns)

        # Overview persisted to disk too (visible for downstream tooling).
        overview_csv = tmp_path / REGION_NAME / "comparacion" / "escenarios_overview.csv"
        assert overview_csv.exists()
        status_json = tmp_path / REGION_NAME / "comparacion" / "comparacion_status.json"
        assert status_json.exists()
        with open(status_json) as f:
            saved_completeness = json.load(f)
        assert saved_completeness["comparison_status"] == "INCOMPLETE"

    def test_sin_particion_distinct_status_also_incomplete(self, tmp_path):
        mod = _import_compare_scenarios()
        scenarios = [SimpleNamespace(name=n) for n in
                     ("legal_comunas", "apc_soft", "apc_free")]

        _write_ensemble(tmp_path, REGION_NAME, "legal_comunas",
                         _make_ensemble_df(0, 2.0, 0.50, 45, 0))
        _write_ensemble(tmp_path, REGION_NAME, "apc_soft",
                         _make_ensemble_df(1, 3.0, 0.55, 40, 2))
        _write_status(tmp_path, REGION_NAME, "apc_free", SIN_PARTICION_RESULT)

        result = mod.compare_and_export(
            region_code=REGION_CODE, output_base=str(tmp_path),
            scenarios=scenarios, skip_viz=True,
        )

        assert result["completeness"]["comparison_status"] == "INCOMPLETE"
        assert result["completeness"]["missing_baseline"]  is None
        row = result["overview"][result["overview"]["escenario"] == "apc_free"].iloc[0]
        assert row["status"] == "sin_particion"
        assert row["status"] != "infeasible_population"
        assert row["reason"] == "initialization_search_exhausted"
        assert row["included_in_scoring"] == False
        assert "apc_free" not in result["ranking"]["escenario"].values

        # Baseline (legal_comunas) IS present here, so deltas should exist —
        # sin_particion elsewhere must not suppress the baseline comparison.
        assert any(c.startswith("delta_") for c in result["ranking"].columns)


# ─── Persistence wiring in main()'s run loop ───────────────────────────────

class TestPersistScenarioStatus:

    def test_persists_non_ok_status(self, tmp_path):
        mod = _import_compare_scenarios()
        mod._persist_scenario_status(str(tmp_path), REGION_CODE, "legal_comunas", INFEASIBLE_RESULT)
        path = tmp_path / REGION_NAME / "redistritaje" / "legal_comunas" / "scenario_status.json"
        assert path.exists()
        with open(path) as f:
            saved = json.load(f)
        assert saved["status"] == "infeasible_population"
        assert saved["reason"] == "indivisible_unit_exceeds_population_bound"

    def test_ok_status_not_persisted_and_clears_stale_file(self, tmp_path):
        mod = _import_compare_scenarios()
        path = tmp_path / REGION_NAME / "redistritaje" / "legal_comunas" / "scenario_status.json"

        # Simulate a previous infeasible run leaving a status file...
        mod._persist_scenario_status(str(tmp_path), REGION_CODE, "legal_comunas", INFEASIBLE_RESULT)
        assert path.exists()

        # ...then a later run succeeds: the stale status must be cleared.
        mod._persist_scenario_status(str(tmp_path), REGION_CODE, "legal_comunas", {"status": "ok"})
        assert not path.exists()
