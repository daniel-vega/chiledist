"""
tests/test_analisis_electoral_pop_by_unit.py
==============================================
Regression tests for a distinct, pre-existing bug in
scripts/malapportionment.py::analisis_electoral() (A4), found while fixing
the unrelated CUT-padding bug (see tests/test_cut_normalization.py) but
not caused by it.

`chiledist.electoral.plan_metrics.plan_electoral_metrics()` expects
`pop_by_unit` indexed by the SAME keys as `assignment` (unit_id — CUT in
real mode), because it does its own internal aggregation to district
level via `assignment.items()`:

    pop_map = pop_by_unit.to_dict()
    pop_by_d = {d: sum(pop_map.get(u, 0) for u, dd in assignment.items()
                        if dd == d) for d in set(assignment.values())}

Before the fix, `main()` passed `pop_por_distrito` — the output of
`_load_population()`, already aggregated to DISTRICT level (1-28) — into
`analisis_electoral()` as if it were `pop_by_unit`. In real (non-demo)
mode, `assignment` keys are CUT strings, so `pop_map.get(u, 0)` always
missed (district-number keys != CUT keys) and every malapportionment
metric derived from `pop_by_d` (pxe_max, pxe_min, ratio_max_min_pxe,
peso_relativo_max/min) silently came back 0 or NaN — with A1's
independently-computed pxe/peso_relativo numbers (which use
`personas_por_escano()`/`peso_relativo_del_voto()` directly, not through
`plan_electoral_metrics()`) staying correct the whole time, making the
discrepancy easy to miss.

In --demo mode this never showed up because `_demo_data()` uses a trivial
identity assignment (`{d: d for d in range(1, 29)}`) — unit IS the
district number there, so a district-indexed Series happened to also be a
valid unit-indexed Series by coincidence.

The fix adds `_load_population_by_unit()` (population indexed by CUT,
not aggregated to district) and threads it into `analisis_electoral()`,
leaving `_load_population()`/`pop_por_distrito` untouched for A1-A3, which
genuinely need district-level population.
"""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _import_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(SCRIPTS_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _import_script("malapportionment.py", "malapportionment_pop_by_unit_test")


def _metric(df: pd.DataFrame, name: str) -> pd.Series:
    return df.set_index("metrica").loc[name]


class TestLoadPopulationByUnit:

    def test_returns_series_indexed_by_normalized_cut(self, mod, tmp_path):
        census_csv = tmp_path / "census.csv"
        census_csv.write_text(
            "CUT,personas\n"
            "1101,100000\n"   # unpadded -> must normalize to "01101"
            "13101,200000\n"
        )
        pop_by_unit = mod._load_population_by_unit(str(census_csv))
        assert pop_by_unit is not None
        assert set(pop_by_unit.index) == {"01101", "13101"}
        assert pop_by_unit.loc["01101"] == 100_000
        assert pop_by_unit.loc["13101"] == 200_000

    def test_does_not_aggregate_to_district(self, mod, tmp_path):
        """Unlike _load_population(), this must NOT need or use `assignment`
        at all — it's unit-level population, period."""
        census_csv = tmp_path / "census.csv"
        census_csv.write_text("CUT,personas\n1101,100000\n1107,50000\n")
        pop_by_unit = mod._load_population_by_unit(str(census_csv))
        # Two distinct communes stay two distinct rows -- no aggregation.
        assert len(pop_by_unit) == 2


class TestAnalisisElectoralPopByUnit:

    def test_malapportionment_metrics_are_not_degenerate_with_unit_level_pop(self, mod):
        """
        The core regression: pop_by_unit indexed by CUT (matching
        `assignment`'s keys) must let plan_electoral_metrics() compute
        real pxe/peso_relativo numbers, not 0/NaN.
        """
        assignment = {"01101": 1, "13101": 10}
        votes_df = pd.DataFrame({
            "CUT":     ["01101", "01101", "13101", "13101"],
            "partido": ["A", "B", "A", "B"],
            "votos":   [600, 400, 900, 100],
        })
        pop_by_unit = pd.Series({"01101": 100_000, "13101": 200_000})

        result = mod.analisis_electoral(assignment, votes_df, pop_by_unit, pacto_map=None)

        pxe_max = _metric(result, "pxe_max")
        pxe_min = _metric(result, "pxe_min")
        ratio   = _metric(result, "ratio_max_min_pxe")
        peso_max = _metric(result, "peso_relativo_max")

        for mode in ("fijas", "calculadas"):
            assert pxe_max[mode] > 0, f"pxe_max degenerate in modo={mode}"
            assert pxe_min[mode] > 0, f"pxe_min degenerate in modo={mode}"
            assert ratio[mode] > 0 and pd.notna(ratio[mode]), \
                f"ratio_max_min_pxe degenerate (0/NaN) in modo={mode}"
            assert peso_max[mode] > 0

    def test_district_indexed_pop_reproduces_the_original_bug(self, mod):
        """
        Documents the failure mode this fix closes: passing population
        indexed by DISTRICT (what _load_population() returns) instead of
        by unit/CUT makes the malapportionment metrics come back
        degenerate, because plan_electoral_metrics()'s internal lookup
        keys never match `assignment`'s CUT keys.
        """
        assignment = {"01101": 1, "13101": 10}
        votes_df = pd.DataFrame({
            "CUT":     ["01101", "01101", "13101", "13101"],
            "partido": ["A", "B", "A", "B"],
            "votos":   [600, 400, 900, 100],
        })
        pop_by_district = pd.Series({1: 100_000, 10: 200_000})  # wrong index space

        result = mod.analisis_electoral(assignment, votes_df, pop_by_district, pacto_map=None)
        pxe_max = _metric(result, "pxe_max")
        assert (pxe_max.fillna(0) == 0).all(), (
            "this test documents the pre-fix failure mode — if it starts "
            "failing, plan_electoral_metrics()'s pop_by_unit contract changed"
        )

    def test_demo_mode_unaffected(self, mod):
        """
        In --demo mode, unit == district (trivial identity assignment), so
        the district-indexed population from _demo_data() IS already a
        valid pop_by_unit — this must keep working exactly as before.
        """
        pop, assignment, votes_df = mod._demo_data()
        result = mod.analisis_electoral(assignment, votes_df, pop, pacto_map=None)
        ratio = _metric(result, "ratio_max_min_pxe")
        assert (ratio > 0).all()
        assert ratio.notna().all()


class TestRealRepoDataPopByUnitRegression:
    """
    End-to-end regression against the real files shipped in datos/: A4's
    pxe/peso_relativo numbers (via plan_electoral_metrics, modo "fijas")
    must agree with A1's independently-computed personas_por_escano() /
    peso_relativo_del_voto() numbers, since both describe the same vigente
    map under the same fixed magnitudes. Skips gracefully if the files
    aren't present in this checkout.
    """

    CENSUS_PATH = Path("datos/poblacion_comunal_censo2024.csv")
    ASSIGNMENT_PATH = Path("datos/asignacion_vigente.json")

    @classmethod
    @pytest.fixture(scope="class")
    def mod(cls):
        return _import_script("malapportionment.py", "malapportionment_real_pop_by_unit_test")

    def test_a4_fijas_pxe_matches_a1(self, mod):
        if not (self.CENSUS_PATH.exists() and self.ASSIGNMENT_PATH.exists()):
            pytest.skip("datos/poblacion_comunal_censo2024.csv or "
                        "datos/asignacion_vigente.json not present in this checkout")

        import chiledist as cd

        assignment = mod._load_assignment(str(self.ASSIGNMENT_PATH))
        pop_por_distrito = mod._load_population(str(self.CENSUS_PATH), assignment)
        pop_by_unit = mod._load_population_by_unit(str(self.CENSUS_PATH))

        magnitudes = pd.Series(
            {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
             if k in set(assignment.values())}
        )
        pop_por_distrito = pop_por_distrito.reindex(magnitudes.index, fill_value=0)

        # A1's own computation (independent of plan_electoral_metrics).
        pxe_a1 = cd.personas_por_escano(pop_por_distrito, magnitudes)

        # A4, modo "fijas" — every commune has real (non-uniform) votes so
        # D'Hondt/gallagher don't degenerate; only pxe/peso_relativo are
        # under test here.
        votes_df = pd.DataFrame({
            "CUT":     list(assignment.keys()),
            "partido": ["A"] * len(assignment),
            "votos":   [100] * len(assignment),
        })
        result = mod.analisis_electoral(assignment, votes_df, pop_by_unit, pacto_map=None)

        pxe_max_a4 = _metric(result, "pxe_max")["fijas"]
        pxe_min_a4 = _metric(result, "pxe_min")["fijas"]

        # plan_electoral_metrics() rounds pxe to whole persons; allow <1
        # person of rounding slack rather than pin an exact float match.
        assert pxe_max_a4 == pytest.approx(pxe_a1.max(), abs=1)
        assert pxe_min_a4 == pytest.approx(pxe_a1.min(), abs=1)
