"""
tests/test_cut_normalization.py
=================================
Regression tests for the CUT format-mismatch bug: some sources represent a
Chilean commune code (CUT) as an unpadded 4-digit value (region 1-9
communes, e.g. 1101) while others use a zero-padded 5-digit string
("01101"). `chiledist.data.census2024.load_census2024()` always returns
CUT as int, so `str(1101) == "1101"` — which never matches the 5-digit
string keys used by `datos/asignacion_vigente.json`
(README.md § Datos externos documents the 5-digit convention there).

Before the fix, `scripts/malapportionment.py::_load_population` and
`scripts/electoral_analysis.py::_load_population` did a naive
`census["CUT"].astype(str)` (no zero-padding) before looking values up in
the zero-padded assignment dict. On the real repo data
(datos/poblacion_comunal_censo2024.csv + datos/asignacion_vigente.json)
this silently dropped population for every region 1-9 commune: 206/346
communes missed, total population undercounted from 18,480,432 to
9,713,395 — with no error or warning.

The fix (chiledist.normalize_cut, chiledist/hierarchy.py) makes CUT
comparable regardless of whether the source used 4 or 5 digits, an int, or
a string — nobody needs to decide which length is "correct". These tests
confirm the join is not lossy any more, without pinning down a single
"correct" CUT width anywhere.
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

import chiledist as cd

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _import_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(SCRIPTS_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── chiledist.normalize_cut ────────────────────────────────────────────────

class TestNormalizeCut:

    def test_int_unpadded(self):
        assert cd.normalize_cut(1101) == "01101"

    def test_str_unpadded(self):
        assert cd.normalize_cut("1101") == "01101"

    def test_str_already_padded(self):
        assert cd.normalize_cut("01101") == "01101"

    def test_int_already_five_digits(self):
        assert cd.normalize_cut(13101) == "13101"

    def test_float_input(self):
        """CSV columns read with pandas sometimes come back as float64."""
        assert cd.normalize_cut(1101.0) == "01101"

    def test_two_digit_region_needs_no_padding(self):
        assert cd.normalize_cut(13101) == cd.normalize_cut("13101")

    def test_all_representations_of_same_commune_are_equal(self):
        normalized = {cd.normalize_cut(r) for r in [1101, "1101", "01101", 1101.0]}
        assert normalized == {"01101"}


# ─── scripts/malapportionment.py ────────────────────────────────────────────

class TestMalapportionmentCutJoin:

    @pytest.fixture(scope="module")
    def mod(self):
        return _import_script("malapportionment.py", "malapportionment_cut_test")

    def test_load_assignment_normalizes_mixed_length_keys(self, mod, tmp_path):
        """The JSON itself might have 4-digit keys for some entries — the
        loaded dict must always expose canonical 5-digit keys regardless."""
        path = tmp_path / "assignment.json"
        path.write_text(json.dumps({"1101": 1, "01107": 1, "13101": 10}))
        assignment = mod._load_assignment(str(path))
        assert set(assignment.keys()) == {"01101", "01107", "13101"}

    def test_load_population_no_silent_loss_across_padding_mismatch(self, mod, tmp_path):
        """
        Reproduces the exact bug: census CUT arrives unpadded (int, per
        load_census2024's contract), assignment keys are zero-padded
        strings (per asignacion_vigente.json's contract). Population must
        not be silently dropped for the communes needing the leading zero.
        """
        census_csv = tmp_path / "census.csv"
        census_csv.write_text(
            "CUT,personas\n"
            "1101,100000\n"   # region 1 -> needs zero-padding
            "1107,50000\n"
            "13101,200000\n"  # region 13 -> already 5 digits either way
        )
        assignment_json = tmp_path / "assignment.json"
        assignment_json.write_text(json.dumps({
            "01101": 1, "01107": 1, "13101": 10,
        }))

        assignment = mod._load_assignment(str(assignment_json))
        pop = mod._load_population(str(census_csv), assignment)

        assert pop is not None
        assert pop.sum() == 350_000, "no population should be lost to a padding mismatch"
        assert pop.loc[1] == 150_000
        assert pop.loc[10] == 200_000

    def test_analisis_electoral_matches_votes_to_real_assignment(self, mod):
        """
        analisis_electoral() used to cast votes_df["CUT"] to
        type(list(assignment.keys())[0]) — a dtype-only cast that produces
        "1101" (unpadded) when assignment keys are already str, still
        missing the zero-padded "01101" key. Confirm votes now aggregate
        correctly against a real-looking (zero-padded) assignment.
        """
        assignment = {"01101": 1, "13101": 10}
        votes_df = pd.DataFrame({
            "CUT":     [1101, 1101, 13101],
            "partido": ["A", "B", "A"],
            "votos":   [100, 50, 300],
        })
        # pop_by_unit indexed by the SAME keys as `assignment` (CUT), not
        # by district — see TestPopByUnitIndexing below for the dedicated
        # regression test on that distinct bug.
        pop_by_unit = pd.Series({"01101": 100_000, "13101": 200_000})

        result = mod.analisis_electoral(assignment, votes_df, pop_by_unit, pacto_map=None)
        assert not result.empty
        # analisis_electoral() returns one row per metric (columns: metrica,
        # fijas, calculadas, delta). If the CUT join had failed,
        # plan_electoral_metrics would see zero votes for every district
        # and escanos_mayor_partido would come back 0 in both modes.
        row = result.set_index("metrica").loc["escanos_mayor_partido"]
        assert row["fijas"] > 0
        assert row["calculadas"] > 0

    def test_analisis_electoral_demo_mode_still_works(self, mod):
        """
        In --demo mode, assignment is the trivial identity {d: d for d in
        1..28} (ints) and votes_df["CUT"] holds the same district numbers
        as ints — the fix must not touch `assignment` when its keys are
        already ints, so this pre-existing, already-consistent case (and
        the pop_by_unit lookup that depends on assignment's keys staying
        as district numbers) keeps working exactly as before.
        """
        pop, assignment, votes_df = mod._demo_data()
        result = mod.analisis_electoral(assignment, votes_df, pop, pacto_map=None)
        row = result.set_index("metrica").loc["escanos_mayor_partido"]
        assert row["fijas"] > 0
        assert row["calculadas"] > 0


# ─── scripts/electoral_analysis.py ──────────────────────────────────────────

class TestElectoralAnalysisCutJoin:

    @pytest.fixture(scope="module")
    def mod(self):
        return _import_script("electoral_analysis.py", "electoral_analysis_cut_test")

    def test_load_assignment_normalizes_mixed_length_keys(self, mod, tmp_path):
        path = tmp_path / "assignment.json"
        path.write_text(json.dumps({"1101": 1, "13101": 10}))
        assignment = mod._load_assignment(str(path))
        assert set(assignment.keys()) == {"01101", "13101"}

    def test_load_population_no_silent_loss_across_padding_mismatch(self, mod, tmp_path):
        census_csv = tmp_path / "census.csv"
        census_csv.write_text(
            "CUT,personas\n"
            "1101,100000\n"
            "13101,200000\n"
        )
        assignment_json = tmp_path / "assignment.json"
        assignment_json.write_text(json.dumps({"01101": 1, "13101": 10}))

        assignment = mod._load_assignment(str(assignment_json))
        pop = mod._load_population(str(census_csv), assignment)

        assert pop is not None
        assert pop.sum() == 300_000
        assert pop.loc[1] == 100_000

    def test_load_votes_normalizes_cut_for_aggregate_votes(self, mod, tmp_path):
        """
        _load_votes() must return a CUT column that matches the zero-padded
        assignment keys, so cd.aggregate_votes()'s internal
        `.map(assignment)` doesn't silently drop every region 1-9 row.
        """
        servel_csv = tmp_path / "servel.csv"
        servel_csv.write_text(
            "CUT,partido,votos\n"
            "1101,A,100\n"
            "1101,B,50\n"
            "13101,A,300\n"
        )
        votes_df = mod._load_votes(str(servel_csv))
        assert votes_df is not None
        assert set(votes_df["CUT"]) == {"01101", "13101"}

        assignment = {"01101": 1, "13101": 10}
        agg = cd.aggregate_votes(votes_df, assignment, unit_col="CUT")
        # Nothing should be dropped: 3 (partido, distrito) rows go in,
        # 3 come out (A/dist1, B/dist1, A/dist10).
        assert agg["votos"].sum() == 450


# ─── End-to-end regression against the real repo data ──────────────────────

class TestRealRepoDataRegression:
    """
    Reproduces the exact incident on the real files shipped in datos/, to
    guard against regressing the specific bug that was reported and fixed.
    Skips gracefully if those files aren't present in this checkout.
    """

    CENSUS_PATH = Path("datos/poblacion_comunal_censo2024.csv")
    ASSIGNMENT_PATH = Path("datos/asignacion_vigente.json")

    @classmethod
    @pytest.fixture(scope="class")
    def mod(cls):
        return _import_script("malapportionment.py", "malapportionment_real_data_test")

    def test_real_data_join_is_not_lossy(self, mod):
        if not (self.CENSUS_PATH.exists() and self.ASSIGNMENT_PATH.exists()):
            pytest.skip("datos/poblacion_comunal_censo2024.csv or "
                        "datos/asignacion_vigente.json not present in this checkout")

        assignment = mod._load_assignment(str(self.ASSIGNMENT_PATH))
        pop = mod._load_population(str(self.CENSUS_PATH), assignment)

        with open(self.ASSIGNMENT_PATH, encoding="utf-8") as f:
            raw_assignment = json.load(f)
        census_total = pd.read_csv(self.CENSUS_PATH)["personas"].sum()

        assert len(raw_assignment) == 346
        assert pop.sum() == census_total, (
            "population aggregated by circunscripción must equal the "
            "census total — any gap means the CUT join is dropping communes"
        )
        assert (pop > 0).all(), "no circunscripción should end up with zero population"
