"""
tests/test_scenario_analysis.py
=================================
Unit tests for:
    - pareto_frontier_nd (extended coverage)
    - ranking_concordance
    - compare_sensitivity

No external data or gerrychain required.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from chiledist.inference.sensitivity import compare_sensitivity, ranking_concordance
from chiledist.inference.comparison import pareto_frontier_nd


# ─── pareto_frontier_nd ───────────────────────────────────────────────────────

class TestParetoFrontierNd:

    def test_2d_known_case_minimize_both(self):
        """
        Points: [1,5], [2,3], [3,1], [4,2].  Minimize both.
        [4,2] is dominated by [3,1] (3<4 and 1<2).
        Pareto: {[1,5], [2,3], [3,1]}.
        """
        pts = np.array([[1, 5], [2, 3], [3, 1], [4, 2]])
        idx = pareto_frontier_nd(pts, minimize=[True, True])
        assert set(idx) == {0, 1, 2}

    def test_single_point(self):
        pts = np.array([[0.5, 3.0]])
        idx = pareto_frontier_nd(pts, minimize=[True, True])
        assert list(idx) == [0]

    def test_all_identical_all_pareto(self):
        """No point dominates another when all are identical."""
        pts = np.array([[1, 2], [1, 2], [1, 2]])
        idx = pareto_frontier_nd(pts, minimize=[True, True])
        assert len(idx) == 3

    def test_dominated_chain_only_minimum(self):
        """Strictly increasing: only the minimum point survives."""
        pts = np.array([[1, 1], [2, 2], [3, 3], [4, 4]])
        idx = pareto_frontier_nd(pts, minimize=[True, True])
        assert list(idx) == [0]

    def test_mixed_minimize_maximize(self):
        """
        Minimize x, maximize y.
        Points: [1,5], [2,4], [3,3], [1,3].
        [1,5] dominates [1,3] (same x, larger y) and [2,4] (smaller x, larger y)
        and [3,3]. Only [1,5] is Pareto-optimal.
        """
        pts = np.array([[1, 5], [2, 4], [3, 3], [1, 3]])
        idx = pareto_frontier_nd(pts, minimize=[True, False])
        assert 0 in idx         # [1,5] is definitely Pareto
        assert 3 not in idx     # [1,3] dominated by [1,5]

    def test_dict_minimize_with_dataframe(self):
        """minimize can be a dict when points is a DataFrame."""
        df = pd.DataFrame({"dev": [2.0, 5.0, 1.0], "splits": [5, 3, 6]})
        # [2,5], [5,3], [1,6]: no point dominates another → all 3 Pareto
        idx = pareto_frontier_nd(df, minimize={"dev": True, "splits": True})
        assert len(idx) == 3

    def test_none_minimize_defaults_to_minimize_all(self):
        pts = np.array([[1, 2], [2, 1], [3, 3]])
        idx_explicit = pareto_frontier_nd(pts, minimize=[True, True])
        idx_default  = pareto_frontier_nd(pts, minimize=None)
        np.testing.assert_array_equal(np.sort(idx_explicit), np.sort(idx_default))

    def test_returns_numpy_array(self):
        pts = np.array([[1, 2], [3, 4]])
        idx = pareto_frontier_nd(pts, minimize=[True, True])
        assert isinstance(idx, np.ndarray)

    def test_subset_of_original_indices(self):
        """All returned indices must be valid row indices of the input."""
        pts = np.array([[1, 5], [2, 3], [3, 1], [4, 2], [0, 6]])
        idx = pareto_frontier_nd(pts, minimize=[True, True])
        assert all(0 <= i < len(pts) for i in idx)

    def test_3d_case(self):
        """
        3D case: minimize all three objectives.
        [1,1,1] dominates [2,2,2] in all dimensions.
        [1,2,3] and [2,1,3] and [2,2,1] should all survive (no mutual domination).
        """
        pts = np.array([
            [1, 1, 1],   # 0: dominates [2,2,2]
            [2, 2, 2],   # 1: dominated
            [1, 2, 3],   # 2: not dominated by [1,1,1]? 1<=1, 1<=2, 1<=3 and 1<2 → yes, dominated
            [2, 1, 3],   # 3: dominated by [1,1,1]: 1<2, 1=1, 1<3
            [2, 2, 1],   # 4: dominated by [1,1,1]: 1<2, 1<2, 1=1
            [3, 3, 3],   # 5: dominated
        ])
        idx = pareto_frontier_nd(pts, minimize=[True, True, True])
        assert 0 in idx
        assert 1 not in idx
        assert 5 not in idx


# ─── ranking_concordance ─────────────────────────────────────────────────────

class TestRankingConcordance:

    def test_identical_ranking_tau_one(self):
        """Same scores → perfect concordance (tau = 1.0, rho = 1.0)."""
        scores = {"A": 0.8, "B": 0.6, "C": 0.7, "D": 0.5, "E": 0.9}
        result = ranking_concordance(scores, scores)
        assert result["kendall_tau"] == pytest.approx(1.0, abs=0.01)
        assert result["spearman_rho"] == pytest.approx(1.0, abs=0.01)

    def test_reversed_ranking_negative_tau(self):
        """Perfectly reversed ranking → tau = -1.0."""
        a = {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.3, "E": 0.1}
        b = {"A": 0.1, "B": 0.3, "C": 0.5, "D": 0.7, "E": 0.9}
        result = ranking_concordance(a, b)
        assert result["kendall_tau"] == pytest.approx(-1.0, abs=0.01)

    def test_required_keys(self):
        a = {"A": 1.0, "B": 0.5, "C": 0.2, "D": 0.8, "E": 0.7}
        b = {"A": 0.9, "B": 0.4, "C": 0.3, "D": 0.7, "E": 0.6}
        result = ranking_concordance(a, b)
        required = ("kendall_tau", "kendall_pval", "spearman_rho",
                    "spearman_pval", "n_comunes", "discordantes",
                    "bajo_potencia_estadistica")
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_n_comunes_counts_shared_keys(self):
        a = {"A": 1.0, "B": 0.5, "X": 0.9}
        b = {"A": 0.8, "B": 0.6, "Y": 0.7}   # only A and B in common
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = ranking_concordance(a, b)
        assert result["n_comunes"] == 2

    def test_single_common_returns_nan(self):
        a = {"A": 1.0}
        b = {"A": 0.5}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = ranking_concordance(a, b)
        assert np.isnan(result["kendall_tau"])
        assert result["bajo_potencia_estadistica"] is True

    def test_discordantes_is_list(self):
        a = {"A": 0.8, "B": 0.6, "C": 0.7, "D": 0.5, "E": 0.9}
        b = {"A": 0.7, "B": 0.8, "C": 0.6, "D": 0.6, "E": 0.8}
        result = ranking_concordance(a, b)
        assert isinstance(result["discordantes"], list)

    def test_bajo_potencia_when_n_lt_5(self):
        a = {"A": 1.0, "B": 0.5, "C": 0.2, "D": 0.8}   # 4 shared
        b = {"A": 0.9, "B": 0.4, "C": 0.3, "D": 0.7}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = ranking_concordance(a, b)
        assert result["bajo_potencia_estadistica"] is True

    def test_bajo_potencia_false_when_n_gte_5(self):
        a = {str(i): float(10 - i) for i in range(5)}   # 5 shared
        b = {str(i): float(10 - i) + 0.1 for i in range(5)}
        result = ranking_concordance(a, b)
        assert result["bajo_potencia_estadistica"] is False

    def test_concordant_ranking_no_discordantes(self):
        """Perfectly concordant rankings produce an empty discordantes list."""
        a = {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.3, "E": 0.1}
        b = {"A": 0.8, "B": 0.6, "C": 0.4, "D": 0.2, "E": 0.0}  # same order
        result = ranking_concordance(a, b)
        assert result["discordantes"] == []


# ─── compare_sensitivity ─────────────────────────────────────────────────────

class TestCompareSensitivity:

    @staticmethod
    def _ens_identical(n: int = 100, seed: int = 0):
        rng = np.random.default_rng(seed)
        df = pd.DataFrame({
            "max_dev_pob_pct": rng.normal(5, 1, n),
            "pp_promedio":     rng.uniform(0.3, 0.7, n),
        })
        return {"a": df.copy(), "b": df.copy()}

    @staticmethod
    def _ens_different(n: int = 100, seed: int = 0):
        rng = np.random.default_rng(seed)
        return {
            "a": pd.DataFrame({"max_dev_pob_pct": rng.normal(5, 0.5, n)}),
            "b": pd.DataFrame({"max_dev_pob_pct": rng.normal(15, 0.5, n)}),  # far apart
        }

    def test_returns_dataframe(self):
        result = compare_sensitivity(self._ens_identical(),
                                     metric_cols=["max_dev_pob_pct"])
        assert isinstance(result, pd.DataFrame)

    def test_required_columns(self):
        result = compare_sensitivity(self._ens_identical(),
                                     metric_cols=["max_dev_pob_pct"])
        required = ("par_a", "par_b", "metrica", "ks_stat", "ks_pvalue",
                    "mediana_a", "mediana_b", "delta_medianas",
                    "p_significativo", "efecto")
        for col in required:
            assert col in result.columns, f"Missing column: {col}"

    def test_identical_distributions_low_ks(self):
        """Two draws from identical distributions → ks_stat near 0."""
        rng = np.random.default_rng(99)
        df_a = pd.DataFrame({"x": rng.normal(5, 1, 200)})
        df_b = pd.DataFrame({"x": rng.normal(5, 1, 200)})
        result = compare_sensitivity({"a": df_a, "b": df_b}, metric_cols=["x"])
        assert result.iloc[0]["ks_stat"] < 0.20

    def test_very_different_distributions_high_ks(self):
        """Distributions with 10-sigma separation → ks_stat near 1.0."""
        result = compare_sensitivity(self._ens_different(),
                                     metric_cols=["max_dev_pob_pct"])
        assert result.iloc[0]["ks_stat"] > 0.80
        assert result.iloc[0]["efecto"] == "grande"

    def test_efecto_valid_categories(self):
        valid = {"negligible", "pequeño", "moderado", "grande"}
        result = compare_sensitivity(self._ens_different(),
                                     metric_cols=["max_dev_pob_pct"])
        assert set(result["efecto"].unique()).issubset(valid)

    def test_par_labels_match_input_keys(self):
        result = compare_sensitivity(
            {"x": pd.DataFrame({"v": [1, 2, 3]}),
             "y": pd.DataFrame({"v": [4, 5, 6]})},
            metric_cols=["v"],
        )
        assert result.iloc[0]["par_a"] == "x"
        assert result.iloc[0]["par_b"] == "y"

    def test_single_ensemble_empty(self):
        """One ensemble → no pairs → empty DataFrame."""
        result = compare_sensitivity(
            {"only": pd.DataFrame({"x": [1, 2, 3]})},
            metric_cols=["x"],
        )
        assert result.empty

    def test_n_rows_equals_n_choose_2_times_metrics(self):
        """3 ensembles × 2 metrics = C(3,2)*2 = 6 rows."""
        rng = np.random.default_rng(0)
        ensembles = {
            k: pd.DataFrame({"a": rng.normal(i, 1, 50), "b": rng.normal(i, 1, 50)})
            for k, i in [("x", 0), ("y", 1), ("z", 2)]
        }
        result = compare_sensitivity(ensembles, metric_cols=["a", "b"])
        assert len(result) == 6

    def test_missing_column_silently_skipped(self):
        """A metric absent from one ensemble produces no row for that pair."""
        result = compare_sensitivity(
            {"a": pd.DataFrame({"present": [1, 2, 3]}),
             "b": pd.DataFrame({"present": [4, 5, 6]})},
            metric_cols=["present", "absent"],
        )
        assert (result["metrica"] == "absent").sum() == 0
        assert (result["metrica"] == "present").sum() == 1

    def test_delta_medianas_sign(self):
        """delta_medianas = mediana_b - mediana_a."""
        result = compare_sensitivity(self._ens_different(),
                                     metric_cols=["max_dev_pob_pct"])
        row = result.iloc[0]
        expected_delta = round(row["mediana_b"] - row["mediana_a"], 4)
        assert row["delta_medianas"] == pytest.approx(expected_delta, abs=0.001)
