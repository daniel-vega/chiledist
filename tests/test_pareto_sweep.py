"""
tests/test_pareto_sweep.py
===========================
Tests unitarios para chiledist/pareto_sweep.py.

Ensemble sintético: 5 niveles de penalización × 20 planes.
El tradeoff es monotónico: mayor penalización → menos comunas partidas
pero mayor desviación poblacional.
"""

import math
import pytest
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from chiledist.inference.pareto_sweep import (
    SWEEP_METRICS,
    METRIC_DIRECTIONS,
    METRIC_LABELS,
    sweep_split_penalty,
    build_tradeoff_frontier,
    detect_knee_point,
    plot_tradeoff_curve,
    summarize_tradeoff,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures sintéticos
# ──────────────────────────────────────────────────────────────────────────────

PENALTIES = [0.0, 0.25, 0.5, 0.75, 1.0]
N_PLANS   = 20

def _make_ensemble(penalty: float, n: int = N_PLANS, seed: int = 0) -> pd.DataFrame:
    """
    Genera un ensemble sintético con tradeoff explícito.
    Mayor penalty → menor n_comunas_partidas, mayor max_dev_pob_pct.
    """
    rng = np.random.default_rng(seed + int(penalty * 100))
    return pd.DataFrame({
        "max_dev_pob_pct":    np.clip(rng.normal(5.0 + 10.0 * penalty, 1.2, n), 0.5, 30.0),
        "n_comunas_partidas": np.clip(rng.normal(10.0 * (1 - penalty), 1.5, n), 0.0, 20.0).round().astype(float),
        "split_severity":     rng.uniform(0.0, 1.0, n),
        "pp_promedio":        rng.uniform(0.1, 0.5, n),
        "pop_afectada_pct":   rng.uniform(0.0, 0.3, n),
        "cut_edges":          rng.integers(100, 300, n).astype(float),
        "score":              rng.uniform(0.0, 1.0, n),
    })


ENSEMBLES = {p: _make_ensemble(p) for p in PENALTIES}


@pytest.fixture(scope="module")
def sweep_df():
    return sweep_split_penalty(ENSEMBLES)


@pytest.fixture(scope="module")
def frontier_result(sweep_df):
    return build_tradeoff_frontier(sweep_df, n_bootstrap=50, random_state=0)


@pytest.fixture(scope="module")
def knee_result(frontier_result):
    return detect_knee_point(frontier_result["frontier"])


# ──────────────────────────────────────────────────────────────────────────────
# Tests: sweep_split_penalty
# ──────────────────────────────────────────────────────────────────────────────

class TestSweepSplitPenalty:
    def test_returns_dataframe(self, sweep_df):
        assert isinstance(sweep_df, pd.DataFrame)

    def test_penalty_column_present(self, sweep_df):
        assert "penalty" in sweep_df.columns

    def test_all_penalties_present(self, sweep_df):
        found = set(sweep_df["penalty"].unique())
        for p in PENALTIES:
            assert p in found

    def test_row_count(self, sweep_df):
        assert len(sweep_df) == len(PENALTIES) * N_PLANS

    def test_metric_columns_preserved(self, sweep_df):
        for col in ["max_dev_pob_pct", "n_comunas_partidas"]:
            assert col in sweep_df.columns

    def test_unknown_column_excluded(self, sweep_df):
        assert "score" not in sweep_df.columns

    def test_empty_input(self):
        result = sweep_split_penalty({})
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert "penalty" in result.columns

    def test_custom_metrics(self):
        custom = sweep_split_penalty(ENSEMBLES, metrics=["max_dev_pob_pct"])
        assert "max_dev_pob_pct" in custom.columns
        assert "n_comunas_partidas" not in custom.columns

    def test_single_penalty(self):
        single = sweep_split_penalty({0.5: _make_ensemble(0.5)})
        assert len(single) == N_PLANS
        assert (single["penalty"] == 0.5).all()


# ──────────────────────────────────────────────────────────────────────────────
# Tests: build_tradeoff_frontier
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildTradeoffFrontier:
    def test_returns_dict(self, frontier_result):
        assert isinstance(frontier_result, dict)

    def test_required_keys(self, frontier_result):
        for key in ["frontier", "all_plans", "per_penalty_stats",
                    "bootstrap_bands", "metadata"]:
            assert key in frontier_result

    def test_frontier_is_dataframe(self, frontier_result):
        assert isinstance(frontier_result["frontier"], pd.DataFrame)

    def test_all_plans_has_is_pareto(self, frontier_result):
        assert "is_pareto" in frontier_result["all_plans"].columns

    def test_frontier_nonempty(self, frontier_result):
        assert len(frontier_result["frontier"]) > 0

    def test_n_pareto_in_metadata(self, frontier_result):
        meta = frontier_result["metadata"]
        assert "n_pareto" in meta
        assert meta["n_pareto"] == frontier_result["all_plans"]["is_pareto"].sum()

    def test_pareto_plans_not_dominated(self, frontier_result, sweep_df):
        """Ningún plan Pareto debe ser dominado por otro plan del pool."""
        frontier = frontier_result["frontier"]
        x = "max_dev_pob_pct"
        y = "n_comunas_partidas"
        all_pts = sweep_df[[x, y]].dropna().values
        for _, row in frontier[[x, y]].dropna().iterrows():
            px, py = row[x], row[y]
            # No debe existir un plan que sea mejor-o-igual en ambos objetivos
            # y estrictamente mejor en al menos uno
            dominated_by = (
                ((all_pts[:, 0] <= px) & (all_pts[:, 1] <= py)) &
                ((all_pts[:, 0] < px) | (all_pts[:, 1] < py))
            )
            assert not dominated_by.any(), \
                f"Plan ({px}, {py}) debería ser dominado pero está en la frontera"

    def test_per_penalty_stats_has_penalties(self, frontier_result):
        stats = frontier_result["per_penalty_stats"]
        if not stats.empty:
            assert "penalty" in stats.columns

    def test_bootstrap_bands_shape(self, frontier_result):
        bb = frontier_result["bootstrap_bands"]
        if not bb.empty:
            assert "x_grid" in bb.columns
            assert "y_p5"   in bb.columns
            assert "y_p95"  in bb.columns

    def test_bootstrap_p5_le_p95(self, frontier_result):
        bb = frontier_result["bootstrap_bands"]
        if not bb.empty:
            assert (bb["y_p5"] <= bb["y_p95"]).all()

    def test_metadata_directions(self, frontier_result):
        meta = frontier_result["metadata"]
        assert "minimize_x" in meta
        assert "minimize_y" in meta

    def test_no_bootstrap(self, sweep_df):
        res = build_tradeoff_frontier(sweep_df, n_bootstrap=0)
        assert res["bootstrap_bands"].empty

    def test_custom_metrics(self, sweep_df):
        res = build_tradeoff_frontier(
            sweep_df,
            x_metric="split_severity",
            y_metric="pp_promedio",
            minimize_x=True,
            minimize_y=False,
            n_bootstrap=0,
        )
        assert res["metadata"]["x_metric"] == "split_severity"
        assert res["metadata"]["y_metric"] == "pp_promedio"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: detect_knee_point
# ──────────────────────────────────────────────────────────────────────────────

class TestDetectKneePoint:
    def test_returns_dict(self, knee_result):
        assert isinstance(knee_result, dict)

    def test_required_keys(self, knee_result):
        for key in ["knee_idx", "knee_x", "knee_y", "knee_penalty",
                    "distances", "diminishing_mask", "method"]:
            assert key in knee_result

    def test_knee_x_in_range(self, knee_result, frontier_result):
        frontier = frontier_result["frontier"]
        if knee_result["knee_x"] is not None:
            x_min = frontier["max_dev_pob_pct"].min()
            x_max = frontier["max_dev_pob_pct"].max()
            assert x_min <= knee_result["knee_x"] <= x_max

    def test_distances_length(self, knee_result, frontier_result):
        n = frontier_result["frontier"][["max_dev_pob_pct", "n_comunas_partidas"]].dropna().__len__()
        assert len(knee_result["distances"]) == n

    def test_distances_nonnegative(self, knee_result):
        assert (knee_result["distances"] >= 0).all()

    def test_knee_idx_valid(self, knee_result):
        if knee_result["knee_idx"] is not None:
            assert knee_result["knee_idx"] >= 0
            assert knee_result["knee_idx"] < len(knee_result["distances"])

    def test_knee_maximizes_distance(self, knee_result):
        if knee_result["knee_idx"] is not None and len(knee_result["distances"]) > 1:
            assert knee_result["distances"][knee_result["knee_idx"]] == \
                   pytest.approx(knee_result["distances"].max(), rel=1e-6)

    def test_empty_frontier(self):
        result = detect_knee_point(pd.DataFrame())
        assert result["knee_idx"] is None
        assert result["knee_x"]   is None

    def test_single_point(self):
        df = pd.DataFrame({"max_dev_pob_pct": [5.0], "n_comunas_partidas": [3.0],
                           "penalty": [0.5]})
        result = detect_knee_point(df)
        assert result["knee_x"] == pytest.approx(5.0)
        assert result["knee_y"] == pytest.approx(3.0)
        assert result["knee_idx"] == 0

    def test_raw_distance_method(self, frontier_result):
        result = detect_knee_point(
            frontier_result["frontier"], method="raw_distance"
        )
        assert result["method"] == "raw_distance"
        assert result["knee_idx"] is not None

    def test_diminishing_mask_length(self, knee_result, frontier_result):
        n = frontier_result["frontier"][["max_dev_pob_pct", "n_comunas_partidas"]].dropna().__len__()
        assert len(knee_result["diminishing_mask"]) == n


# ──────────────────────────────────────────────────────────────────────────────
# Tests: plot_tradeoff_curve
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotTradeoffCurve:
    def teardown_method(self):
        plt.close("all")

    def test_returns_figure(self, sweep_df, frontier_result):
        fig = plot_tradeoff_curve(sweep_df, frontier_result)
        assert isinstance(fig, plt.Figure)

    def test_with_knee(self, sweep_df, frontier_result, knee_result):
        fig = plot_tradeoff_curve(sweep_df, frontier_result, knee_result)
        assert isinstance(fig, plt.Figure)

    def test_without_scatter(self, sweep_df, frontier_result):
        fig = plot_tradeoff_curve(sweep_df, frontier_result, show_scatter=False)
        assert isinstance(fig, plt.Figure)

    def test_without_bands(self, sweep_df, frontier_result):
        fig = plot_tradeoff_curve(sweep_df, frontier_result, show_density_bands=False)
        assert isinstance(fig, plt.Figure)

    def test_custom_labels(self, sweep_df, frontier_result):
        fig = plot_tradeoff_curve(
            sweep_df, frontier_result,
            x_label="Desviación X", y_label="Particiones Y",
        )
        ax = fig.axes[0]
        assert "Desviación X" in ax.get_xlabel()

    def test_custom_title(self, sweep_df, frontier_result):
        fig = plot_tradeoff_curve(sweep_df, frontier_result, title="Mi título")
        ax = fig.axes[0]
        assert "Mi título" in ax.get_title()

    def test_save_path(self, sweep_df, frontier_result, tmp_path):
        out = str(tmp_path / "tradeoff.png")
        fig = plot_tradeoff_curve(sweep_df, frontier_result, save_path=out)
        import os
        assert os.path.exists(out)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: summarize_tradeoff
# ──────────────────────────────────────────────────────────────────────────────

class TestSummarizeTradeoff:
    def test_returns_dataframe(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        assert isinstance(s, pd.DataFrame)

    def test_index_is_penalty(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        assert s.index.name == "penalty"
        for p in PENALTIES:
            assert p in s.index

    def test_n_planes_correct(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        assert (s["n_planes"] == N_PLANS).all()

    def test_metric_mean_columns(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        assert "max_dev_pob_pct_mean" in s.columns
        assert "n_comunas_partidas_mean" in s.columns

    def test_metric_std_columns(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        assert "max_dev_pob_pct_std" in s.columns

    def test_is_knee_column(self, sweep_df, frontier_result, knee_result):
        s = summarize_tradeoff(sweep_df, frontier_result, knee_result)
        assert "is_knee" in s.columns
        assert s["is_knee"].sum() == 1

    def test_pct_pareto_column(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        if "pct_pareto" in s.columns:
            assert (s["pct_pareto"] >= 0).all()
            assert (s["pct_pareto"] <= 100).all()

    def test_without_knee(self, sweep_df, frontier_result):
        s = summarize_tradeoff(sweep_df, frontier_result)
        assert "is_knee" in s.columns
        assert (s["is_knee"] == False).all()

    def test_empty_input(self):
        empty = pd.DataFrame(columns=["penalty"])
        result = summarize_tradeoff(empty, {"all_plans": empty, "frontier": empty})
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Tests: constantes y metadatos del módulo
# ──────────────────────────────────────────────────────────────────────────────

class TestModuleConstants:
    def test_sweep_metrics_is_list(self):
        assert isinstance(SWEEP_METRICS, list)
        assert len(SWEEP_METRICS) > 0

    def test_metric_directions_keys(self):
        for m in SWEEP_METRICS:
            assert m in METRIC_DIRECTIONS

    def test_metric_directions_bool(self):
        for val in METRIC_DIRECTIONS.values():
            assert isinstance(val, bool)

    def test_metric_labels_keys(self):
        for m in SWEEP_METRICS:
            assert m in METRIC_LABELS

    def test_pp_promedio_is_max(self):
        assert METRIC_DIRECTIONS["pp_promedio"] is False
