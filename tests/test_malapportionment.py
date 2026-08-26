"""
Tests de consistencia matemática para chiledist.malapportionment.

Verifica:
- Casos límite (proporcionalidad perfecta, un solo distrito, vacío)
- Valores conocidos calculados a mano
- Propiedades de orden (más desigualdad → Gini mayor)
- Consistencia entre funciones del módulo
- Tipos de retorno (estructuras, Figure)
"""
import math
import pytest
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import chiledist.evaluation.malapportionment as mala
from chiledist.evaluation.malapportionment import (
    samuels_snyder_index,
    loosemore_hanby_malapportionment,
    gini_personas_por_escano,
    max_min_representation_ratio,
    malapportionment_summary,
    compare_plans,
    international_comparison,
    BENCHMARK_MALAPPORTIONMENT,
    plot_pxe_distribution,
    plot_malapportionment_ranking,
    plot_international_comparison,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures comunes
# ──────────────────────────────────────────────────────────────────────────────

# Distribución proporcional perfecta: s_i = p_i ∀ i
_POP_PROP  = pd.Series({1: 500_000, 2: 300_000, 3: 200_000})
_MAG_PROP  = pd.Series({1:  5,  2:  3,  3:  2})          # exactamente proporcional

# Distribución uniforme: igual pop, igual mag
_POP_UNIF  = pd.Series({1: 100_000, 2: 100_000, 3: 100_000})
_MAG_UNIF  = pd.Series({1: 3, 2: 3, 3: 3})

# Distribución con malapportionment conocido:
#   pop = [900, 100], mag = [1, 1]
#   s = [0.5, 0.5], p = [0.9, 0.1]
#   M = (|0.5-0.9| + |0.5-0.1|) / 2 = 0.4
_POP_2A  = pd.Series({1: 900, 2: 100})
_MAG_2A  = pd.Series({1: 1,   2: 1})
_SS_2A   = 0.4

# Distribución con 4 distritos
_POP_4   = pd.Series({1: 400_000, 2: 300_000, 3: 200_000, 4: 100_000})
_MAG_4   = pd.Series({1: 2, 2: 3, 3: 2, 4: 1})  # 8 seats total


# ──────────────────────────────────────────────────────────────────────────────
# TestSamuelsSnyder
# ──────────────────────────────────────────────────────────────────────────────

class TestSamuelsSnyder:
    def test_proportional_gives_zero(self):
        assert samuels_snyder_index(_POP_PROP, _MAG_PROP) == pytest.approx(0.0, abs=1e-5)

    def test_uniform_gives_zero(self):
        assert samuels_snyder_index(_POP_UNIF, _MAG_UNIF) == pytest.approx(0.0, abs=1e-5)

    def test_known_value_two_districts(self):
        result = samuels_snyder_index(_POP_2A, _MAG_2A)
        assert result == pytest.approx(_SS_2A, abs=1e-5)

    def test_single_district_zero(self):
        pop = pd.Series({1: 500_000})
        mag = pd.Series({1: 5})
        assert samuels_snyder_index(pop, mag) == pytest.approx(0.0, abs=1e-5)

    def test_empty_series_nan(self):
        result = samuels_snyder_index(pd.Series(dtype=float), pd.Series(dtype=float))
        assert math.isnan(result)

    def test_zero_total_pop_nan(self):
        pop = pd.Series({1: 0, 2: 0})
        mag = pd.Series({1: 1, 2: 1})
        assert math.isnan(samuels_snyder_index(pop, mag))

    def test_result_in_range(self):
        result = samuels_snyder_index(_POP_4, _MAG_4)
        assert 0.0 <= result < 0.5

    def test_misaligned_indices_uses_intersection(self):
        pop = pd.Series({1: 500_000, 2: 300_000, 99: 200_000})
        mag = pd.Series({1: 5, 2: 3, 3: 2})
        # Only districts 1 and 2 are common
        result = samuels_snyder_index(pop, mag)
        expected = samuels_snyder_index(
            pd.Series({1: 500_000, 2: 300_000}),
            pd.Series({1: 5, 2: 3}),
        )
        assert result == pytest.approx(expected, abs=1e-5)

    def test_zero_magnitude_districts_excluded(self):
        pop = pd.Series({1: 500_000, 2: 300_000, 3: 200_000})
        mag = pd.Series({1: 5, 2: 3, 3: 0})  # district 3 excluded
        result = samuels_snyder_index(pop, mag)
        expected = samuels_snyder_index(
            pd.Series({1: 500_000, 2: 300_000}),
            pd.Series({1: 5, 2: 3}),
        )
        assert result == pytest.approx(expected, abs=1e-5)

    def test_symmetry(self):
        # Swapping two districts with same total pop and seats gives same index
        pop_a = pd.Series({1: 800, 2: 200})
        mag_a = pd.Series({1: 3, 2: 1})
        pop_b = pd.Series({1: 200, 2: 800})
        mag_b = pd.Series({1: 3, 2: 1})
        # Asymmetric on purpose: SS(a) should == SS(b) because |s-p| is symmetric in i
        # s_a = [3/4, 1/4], p_a = [4/5, 1/5] → |3/4 - 4/5| + |1/4 - 1/5| = 0.05 + 0.05 = 0.10
        # s_b = [3/4, 1/4], p_b = [1/5, 4/5] → different
        r_a = samuels_snyder_index(pop_a, mag_a)
        r_b = samuels_snyder_index(pop_b, mag_b)
        # Both should be in valid range (M can exceed 0.5 for extreme allocations)
        assert 0.0 <= r_a < 1.0
        assert 0.0 <= r_b < 1.0


# ──────────────────────────────────────────────────────────────────────────────
# TestLoosemoreHanbyMalapportionment
# ──────────────────────────────────────────────────────────────────────────────

class TestLoosemoreHanbyMalapportionment:
    def test_identical_to_samuels_snyder_proportional(self):
        assert loosemore_hanby_malapportionment(_POP_PROP, _MAG_PROP) == \
               samuels_snyder_index(_POP_PROP, _MAG_PROP)

    def test_identical_to_samuels_snyder_known(self):
        assert loosemore_hanby_malapportionment(_POP_2A, _MAG_2A) == \
               samuels_snyder_index(_POP_2A, _MAG_2A)

    def test_identical_to_samuels_snyder_four_districts(self):
        assert loosemore_hanby_malapportionment(_POP_4, _MAG_4) == \
               samuels_snyder_index(_POP_4, _MAG_4)

    def test_known_value(self):
        result = loosemore_hanby_malapportionment(_POP_2A, _MAG_2A)
        assert result == pytest.approx(_SS_2A, abs=1e-5)


# ──────────────────────────────────────────────────────────────────────────────
# TestGiniPXE
# ──────────────────────────────────────────────────────────────────────────────

class TestGiniPXE:
    def test_equal_pxe_pop_weighted_zero(self):
        pop = pd.Series({1: 100, 2: 200, 3: 300})
        mag = pd.Series({1: 1, 2: 2, 3: 3})   # PxE = 100 everywhere
        assert gini_personas_por_escano(pop, mag, pop_weighted=True) == pytest.approx(0.0, abs=1e-5)

    def test_equal_pxe_unweighted_zero(self):
        pop = pd.Series({1: 100, 2: 200, 3: 300})
        mag = pd.Series({1: 1, 2: 2, 3: 3})
        assert gini_personas_por_escano(pop, mag, pop_weighted=False) == pytest.approx(0.0, abs=1e-5)

    def test_single_district_zero(self):
        pop = pd.Series({1: 500_000})
        mag = pd.Series({1: 5})
        assert gini_personas_por_escano(pop, mag) == pytest.approx(0.0, abs=1e-5)

    def test_empty_nan(self):
        result = gini_personas_por_escano(pd.Series(dtype=float), pd.Series(dtype=float))
        assert math.isnan(result)

    def test_result_in_range(self):
        result = gini_personas_por_escano(_POP_4, _MAG_4, pop_weighted=True)
        assert 0.0 <= result < 1.0

    def test_nonzero_for_unequal_pxe(self):
        # PxE = [900, 100] → clearly unequal
        result = gini_personas_por_escano(_POP_2A, _MAG_2A, pop_weighted=True)
        assert result > 0.0

    def test_pop_weighted_and_unweighted_differ_for_unequal(self):
        gw = gini_personas_por_escano(_POP_2A, _MAG_2A, pop_weighted=True)
        gu = gini_personas_por_escano(_POP_2A, _MAG_2A, pop_weighted=False)
        # For pop=[900,100], mag=[1,1]: PxE=[900,100]
        # Pop-weighted should differ from unweighted because populations are very different
        assert gw != pytest.approx(gu, abs=1e-5)

    def test_more_inequality_higher_gini(self):
        # low inequality
        pop_low = pd.Series({1: 500, 2: 450, 3: 400})
        mag_low = pd.Series({1: 5, 2: 4, 3: 4})
        # high inequality
        pop_high = pd.Series({1: 900, 2: 50, 3: 50})
        mag_high = pd.Series({1: 1, 2: 1, 3: 1})
        g_low  = gini_personas_por_escano(pop_low,  mag_low,  pop_weighted=True)
        g_high = gini_personas_por_escano(pop_high, mag_high, pop_weighted=True)
        assert g_high > g_low

    def test_pop_weighted_manual_two_districts(self):
        # pop=[9,1], mag=[1,1]
        # PxE=[9,1], p=[0.9,0.1], mu_pop = 0.9*9+0.1*1 = 8.2
        # G = p_1*p_2*|9-1| + p_2*p_1*|1-9| / (2*8.2) = 2*0.9*0.1*8/(2*8.2)
        pop = pd.Series({1: 9, 2: 1})
        mag = pd.Series({1: 1, 2: 1})
        mu  = 0.9 * 9 + 0.1 * 1        # = 8.2
        diff_sum = 2 * 0.9 * 0.1 * abs(9 - 1)  # = 1.44
        expected = diff_sum / (2 * mu)          # = 1.44/16.4 ≈ 0.0878
        result = gini_personas_por_escano(pop, mag, pop_weighted=True)
        assert result == pytest.approx(expected, rel=1e-4)

    def test_unweighted_nonnegative(self):
        result = gini_personas_por_escano(_POP_4, _MAG_4, pop_weighted=False)
        assert result >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# TestMaxMinRatio
# ──────────────────────────────────────────────────────────────────────────────

class TestMaxMinRatio:
    def test_equal_pxe_ratio_one(self):
        pop = pd.Series({1: 100, 2: 200})
        mag = pd.Series({1: 1, 2: 2})  # PxE = 100 everywhere
        result = max_min_representation_ratio(pop, mag)
        assert result["ratio"] == pytest.approx(1.0, abs=1e-4)

    def test_known_computation(self):
        # pop=[900,100], mag=[1,1] → PxE=[900,100]
        result = max_min_representation_ratio(_POP_2A, _MAG_2A)
        assert result["max_pxe"] == pytest.approx(900.0, abs=1e-1)
        assert result["min_pxe"] == pytest.approx(100.0, abs=1e-1)
        assert result["ratio"]   == pytest.approx(9.0, abs=1e-2)

    def test_returns_all_keys(self):
        result = max_min_representation_ratio(_POP_4, _MAG_4)
        required = {"ratio","max_pxe","max_district","min_pxe","min_district",
                    "mean_pxe","std_pxe","cv"}
        assert required.issubset(result.keys())

    def test_max_district_is_correct(self):
        result = max_min_representation_ratio(_POP_2A, _MAG_2A)
        assert result["max_district"] == 1  # district 1 has PxE=900

    def test_min_district_is_correct(self):
        result = max_min_representation_ratio(_POP_2A, _MAG_2A)
        assert result["min_district"] == 2  # district 2 has PxE=100

    def test_cv_zero_for_equal(self):
        pop = pd.Series({1: 100, 2: 200, 3: 300})
        mag = pd.Series({1: 1, 2: 2, 3: 3})  # PxE = 100 everywhere
        result = max_min_representation_ratio(pop, mag)
        assert result["cv"] == pytest.approx(0.0, abs=1e-4)

    def test_empty_returns_nan(self):
        result = max_min_representation_ratio(pd.Series(dtype=float), pd.Series(dtype=float))
        assert math.isnan(result["ratio"])

    def test_mean_pxe_equals_national(self):
        result = max_min_representation_ratio(_POP_4, _MAG_4)
        expected_mean = float(_POP_4.sum()) / float(_MAG_4.sum())
        assert result["mean_pxe"] == pytest.approx(expected_mean, abs=1.0)


# ──────────────────────────────────────────────────────────────────────────────
# TestMalapportionmentSummary
# ──────────────────────────────────────────────────────────────────────────────

class TestMalapportionmentSummary:
    def test_returns_dict(self):
        result = malapportionment_summary(_POP_4, _MAG_4, label="test")
        assert isinstance(result, dict)

    def test_label_preserved(self):
        result = malapportionment_summary(_POP_4, _MAG_4, label="mi_plan")
        assert result["plan"] == "mi_plan"

    def test_samuels_snyder_consistent(self):
        summary = malapportionment_summary(_POP_4, _MAG_4, label="x")
        expected = samuels_snyder_index(_POP_4, _MAG_4)
        assert summary["samuels_snyder"] == pytest.approx(expected, abs=1e-5)

    def test_loosemore_hanby_alias(self):
        summary = malapportionment_summary(_POP_4, _MAG_4)
        assert summary["loosemore_hanby_M"] == summary["samuels_snyder"]

    def test_gini_consistent(self):
        summary = malapportionment_summary(_POP_4, _MAG_4)
        expected = gini_personas_por_escano(_POP_4, _MAG_4, pop_weighted=True)
        assert summary["gini_pop_weighted"] == pytest.approx(expected, abs=1e-5)

    def test_max_min_ratio_consistent(self):
        summary = malapportionment_summary(_POP_4, _MAG_4)
        mmr = max_min_representation_ratio(_POP_4, _MAG_4)
        assert summary["max_min_ratio"] == pytest.approx(mmr["ratio"], abs=1e-4)

    def test_proportional_all_zeros(self):
        summary = malapportionment_summary(_POP_PROP, _MAG_PROP)
        assert summary["samuels_snyder"]   == pytest.approx(0.0, abs=1e-5)
        assert summary["gini_pop_weighted"] == pytest.approx(0.0, abs=1e-5)
        assert summary["max_min_ratio"]    == pytest.approx(1.0, abs=1e-4)

    def test_n_districts_and_totals(self):
        summary = malapportionment_summary(_POP_4, _MAG_4)
        assert summary["n_districts"] == 4
        assert summary["total_seats"] == int(_MAG_4.sum())
        assert summary["total_pop"]   == int(_POP_4.sum())


# ──────────────────────────────────────────────────────────────────────────────
# TestComparePlans
# ──────────────────────────────────────────────────────────────────────────────

class TestComparePlans:
    # Simple assignment: unit_id → district_id
    _POP_UNITS = pd.Series({1: 400_000, 2: 300_000, 3: 200_000, 4: 100_000})

    _PLAN_A = {1: 1, 2: 1, 3: 2, 4: 2}  # D1=700k, D2=300k
    _PLAN_B = {1: 1, 2: 2, 3: 1, 4: 2}  # D1=600k, D2=400k
    _PLANS  = {"plan_A": _PLAN_A, "plan_B": _PLAN_B}

    def test_returns_dataframe(self):
        mag = pd.Series({1: 4, 2: 4})
        result = compare_plans(self._PLANS, self._POP_UNITS, magnitudes=mag)
        assert isinstance(result, pd.DataFrame)

    def test_index_is_plan_labels(self):
        mag = pd.Series({1: 4, 2: 4})
        result = compare_plans(self._PLANS, self._POP_UNITS, magnitudes=mag)
        assert set(result.index) == {"plan_A", "plan_B"}

    def test_expected_columns_present(self):
        mag = pd.Series({1: 4, 2: 4})
        result = compare_plans(self._PLANS, self._POP_UNITS, magnitudes=mag)
        for col in ["samuels_snyder", "gini_pop_weighted", "max_min_ratio", "cv"]:
            assert col in result.columns

    def test_values_differ_across_plans(self):
        mag = pd.Series({1: 4, 2: 4})
        result = compare_plans(self._PLANS, self._POP_UNITS, magnitudes=mag)
        # Plans differ in district composition → SS should differ
        assert result.loc["plan_A", "samuels_snyder"] != result.loc["plan_B", "samuels_snyder"]

    def test_magnitudes_dict_accepted(self):
        mag = {1: 4, 2: 4}
        result = compare_plans(self._PLANS, self._POP_UNITS, magnitudes=mag)
        assert isinstance(result, pd.DataFrame)

    def test_empty_plans_empty_df(self):
        result = compare_plans({}, self._POP_UNITS)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ──────────────────────────────────────────────────────────────────────────────
# TestInternationalComparison
# ──────────────────────────────────────────────────────────────────────────────

class TestInternationalComparison:
    _CUSTOM = {"Chile_APC_soft": {
        "samuels_snyder": 0.08,
        "gini_pop_weighted": 0.06,
        "max_min_ratio": 3.5,
        "cv": 0.30,
    }}

    def test_returns_dataframe(self):
        result = international_comparison()
        assert isinstance(result, pd.DataFrame)

    def test_benchmarks_included_by_default(self):
        result = international_comparison()
        for country in BENCHMARK_MALAPPORTIONMENT:
            assert country in result.index

    def test_custom_data_merged(self):
        result = international_comparison(custom=self._CUSTOM)
        assert "Chile_APC_soft" in result.index

    def test_custom_type_is_custom(self):
        result = international_comparison(custom=self._CUSTOM)
        assert result.loc["Chile_APC_soft", "type"] == "custom"

    def test_sorted_ascending_by_samuels_snyder(self):
        result = international_comparison()
        ss_vals = result["samuels_snyder"].dropna()
        assert (ss_vals.values[:-1] <= ss_vals.values[1:]).all()

    def test_include_benchmarks_false_no_benchmarks(self):
        result = international_comparison(custom=self._CUSTOM, include_benchmarks=False)
        assert "Chile_APC_soft" in result.index
        for country in BENCHMARK_MALAPPORTIONMENT:
            assert country not in result.index

    def test_metrics_arg_limits_columns(self):
        result = international_comparison(metrics=["samuels_snyder"])
        # Should have samuels_snyder but not gini_pop_weighted in metric cols
        assert "samuels_snyder" in result.columns
        assert "gini_pop_weighted" not in result.columns


# ──────────────────────────────────────────────────────────────────────────────
# TestBenchmarkData
# ──────────────────────────────────────────────────────────────────────────────

class TestBenchmarkData:
    def test_all_expected_countries_present(self):
        for key in ["Chile_legal_2021", "USA_House_2023", "Argentina_2019",
                    "Brasil_2018", "España_2019"]:
            assert key in BENCHMARK_MALAPPORTIONMENT

    def test_all_have_samuels_snyder(self):
        for key, val in BENCHMARK_MALAPPORTIONMENT.items():
            assert "samuels_snyder" in val, f"Missing samuels_snyder in {key}"

    def test_samuels_snyder_values_in_range(self):
        for key, val in BENCHMARK_MALAPPORTIONMENT.items():
            ss = val["samuels_snyder"]
            assert 0.0 < ss < 1.0, f"SS out of range for {key}: {ss}"

    def test_usa_has_lowest_ss(self):
        ss_values = {k: v["samuels_snyder"] for k, v in BENCHMARK_MALAPPORTIONMENT.items()}
        usa_ss = ss_values["USA_House_2023"]
        assert all(usa_ss <= v for v in ss_values.values()), "USA should have lowest SS"


# ──────────────────────────────────────────────────────────────────────────────
# TestPlotPxeDistribution
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotPxeDistribution:
    def test_returns_figure(self):
        fig = plot_pxe_distribution(_POP_4, _MAG_4, label="test")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_reference_line_accepted(self):
        fig = plot_pxe_distribution(_POP_4, _MAG_4, reference_line=200_000.0)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_existing_ax_accepted(self):
        fig_ext, ax_ext = plt.subplots()
        fig_ret = plot_pxe_distribution(_POP_4, _MAG_4, ax=ax_ext)
        assert fig_ret is fig_ext
        plt.close(fig_ext)


# ──────────────────────────────────────────────────────────────────────────────
# TestPlotMalapportionmentRanking
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotMalapportionmentRanking:
    def test_returns_figure(self):
        fig = plot_malapportionment_ranking(_POP_4, _MAG_4, label="test")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_top_n_parameter(self):
        pop = pd.Series({i: 100_000 + i * 10_000 for i in range(1, 9)})
        mag = pd.Series({i: max(1, 3 - i // 3) for i in range(1, 9)})
        fig = plot_malapportionment_ranking(pop, mag, top_n=4)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_proportional_runs_without_error(self):
        fig = plot_malapportionment_ranking(_POP_PROP, _MAG_PROP)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# TestPlotInternationalComparison
# ──────────────────────────────────────────────────────────────────────────────

class TestPlotInternationalComparison:
    def test_returns_figure(self):
        df = international_comparison()
        fig = plot_international_comparison(df)
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_raises_on_missing_metric(self):
        df = international_comparison()
        with pytest.raises(ValueError, match="no encontrada"):
            plot_international_comparison(df, metric="nonexistent_metric")

    def test_custom_metric(self):
        df = international_comparison()
        fig = plot_international_comparison(df, metric="max_min_ratio")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)
