"""
tests/test_malapportionment_functions.py
=========================================
Unit tests for malapportionment functions:
    personas_por_escano, peso_relativo_del_voto, comparar_magnitudes

No external data or gerrychain required.
"""

import numpy as np
import pandas as pd
import pytest

from chiledist.electoral import (
    MAGNITUDES_LEGALES_LEY20840,
    TOTAL_ESCANOS_CAMARA,
)
from chiledist.engines.allocation import comparar_magnitudes
from chiledist.evaluation import (
    personas_por_escano,
    peso_relativo_del_voto,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

# 2-district case with 9:1 population inequality
POP_2  = pd.Series({1: 900_000, 2: 100_000})
MAG_EQ = pd.Series({1: 5, 2: 5})     # equal magnitudes → max malapportionment
MAG_PR = pd.Series({1: 9, 2: 1})     # proportional magnitudes


# ─── personas_por_escano ──────────────────────────────────────────────────────

class TestPersonasPorEscano:

    def test_basic_values(self):
        pxe = personas_por_escano(POP_2, MAG_EQ)
        assert pxe[1] == pytest.approx(180_000.0)
        assert pxe[2] == pytest.approx(20_000.0)

    def test_proportional_magnitudes_equal_pxe(self):
        """With proportional magnitudes, pxe should be equal across districts."""
        pxe = personas_por_escano(POP_2, MAG_PR)
        assert pxe[1] == pytest.approx(pxe[2], rel=0.01)

    def test_returns_series(self):
        pxe = personas_por_escano(POP_2, MAG_EQ)
        assert isinstance(pxe, pd.Series)

    def test_missing_index_intersection(self):
        """Districts not shared between pop and magnitudes are dropped."""
        pop = pd.Series({1: 500_000, 3: 300_000})  # district 3 absent in MAG_EQ
        pxe = personas_por_escano(pop, MAG_EQ)
        assert 3 not in pxe.index
        assert 1 in pxe.index

    def test_zero_magnitude_becomes_nan(self):
        """Zero magnitude produces NaN, not ZeroDivisionError."""
        pop = pd.Series({1: 500_000})
        mag = pd.Series({1: 0})
        pxe = personas_por_escano(pop, mag)
        assert np.isnan(pxe[1])

    def test_single_district(self):
        pop = pd.Series({1: 1_000_000})
        mag = pd.Series({1: 4})
        pxe = personas_por_escano(pop, mag)
        assert pxe[1] == pytest.approx(250_000.0)

    def test_equal_population_all_same_pxe(self):
        pop = pd.Series({1: 300_000, 2: 300_000, 3: 300_000})
        mag = pd.Series({1: 5, 2: 5, 3: 5})
        pxe = personas_por_escano(pop, mag)
        vals = pxe.values
        assert vals[0] == pytest.approx(vals[1], rel=0.01)
        assert vals[0] == pytest.approx(vals[2], rel=0.01)


# ─── peso_relativo_del_voto ───────────────────────────────────────────────────

class TestPesoRelativoDelVoto:

    def test_values_with_equal_magnitudes(self):
        """
        POP_2 = {1: 900k, 2: 100k}, MAG_EQ = {1: 5, 2: 5}.
        media_nacional = 1_000_000 / 10 = 100_000 per seat.
        D1: pxe = 180_000 → peso = 180_000/100_000 = 1.8
        D2: pxe = 20_000  → peso = 20_000/100_000  = 0.2
        """
        prv = peso_relativo_del_voto(POP_2, MAG_EQ)
        assert prv[1] == pytest.approx(1.8, rel=0.01)
        assert prv[2] == pytest.approx(0.2, rel=0.01)

    def test_proportional_magnitudes_all_one(self):
        """Perfectly proportional magnitudes → all weights = 1.0."""
        prv = peso_relativo_del_voto(POP_2, MAG_PR)
        for val in prv.values:
            assert val == pytest.approx(1.0, rel=0.01)

    def test_equal_districts_all_one(self):
        """Identical districts → peso = 1.0 everywhere."""
        pop = pd.Series({1: 300_000, 2: 300_000, 3: 300_000})
        mag = pd.Series({1: 5, 2: 5, 3: 5})
        prv = peso_relativo_del_voto(pop, mag)
        assert all(v == pytest.approx(1.0, rel=0.01) for v in prv.values)

    def test_returns_series(self):
        prv = peso_relativo_del_voto(POP_2, MAG_EQ)
        assert isinstance(prv, pd.Series)

    def test_zero_magnitude_produces_nan(self):
        pop = pd.Series({1: 500_000})
        mag = pd.Series({1: 0})
        prv = peso_relativo_del_voto(pop, mag)
        assert np.isnan(prv.iloc[0])

    def test_underrepresented_vote_has_peso_gt_one(self):
        """Large district with few seats → vote worth less (peso > 1.0)."""
        prv = peso_relativo_del_voto(POP_2, MAG_EQ)
        assert prv[1] > 1.0  # D1: 900k pop, 5 seats → underrepresented

    def test_overrepresented_vote_has_peso_lt_one(self):
        """Small district with many seats relative to pop → vote worth more (peso < 1.0)."""
        prv = peso_relativo_del_voto(POP_2, MAG_EQ)
        assert prv[2] < 1.0  # D2: 100k pop, 5 seats → overrepresented


# ─── comparar_magnitudes ──────────────────────────────────────────────────────

class TestCompararMagnitudes:

    def test_returns_dataframe(self):
        df = comparar_magnitudes(POP_2, MAG_EQ, total_seats=10, min_seats=1, max_seats=9)
        assert isinstance(df, pd.DataFrame)

    def test_required_columns(self):
        df = comparar_magnitudes(POP_2, MAG_EQ, total_seats=10, min_seats=1, max_seats=9)
        for col in ("distrito", "magnitud_vigente", "magnitud_nueva",
                    "delta", "pop_vigente_pxe", "pop_nueva_pxe"):
            assert col in df.columns, f"Missing column: {col}"

    def test_delta_sign_with_severe_inequality(self):
        """
        With POP_2 = {1: 900k, 2: 100k} and MAG_EQ = {1: 5, 2: 5}:
        recalculation should give D1 more seats (positive delta) and D2 fewer.
        """
        df = comparar_magnitudes(POP_2, MAG_EQ, total_seats=10, min_seats=1, max_seats=9)
        d1 = df[df["distrito"] == 1].iloc[0]
        d2 = df[df["distrito"] == 2].iloc[0]
        assert d1["delta"] > 0, "D1 (large pop) should gain seats"
        assert d2["delta"] < 0, "D2 (small pop) should lose seats"

    def test_total_seats_conserved(self):
        df = comparar_magnitudes(POP_2, MAG_EQ, total_seats=10, min_seats=1, max_seats=9)
        assert df["magnitud_nueva"].sum() == 10

    def test_vigente_seats_unchanged(self):
        """magnitud_vigente column should match the input exactly."""
        df = comparar_magnitudes(POP_2, MAG_EQ, total_seats=10, min_seats=1, max_seats=9)
        vigente = df.set_index("distrito")["magnitud_vigente"]
        assert vigente[1] == 5
        assert vigente[2] == 5

    def test_new_pxe_more_equal(self):
        """New magnitudes reduce malapportionment: max/min ratio decreases."""
        df = comparar_magnitudes(POP_2, MAG_EQ, total_seats=10, min_seats=1, max_seats=9)
        pxe_vig = df["pop_vigente_pxe"].astype(float)
        pxe_new = df["pop_nueva_pxe"].astype(float)
        ratio_vig = pxe_vig.max() / pxe_vig.min()
        ratio_new = pxe_new.max() / pxe_new.min()
        assert ratio_new < ratio_vig, "New magnitudes should reduce pxe inequality"

    def test_accepts_dict_input(self):
        """magnitudes_vigentes can be a plain dict."""
        df = comparar_magnitudes(POP_2, {1: 5, 2: 5}, total_seats=10,
                                 min_seats=1, max_seats=9)
        assert len(df) == 2

    def test_ley20840_all_28_districts(self):
        """MAGNITUDES_LEGALES_LEY20840 produces one row per district."""
        pop28 = pd.Series({k: 500_000 + k * 30_000 for k in range(1, 29)})
        df = comparar_magnitudes(
            pop28, MAGNITUDES_LEGALES_LEY20840,
            total_seats=TOTAL_ESCANOS_CAMARA,
            min_seats=3, max_seats=8,
        )
        assert len(df) == 28
        assert df["magnitud_nueva"].sum() == TOTAL_ESCANOS_CAMARA

    def test_proportional_population_zero_delta(self):
        """If current pop is proportional to vigente magnitudes, delta ≈ 0."""
        mag_vig = pd.Series({1: 8, 2: 2})             # 4:1 ratio
        pop_prop = pd.Series({1: 800_000, 2: 200_000}) # 4:1 ratio (proportional)
        df = comparar_magnitudes(pop_prop, mag_vig, total_seats=10,
                                 min_seats=1, max_seats=9)
        # With proportional pop, the new allocation matches the old one
        for _, row in df.iterrows():
            assert abs(row["delta"]) <= 1, "Delta should be 0 or ±1 for proportional input"
