"""
tests/test_fairshare.py
========================
Tests unitarios para chiledist/fairshare.py.

Cobertura:
    - fair_share_matrix (method='district' y 'biproportional')
    - results_to_matrix
    - l1_distance_fair_share
    - l2_distance_fair_share
    - max_cell_deviation
    - fair_share_summary
    - Validación de inputs (errores y warnings)

No requiere datos externos ni gerrychain.

Casos canónicos
---------------
Caso 1 — simétrico (métodos coinciden):
    D1: A=600, B=400, seats=5  → q_A=3, q_B=2
    D2: A=200, B=800, seats=5  → q_A=1, q_B=4
    Cuotas nacionales: A=4, B=6 (coincide con suma de filas de ambos métodos)

Caso 2 — asimétrico (métodos divergen):
    D1: A=900, B=100, seats=8  → district: q_A=7.2, q_B=0.8
    D2: A=100, B=900, seats=2  → district: q_A=0.2, q_B=1.8
    row sums district: A=7.4, B=2.6
    Cuotas nacionales: A=5, B=5 (biproportional las respeta)

Caso 3 — tres partidos:
    D1: A=500, B=300, C=200, seats=5
    D2: A=100, B=200, C=700, seats=5
    Cuotas nacionales (de 10 escaños): A=3.0, B=2.5, C=4.5
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from chiledist.fairshare import (
    fair_share_matrix,
    fair_share_summary,
    l1_distance_fair_share,
    l2_distance_fair_share,
    max_cell_deviation,
    results_to_matrix,
)


# ─── Fixtures de módulo ───────────────────────────────────────────────────────

VOTES_SYM = pd.DataFrame({
    "district": [1, 1, 2, 2],
    "partido":  ["A", "B", "A", "B"],
    "votos":    [600, 400, 200, 800],
})
MAGS_EQ = pd.Series({1: 5, 2: 5})

VOTES_ASYM = pd.DataFrame({
    "district": [1, 1, 2, 2],
    "partido":  ["A", "B", "A", "B"],
    "votos":    [900.0, 100.0, 100.0, 900.0],
})
MAGS_UNEQ = pd.Series({1: 8, 2: 2})

VOTES_3P = pd.DataFrame({
    "district": [1, 1, 1, 2, 2, 2],
    "partido":  ["A", "B", "C", "A", "B", "C"],
    "votos":    [500, 300, 200, 100, 200, 700],
})
MAGS_3P = pd.Series({1: 5, 2: 5})

# Integer allocation que coincide exactamente con el fair share del caso 1
N_EXACT = pd.DataFrame({1: {"A": 3, "B": 2}, 2: {"A": 1, "B": 4}})
# Integer allocation con distorsión conocida respecto al caso 1
# A sobrerrepresentada en D1, subrepresentada en D2
N_DISTORTED = pd.DataFrame({1: {"A": 4, "B": 1}, 2: {"A": 0, "B": 5}})


# ─── fair_share_matrix — método district ─────────────────────────────────────

class TestFairShareMatrixDistrict:

    def test_returns_dataframe(self):
        Q = fair_share_matrix(VOTES_SYM, MAGS_EQ, method="district")
        assert isinstance(Q, pd.DataFrame)

    def test_symmetric_known_values(self):
        """Caso canónico: proporciones exactas → Q debe ser entero."""
        Q = fair_share_matrix(VOTES_SYM, MAGS_EQ, method="district")
        assert Q.loc["A", 1] == pytest.approx(3.0, rel=1e-9)
        assert Q.loc["B", 1] == pytest.approx(2.0, rel=1e-9)
        assert Q.loc["A", 2] == pytest.approx(1.0, rel=1e-9)
        assert Q.loc["B", 2] == pytest.approx(4.0, rel=1e-9)

    def test_column_sums_equal_magnitudes(self):
        """La suma de cada columna debe igualar la magnitud del distrito."""
        Q = fair_share_matrix(VOTES_SYM, MAGS_EQ, method="district")
        for d, m in MAGS_EQ.items():
            assert Q[d].sum() == pytest.approx(m, rel=1e-9)

    def test_column_sums_unequal_magnitudes(self):
        Q = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="district")
        for d, m in MAGS_UNEQ.items():
            assert Q[d].sum() == pytest.approx(m, rel=1e-9)

    def test_district_row_sums_not_equal_national_quotas_when_asymmetric(self):
        """Caso asimétrico: método distrital NO respeta cuotas nacionales."""
        Q = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="district")
        total_v = VOTES_ASYM["votos"].sum()
        total_s = MAGS_UNEQ.sum()
        qa = VOTES_ASYM.groupby("partido")["votos"].sum()["A"] / total_v * total_s
        # quota_A ≈ 5.0, but district row sum A = 7.4
        assert Q.loc["A"].sum() != pytest.approx(qa, abs=0.5)

    def test_nonnegative_entries(self):
        Q = fair_share_matrix(VOTES_3P, MAGS_3P, method="district")
        assert (Q.to_numpy() >= 0).all()

    def test_three_parties_proportions(self):
        """Proporciones dentro de cada distrito se preservan."""
        Q = fair_share_matrix(VOTES_3P, MAGS_3P, method="district")
        # D1: A:B:C = 5:3:2 → escaños: 2.5, 1.5, 1.0 (de 5)
        assert Q.loc["A", 1] == pytest.approx(2.5, rel=1e-9)
        assert Q.loc["B", 1] == pytest.approx(1.5, rel=1e-9)
        assert Q.loc["C", 1] == pytest.approx(1.0, rel=1e-9)


# ─── fair_share_matrix — método biproportional ───────────────────────────────

class TestFairShareMatrixBiproportional:

    def test_symmetric_coincides_with_district(self):
        """En el caso simétrico ambos métodos dan el mismo resultado."""
        Q_d  = fair_share_matrix(VOTES_SYM, MAGS_EQ, method="district")
        Q_bp = fair_share_matrix(VOTES_SYM, MAGS_EQ, method="biproportional")
        np.testing.assert_allclose(Q_d.to_numpy(), Q_bp.to_numpy(), atol=1e-8)

    def test_column_sums_equal_magnitudes(self):
        Q = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="biproportional")
        for d, m in MAGS_UNEQ.items():
            assert Q[d].sum() == pytest.approx(m, rel=1e-7)

    def test_row_sums_equal_hamilton_quotas(self):
        """El método biproporcional respeta las cuotas Hamilton nacionales."""
        Q = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="biproportional")
        total_v = VOTES_ASYM["votos"].sum()
        total_s = float(MAGS_UNEQ.sum())
        votes_by_party = VOTES_ASYM.groupby("partido")["votos"].sum()
        for p in Q.index:
            quota = votes_by_party[p] / total_v * total_s
            assert Q.loc[p].sum() == pytest.approx(quota, rel=1e-6)

    def test_biproportional_differs_from_district_when_asymmetric(self):
        """Los métodos difieren cuando la distribución geográfica de votos es asimétrica."""
        Q_d  = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="district")
        Q_bp = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="biproportional")
        assert not np.allclose(Q_d.to_numpy(), Q_bp.to_numpy(), atol=0.1)

    def test_three_parties_row_sums(self):
        Q = fair_share_matrix(VOTES_3P, MAGS_3P, method="biproportional")
        total_v = VOTES_3P["votos"].sum()
        total_s = float(MAGS_3P.sum())
        vbp = VOTES_3P.groupby("partido")["votos"].sum()
        for p in Q.index:
            expected = vbp[p] / total_v * total_s
            assert Q.loc[p].sum() == pytest.approx(expected, rel=1e-6)

    def test_nonnegative_entries(self):
        Q = fair_share_matrix(VOTES_3P, MAGS_3P, method="biproportional")
        assert (Q.to_numpy() >= 0).all()

    def test_total_seats_conserved(self):
        """La suma total de Q debe igualar el total de escaños."""
        Q = fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="biproportional")
        assert Q.to_numpy().sum() == pytest.approx(MAGS_UNEQ.sum(), rel=1e-9)

    def test_custom_columns(self):
        """Acepta columnas con nombres personalizados."""
        votes_alt = VOTES_SYM.rename(columns={
            "district": "dist", "partido": "party", "votos": "votes"
        })
        Q = fair_share_matrix(
            votes_alt, MAGS_EQ,
            district_col="dist", partido_col="party", votos_col="votes",
        )
        assert Q.shape == (2, 2)

    def test_dict_magnitudes(self):
        """Acepta magnitudes como dict además de pd.Series."""
        Q = fair_share_matrix(VOTES_SYM, {1: 5, 2: 5}, method="biproportional")
        assert Q.loc["A", 1] == pytest.approx(3.0, rel=1e-7)

    def test_convergence_warning(self):
        """Advierte si IPF no converge con max_iter muy bajo."""
        with pytest.warns(UserWarning, match="IPF no convergió"):
            fair_share_matrix(VOTES_ASYM, MAGS_UNEQ, method="biproportional",
                              max_iter=1, tol=1e-15)


# ─── fair_share_matrix — validación de inputs ────────────────────────────────

class TestFairShareMatrixValidation:

    def test_missing_column_raises(self):
        bad = VOTES_SYM.drop(columns=["votos"])
        with pytest.raises(ValueError, match="votos"):
            fair_share_matrix(bad, MAGS_EQ)

    def test_negative_votes_raises(self):
        bad = VOTES_SYM.copy()
        bad.loc[0, "votos"] = -1
        with pytest.raises(ValueError, match="votos negativos"):
            fair_share_matrix(bad, MAGS_EQ)

    def test_zero_magnitude_raises(self):
        with pytest.raises(ValueError, match="≤ 0"):
            fair_share_matrix(VOTES_SYM, {1: 5, 2: 0})

    def test_uncovered_district_raises(self):
        with pytest.raises(ValueError, match="no cubre"):
            fair_share_matrix(VOTES_SYM, {1: 5})  # missing district 2

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="no reconocido"):
            fair_share_matrix(VOTES_SYM, MAGS_EQ, method="hamilton")  # type: ignore

    def test_zero_total_votes_raises(self):
        zero_votes = VOTES_SYM.copy()
        zero_votes["votos"] = 0
        with pytest.raises(ValueError, match="total de votos.*cero"):
            fair_share_matrix(zero_votes, MAGS_EQ, method="biproportional")


# ─── results_to_matrix ────────────────────────────────────────────────────────

class TestResultsToMatrix:

    def _make_results(self) -> pd.DataFrame:
        return pd.DataFrame({
            "district": [1, 1, 2, 2],
            "partido":  ["A", "B", "A", "B"],
            "escanos":  [3, 2, 1, 4],
        })

    def test_returns_dataframe(self):
        assert isinstance(results_to_matrix(self._make_results()), pd.DataFrame)

    def test_shape(self):
        N = results_to_matrix(self._make_results())
        assert N.shape == (2, 2)

    def test_values(self):
        N = results_to_matrix(self._make_results())
        assert N.loc["A", 1] == 3
        assert N.loc["B", 2] == 4

    def test_missing_parties_get_zero(self):
        """Partido ausente en un distrito → celda = 0 (por fill_value)."""
        results = pd.DataFrame({
            "district": [1],
            "partido":  ["A"],
            "escanos":  [5],
        })
        N = results_to_matrix(results)
        assert N.loc["A", 1] == 5

    def test_missing_column_raises(self):
        bad = self._make_results().drop(columns=["escanos"])
        with pytest.raises(ValueError, match="escanos"):
            results_to_matrix(bad)

    def test_custom_column_names(self):
        results = pd.DataFrame({
            "dist": [1, 2], "party": ["A", "B"], "seats": [3, 4]
        })
        N = results_to_matrix(results, district_col="dist",
                               partido_col="party", escanos_col="seats")
        assert N.loc["A", 1] == 3


# ─── l1_distance_fair_share ───────────────────────────────────────────────────

class TestL1Distance:

    def _q(self) -> pd.DataFrame:
        return fair_share_matrix(VOTES_SYM, MAGS_EQ, method="biproportional")

    def test_zero_when_exact(self):
        Q = self._q()
        assert l1_distance_fair_share(N_EXACT, Q) == pytest.approx(0.0, abs=1e-9)

    def test_known_value_distorted(self):
        """N_DISTORTED: A sobresale en D1 (+1), B sobresale en D2 (+1), etc."""
        Q = self._q()
        # N_DISTORTED = [[4,0],[1,5]], Q = [[3,1],[2,4]]
        # L1 = |4-3| + |0-1| + |1-2| + |5-4| = 4.0
        result = l1_distance_fair_share(N_DISTORTED, Q)
        assert result == pytest.approx(4.0, abs=1e-9)

    def test_normalized(self):
        Q = self._q()
        l1_raw  = l1_distance_fair_share(N_DISTORTED, Q)
        l1_norm = l1_distance_fair_share(N_DISTORTED, Q, normalize=True)
        total_seats = float(MAGS_EQ.sum())
        assert l1_norm == pytest.approx(l1_raw / total_seats, rel=1e-9)

    def test_normalized_in_range(self):
        Q = self._q()
        l1_norm = l1_distance_fair_share(N_DISTORTED, Q, normalize=True)
        assert 0.0 <= l1_norm <= 2.0

    def test_symmetric_property(self):
        """L1(N, Q) == L1(Q_as_int, N_as_float): distancia es simétrica."""
        Q = self._q()
        d1 = l1_distance_fair_share(N_DISTORTED, Q)
        d2 = l1_distance_fair_share(Q, N_DISTORTED)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_nonnegative(self):
        Q = self._q()
        assert l1_distance_fair_share(N_DISTORTED, Q) >= 0.0


# ─── l2_distance_fair_share ───────────────────────────────────────────────────

class TestL2Distance:

    def _q(self) -> pd.DataFrame:
        return fair_share_matrix(VOTES_SYM, MAGS_EQ, method="biproportional")

    def test_zero_when_exact(self):
        Q = self._q()
        assert l2_distance_fair_share(N_EXACT, Q) == pytest.approx(0.0, abs=1e-9)

    def test_known_value_distorted(self):
        """L2 = sqrt(1²+1²+1²+1²) = 2.0"""
        Q = self._q()
        assert l2_distance_fair_share(N_DISTORTED, Q) == pytest.approx(2.0, rel=1e-9)

    def test_normalize_returns_rmse(self):
        Q = self._q()
        l2   = l2_distance_fair_share(N_DISTORTED, Q, normalize=False)
        rmse = l2_distance_fair_share(N_DISTORTED, Q, normalize=True)
        n_cells = N_DISTORTED.shape[0] * N_DISTORTED.shape[1]
        assert rmse == pytest.approx(l2 / np.sqrt(n_cells), rel=1e-9)

    def test_l2_geq_max_dev(self):
        """L2 ≥ max_dev siempre (la norma de Frobenius domina la entrada máxima)."""
        Q = self._q()
        l2  = l2_distance_fair_share(N_DISTORTED, Q)
        mcd = max_cell_deviation(N_DISTORTED, Q)
        assert l2 >= mcd["max_dev"] - 1e-12

    def test_l1_geq_l2_for_same_matrices(self):
        """Para matrices pequeñas L1 ≥ L2 (norma L1 ≥ norma Frobenius en ℝ^n)."""
        Q  = self._q()
        l1 = l1_distance_fair_share(N_DISTORTED, Q)
        l2 = l2_distance_fair_share(N_DISTORTED, Q)
        assert l1 >= l2 - 1e-12


# ─── max_cell_deviation ───────────────────────────────────────────────────────

class TestMaxCellDeviation:

    def _q(self) -> pd.DataFrame:
        return fair_share_matrix(VOTES_SYM, MAGS_EQ, method="biproportional")

    def test_zero_when_exact(self):
        Q = self._q()
        mcd = max_cell_deviation(N_EXACT, Q)
        assert mcd["max_dev"] == pytest.approx(0.0, abs=1e-9)
        assert mcd["direction"] == "exacto"

    def test_known_max_when_distorted(self):
        Q = self._q()
        mcd = max_cell_deviation(N_DISTORTED, Q)
        assert mcd["max_dev"] == pytest.approx(1.0, abs=1e-9)

    def test_returns_required_keys(self):
        Q = self._q()
        mcd = max_cell_deviation(N_DISTORTED, Q)
        for key in ("max_dev", "partido", "distrito", "n_obs", "q_ideal", "direction"):
            assert key in mcd, f"Clave faltante: {key}"

    def test_direction_sobre(self):
        """A en D1: n=4, q=3 → sobre-representado."""
        Q = self._q()
        mcd = max_cell_deviation(N_DISTORTED, Q)
        # La celda max puede ser A/D1 (n=4,q=3) o B/D2 (n=5,q=4) — ambas +1
        assert mcd["direction"] == "sobre"

    def test_direction_sub(self):
        """Asignación donde A pierde escaños."""
        N_sub = pd.DataFrame({1: {"A": 2, "B": 3}, 2: {"A": 1, "B": 4}})
        Q = self._q()
        mcd = max_cell_deviation(N_sub, Q)
        # A en D1: n=2, q=3 → sub
        assert mcd["n_obs"] < mcd["q_ideal"]
        assert mcd["direction"] == "sub"

    def test_partido_and_distrito_valid(self):
        """Los valores de partido y distrito son del índice/columna real."""
        Q = self._q()
        mcd = max_cell_deviation(N_DISTORTED, Q)
        assert mcd["partido"] in N_DISTORTED.index
        assert mcd["distrito"] in N_DISTORTED.columns


# ─── fair_share_summary ───────────────────────────────────────────────────────

class TestFairShareSummary:

    def _q(self) -> pd.DataFrame:
        return fair_share_matrix(VOTES_SYM, MAGS_EQ, method="biproportional")

    def test_returns_dict(self):
        Q = self._q()
        assert isinstance(fair_share_summary(N_EXACT, Q), dict)

    def test_required_keys(self):
        Q = self._q()
        s = fair_share_summary(N_EXACT, Q)
        required = (
            "plan", "l1", "l1_norm", "l2", "rmse",
            "max_dev", "max_dev_partido", "max_dev_distrito", "max_dev_direction",
            "n_celdas", "n_sobre", "n_sub", "n_exacto", "share_sobre",
        )
        for k in required:
            assert k in s, f"Clave faltante: {k}"

    def test_exact_allocation_zeros(self):
        Q = self._q()
        s = fair_share_summary(N_EXACT, Q, label="exact")
        assert s["l1"] == pytest.approx(0.0, abs=1e-9)
        assert s["l2"] == pytest.approx(0.0, abs=1e-9)
        assert s["max_dev"] == pytest.approx(0.0, abs=1e-9)
        assert s["n_sobre"] == 0
        assert s["n_sub"] == 0
        assert s["n_exacto"] == 4

    def test_distorted_l1_correct(self):
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        assert s["l1"] == pytest.approx(4.0, abs=1e-9)

    def test_distorted_l2_correct(self):
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        assert s["l2"] == pytest.approx(2.0, abs=1e-9)

    def test_l1_norm_in_range(self):
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        assert 0.0 <= s["l1_norm"] <= 2.0

    def test_label_propagates(self):
        Q = self._q()
        s = fair_share_summary(N_EXACT, Q, label="mi_plan")
        assert s["plan"] == "mi_plan"

    def test_n_celdas_correct(self):
        Q = self._q()
        s = fair_share_summary(N_EXACT, Q)
        assert s["n_celdas"] == 4  # 2 partidos × 2 distritos

    def test_sobre_sub_exacto_sum_to_n_celdas(self):
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        assert s["n_sobre"] + s["n_sub"] + s["n_exacto"] == s["n_celdas"]

    def test_share_sobre_in_unit_interval(self):
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        assert 0.0 <= s["share_sobre"] <= 1.0

    def test_rmse_equals_l2_normalized(self):
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        expected_rmse = s["l2"] / np.sqrt(s["n_celdas"])
        assert s["rmse"] == pytest.approx(expected_rmse, rel=1e-6)

    def test_consistent_with_individual_functions(self):
        """Los escalares coinciden con las funciones individuales."""
        Q = self._q()
        s = fair_share_summary(N_DISTORTED, Q)
        assert s["l1"]      == pytest.approx(l1_distance_fair_share(N_DISTORTED, Q), rel=1e-9)
        assert s["l2"]      == pytest.approx(l2_distance_fair_share(N_DISTORTED, Q), rel=1e-9)
        assert s["max_dev"] == pytest.approx(max_cell_deviation(N_DISTORTED, Q)["max_dev"], rel=1e-9)


# ─── integración con chiledist público ───────────────────────────────────────

class TestPublicAPIIntegration:

    def test_importable_from_chiledist(self):
        import chiledist as cd
        assert hasattr(cd, "fair_share_matrix")
        assert hasattr(cd, "results_to_matrix")
        assert hasattr(cd, "l1_distance_fair_share")
        assert hasattr(cd, "l2_distance_fair_share")
        assert hasattr(cd, "max_cell_deviation")
        assert hasattr(cd, "fair_share_summary")

    def test_run_electoral_plan_to_fair_share_workflow(self):
        """Flujo completo: aggregate_votes → run_electoral_plan → fair_share_summary."""
        import chiledist as cd
        import chiledist.fairshare as fs

        # Datos sintéticos
        votes_long = pd.DataFrame({
            "CUT":     [1, 1, 2, 2],
            "partido": ["A", "B", "A", "B"],
            "votos":   [600, 400, 200, 800],
        })
        assignment  = {1: 10, 2: 20}  # CUT 1 → distrito 10, CUT 2 → distrito 20
        magnitudes  = pd.Series({10: 5, 20: 5})

        votes_by_dist = cd.aggregate_votes(votes_long, assignment, unit_col="CUT")
        results       = cd.run_electoral_plan(votes_by_dist, magnitudes)
        N             = fs.results_to_matrix(results)
        Q             = fs.fair_share_matrix(votes_by_dist, magnitudes)
        summary       = fs.fair_share_summary(N, Q, label="test_plan")

        assert isinstance(summary, dict)
        assert summary["l1"] >= 0.0
        assert summary["plan"] == "test_plan"
