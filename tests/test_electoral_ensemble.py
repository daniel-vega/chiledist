"""
tests/test_electoral_ensemble.py
==================================
Tests unitarios para chiledist/electoral_ensemble.py.

Ensemble sintético: 3 planes, 4 unidades, 2 circunscripciones.
"""

import math
import pytest
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from chiledist.inference.electoral_ensemble import (
    _dist_stats,
    _normalize_assignments,
    run_electoral_ensemble,
    ensemble_gallagher,
    ensemble_seat_bonus,
    ensemble_enp,
    ensemble_effective_threshold,
    summarize_electoral_ensemble,
    plot_ensemble_histogram,
    plot_ensemble_violin,
    plot_ensemble_ecdf,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

# Votos por unidad censal y partido
# 4 unidades, 3 partidos (A y B en pacto P1; C en pacto P2)
VOTES_DF = pd.DataFrame({
    "CUT":     [1, 1, 1,   2, 2, 2,   3, 3, 3,   4, 4, 4],
    "partido": ["A","B","C"] * 4,
    "votos":   [300,200,100, 400,100,100, 200,300,50, 100,200,150],
})

POP = pd.Series({1: 1000, 2: 800, 3: 1200, 4: 900})

MAGNITUDES = pd.Series({1: 3, 2: 4})

PACTO_MAP = {"A": "P1", "B": "P1", "C": "P2"}

# 3 planes: distintas asignaciones de unidades a distritos
PLAN_0 = {1: 1, 2: 1, 3: 2, 4: 2}   # D1: unidades 1,2 / D2: unidades 3,4
PLAN_1 = {1: 1, 2: 2, 3: 1, 4: 2}   # D1: unidades 1,3 / D2: unidades 2,4
PLAN_2 = {1: 2, 2: 1, 3: 1, 4: 2}   # D1: unidades 2,3 / D2: unidades 1,4

ENSEMBLE_LIST = [PLAN_0, PLAN_1, PLAN_2]
ENSEMBLE_DICT = {"plan_alpha": PLAN_0, "plan_beta": PLAN_1, "plan_gamma": PLAN_2}


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _dist_stats
# ──────────────────────────────────────────────────────────────────────────────

class TestDistStats:
    def test_basic_statistics(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        stats = _dist_stats(s)
        assert stats["mean"] == pytest.approx(3.0, rel=1e-5)
        assert stats["median"] == pytest.approx(3.0, rel=1e-5)
        assert stats["n"] == 5

    def test_percentiles(self):
        s = pd.Series(range(101))  # 0..100
        stats = _dist_stats(s)
        assert stats["p5"]  == pytest.approx(5.0,  abs=1.0)
        assert stats["p95"] == pytest.approx(95.0, abs=1.0)

    def test_ci95_contains_mean(self):
        s = pd.Series([10.0] * 20)
        stats = _dist_stats(s)
        assert stats["ci95_low"] <= stats["mean"] <= stats["ci95_high"]

    def test_empty_series_returns_nan(self):
        stats = _dist_stats(pd.Series([], dtype=float))
        assert math.isnan(stats["mean"])
        assert stats["n"] == 0

    def test_single_value(self):
        stats = _dist_stats(pd.Series([42.0]))
        assert stats["mean"] == pytest.approx(42.0)
        assert stats["std"] == pytest.approx(0.0)
        assert stats["n"] == 1

    def test_dropna(self):
        s = pd.Series([1.0, float("nan"), 3.0])
        stats = _dist_stats(s)
        assert stats["n"] == 2


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _normalize_assignments
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizeAssignments:
    def test_list_input(self):
        result = _normalize_assignments([PLAN_0, PLAN_1])
        assert len(result) == 2
        assert result[0][0] == "0"
        assert result[1][0] == "1"
        assert result[0][1] == PLAN_0

    def test_dict_input(self):
        result = _normalize_assignments(ENSEMBLE_DICT)
        ids = [r[0] for r in result]
        assert "plan_alpha" in ids
        assert "plan_beta" in ids


# ──────────────────────────────────────────────────────────────────────────────
# Tests: run_electoral_ensemble
# ──────────────────────────────────────────────────────────────────────────────

class TestRunElectoralEnsemble:
    def test_returns_dataframe(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert isinstance(res, pd.DataFrame)
        assert len(res) == 3

    def test_index_from_list(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert list(res.index) == ["0", "1", "2"]

    def test_index_from_dict(self):
        res = run_electoral_ensemble(
            ENSEMBLE_DICT, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert "plan_alpha" in res.index
        assert "plan_beta" in res.index

    def test_required_columns(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        for col in ["gallagher", "loosemore_hanby", "rae", "enp_votos", "enp_escanos",
                    "n_partidos_con_escanos", "modo_dhondt", "modo_magnitudes"]:
            assert col in res.columns, f"columna '{col}' falta"

    def test_binivel_mode(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP,
            magnitudes=MAGNITUDES, pacto_map=PACTO_MAP
        )
        assert (res["modo_dhondt"] == "binivel").all()

    def test_uninivel_mode(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert (res["modo_dhondt"] == "uninivel").all()

    def test_magnitudes_fijas(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert (res["modo_magnitudes"] == "fijas").all()

    def test_magnitudes_calculadas(self):
        res = run_electoral_ensemble(ENSEMBLE_LIST, VOTES_DF, POP)
        assert (res["modo_magnitudes"] == "calculadas").all()

    def test_seat_bonus_columns(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP,
            magnitudes=MAGNITUDES, include_seat_bonus=True
        )
        sb_cols = [c for c in res.columns if c.startswith("seat_bonus_")]
        assert len(sb_cols) >= 1

    def test_no_seat_bonus_columns(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP,
            magnitudes=MAGNITUDES, include_seat_bonus=False
        )
        sb_cols = [c for c in res.columns if c.startswith("seat_bonus_")]
        assert len(sb_cols) == 0

    def test_gallagher_in_range(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert (res["gallagher"] >= 0).all()
        assert (res["gallagher"] <= 100).all()

    def test_enp_at_least_one(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert (res["enp_votos"] >= 1.0).all()
        assert (res["enp_escanos"] >= 1.0).all()

    def test_empty_ensemble(self):
        res = run_electoral_ensemble([], VOTES_DF, POP, magnitudes=MAGNITUDES)
        assert isinstance(res, pd.DataFrame)
        assert len(res) == 0

    def test_magnitudes_as_dict(self):
        mags_dict = {1: 3, 2: 4}
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=mags_dict
        )
        assert len(res) == 3

    def test_n_partidos_con_escanos(self):
        res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )
        assert (res["n_partidos_con_escanos"] >= 1).all()


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ensemble_gallagher
# ──────────────────────────────────────────────────────────────────────────────

class TestEnsembleGallagher:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )

    def test_returns_dict(self):
        stats = ensemble_gallagher(self.res)
        assert isinstance(stats, dict)

    def test_required_keys(self):
        stats = ensemble_gallagher(self.res)
        for key in ["mean", "median", "std", "p5", "p25", "p75", "p95",
                    "ci95_low", "ci95_high", "n"]:
            assert key in stats

    def test_n_equals_ensemble_size(self):
        stats = ensemble_gallagher(self.res)
        assert stats["n"] == 3

    def test_raises_without_column(self):
        bad = self.res.drop(columns=["gallagher"])
        with pytest.raises(ValueError, match="gallagher"):
            ensemble_gallagher(bad)

    def test_mean_in_range(self):
        stats = ensemble_gallagher(self.res)
        assert 0.0 <= stats["mean"] <= 100.0


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ensemble_seat_bonus
# ──────────────────────────────────────────────────────────────────────────────

class TestEnsembleSeatBonus:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP,
            magnitudes=MAGNITUDES, include_seat_bonus=True
        )

    def test_all_parties_returns_dataframe(self):
        sb = ensemble_seat_bonus(self.res)
        assert isinstance(sb, pd.DataFrame)

    def test_index_is_party_names(self):
        sb = ensemble_seat_bonus(self.res)
        assert sb.index.name == "partido"
        assert len(sb) >= 1

    def test_specific_party_returns_dict(self):
        parties = [c[len("seat_bonus_"):] for c in self.res.columns
                   if c.startswith("seat_bonus_")]
        stats = ensemble_seat_bonus(self.res, partido=parties[0])
        assert isinstance(stats, dict)
        assert "mean" in stats

    def test_raises_missing_party(self):
        with pytest.raises(ValueError, match="no encontrado"):
            ensemble_seat_bonus(self.res, partido="INEXISTENTE_XYZ")

    def test_raises_no_seat_bonus_cols(self):
        no_sb = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP,
            magnitudes=MAGNITUDES, include_seat_bonus=False
        )
        with pytest.raises(ValueError, match="seat_bonus"):
            ensemble_seat_bonus(no_sb)

    def test_dataframe_has_stats_columns(self):
        sb = ensemble_seat_bonus(self.res)
        for col in ["mean", "median", "std", "n"]:
            assert col in sb.columns


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ensemble_enp
# ──────────────────────────────────────────────────────────────────────────────

class TestEnsembleEnp:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )

    def test_returns_dict_with_two_keys(self):
        enp = ensemble_enp(self.res)
        assert "enp_votos" in enp
        assert "enp_escanos" in enp

    def test_enp_values_are_dicts(self):
        enp = ensemble_enp(self.res)
        assert isinstance(enp["enp_votos"], dict)
        assert isinstance(enp["enp_escanos"], dict)

    def test_raises_missing_column(self):
        bad = self.res.drop(columns=["enp_votos"])
        with pytest.raises(ValueError, match="enp_votos"):
            ensemble_enp(bad)

    def test_enp_values_at_least_one(self):
        enp = ensemble_enp(self.res)
        assert enp["enp_votos"]["mean"] >= 1.0
        assert enp["enp_escanos"]["mean"] >= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ensemble_effective_threshold
# ──────────────────────────────────────────────────────────────────────────────

class TestEnsembleEffectiveThreshold:
    def _make_mags_list(self):
        return [
            pd.Series({1: 3, 2: 4}),
            pd.Series({1: 3, 2: 5}),
            pd.Series({1: 4, 2: 4}),
        ]

    def test_returns_dataframe(self):
        df = ensemble_effective_threshold(self._make_mags_list())
        assert isinstance(df, pd.DataFrame)

    def test_index_is_districts(self):
        df = ensemble_effective_threshold(self._make_mags_list())
        assert 1 in df.index
        assert 2 in df.index

    def test_thresholds_in_range(self):
        df = ensemble_effective_threshold(self._make_mags_list())
        assert (df["mean"] > 0).all()
        assert (df["mean"] <= 1.0).all()

    def test_accepts_dict_list(self):
        mags_list = [{1: 3, 2: 4}, {1: 5, 2: 3}]
        df = ensemble_effective_threshold(mags_list)
        assert len(df) == 2

    def test_fixed_magnitude_std_zero(self):
        # Si todos los planes tienen la misma magnitud, std debe ser 0
        mags_list = [pd.Series({1: 3, 2: 4})] * 5
        df = ensemble_effective_threshold(mags_list)
        assert df.loc[1, "std"] == pytest.approx(0.0, abs=1e-10)
        assert df.loc[2, "std"] == pytest.approx(0.0, abs=1e-10)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: summarize_electoral_ensemble
# ──────────────────────────────────────────────────────────────────────────────

class TestSummarizeElectoralEnsemble:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP,
            magnitudes=MAGNITUDES, include_seat_bonus=True
        )

    def test_returns_dataframe(self):
        s = summarize_electoral_ensemble(self.res)
        assert isinstance(s, pd.DataFrame)

    def test_index_contains_scalar_metrics(self):
        s = summarize_electoral_ensemble(self.res)
        for m in ["gallagher", "enp_votos", "enp_escanos"]:
            assert m in s.index

    def test_includes_seat_bonus(self):
        s = summarize_electoral_ensemble(self.res)
        sb_rows = [i for i in s.index if i.startswith("seat_bonus_")]
        assert len(sb_rows) >= 1

    def test_columns(self):
        s = summarize_electoral_ensemble(self.res)
        for col in ["mean", "median", "std", "p5", "p95", "ci95_low", "ci95_high", "n"]:
            assert col in s.columns

    def test_n_equals_ensemble_size(self):
        s = summarize_electoral_ensemble(self.res)
        assert (s["n"] == 3).all()

    def test_empty_ensemble(self):
        empty = pd.DataFrame()
        s = summarize_electoral_ensemble(empty)
        assert isinstance(s, pd.DataFrame)
        assert len(s) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Tests: plot_ensemble_histogram
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotEnsembleHistogram:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )

    def teardown_method(self):
        plt.close("all")

    def test_returns_figure(self):
        fig = plot_ensemble_histogram(self.res, metric="gallagher")
        assert isinstance(fig, plt.Figure)

    def test_with_observed_value(self):
        fig = plot_ensemble_histogram(self.res, metric="gallagher", observed=5.0)
        assert isinstance(fig, plt.Figure)

    def test_raises_unknown_metric(self):
        with pytest.raises(ValueError, match="no encontrada"):
            plot_ensemble_histogram(self.res, metric="INEXISTENTE_XYZ")

    def test_existing_ax(self):
        fig0, ax = plt.subplots()
        fig_ret = plot_ensemble_histogram(self.res, metric="gallagher", ax=ax)
        assert fig_ret is fig0


# ──────────────────────────────────────────────────────────────────────────────
# Tests: plot_ensemble_violin
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotEnsembleViolin:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )

    def teardown_method(self):
        plt.close("all")

    def test_returns_figure(self):
        fig = plot_ensemble_violin(self.res)
        assert isinstance(fig, plt.Figure)

    def test_custom_metrics(self):
        fig = plot_ensemble_violin(self.res, metrics=["gallagher", "enp_votos"])
        assert isinstance(fig, plt.Figure)

    def test_with_observed(self):
        fig = plot_ensemble_violin(
            self.res, observed={"gallagher": 4.0, "enp_votos": 2.5}
        )
        assert isinstance(fig, plt.Figure)

    def test_raises_no_metrics(self):
        with pytest.raises(ValueError, match="No hay métricas"):
            plot_ensemble_violin(self.res, metrics=[])


# ──────────────────────────────────────────────────────────────────────────────
# Tests: plot_ensemble_ecdf
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotEnsembleEcdf:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.res = run_electoral_ensemble(
            ENSEMBLE_LIST, VOTES_DF, POP, magnitudes=MAGNITUDES
        )

    def teardown_method(self):
        plt.close("all")

    def test_returns_figure(self):
        fig = plot_ensemble_ecdf(self.res, metric="gallagher")
        assert isinstance(fig, plt.Figure)

    def test_with_observed(self):
        fig = plot_ensemble_ecdf(self.res, metric="gallagher", observed=4.0)
        assert isinstance(fig, plt.Figure)

    def test_raises_unknown_metric(self):
        with pytest.raises(ValueError, match="no encontrada"):
            plot_ensemble_ecdf(self.res, metric="INEXISTENTE_XYZ")

    def test_existing_ax(self):
        fig0, ax = plt.subplots()
        fig_ret = plot_ensemble_ecdf(self.res, metric="gallagher", ax=ax)
        assert fig_ret is fig0
