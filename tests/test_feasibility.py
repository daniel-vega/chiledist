"""
tests/test_feasibility.py
==========================
Unit tests for the deterministic population feasibility preflight
(chiledist.feasibility.check_population_feasibility).
"""

import pytest

from chiledist.feasibility import (
    PopulationFeasibilityResult,
    REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND,
    check_population_feasibility,
)


class TestCheckPopulationFeasibility:

    def test_feasible_case(self):
        """4 units of 100 each, 4 districts, ±5% tolerance: trivially feasible."""
        result = check_population_feasibility(
            {"U1": 100, "U2": 100, "U3": 100, "U4": 100},
            n_districts=4,
            pop_tolerance=0.05,
        )
        assert isinstance(result, PopulationFeasibilityResult)
        assert result.feasible is True
        assert result.total_population == pytest.approx(400.0)
        assert result.ideal_population == pytest.approx(100.0)
        assert result.minimum_required_tolerance == pytest.approx(0.0)
        assert result.largest_indivisible_unit_id in {"U1", "U2", "U3", "U4"}
        assert result.reason is None

    def test_exact_boundary_is_feasible(self):
        """
        min_required_tolerance == pop_tolerance exactly must count as
        feasible (criterion is strict '>' for infeasibility, so equality
        is the inclusive boundary).

        Uses values exactly representable in binary floating point
        (quarters) so the equality check isn't confounded by rounding:
        ideal = 400/4 = 100; largest unit = 125 -> required = 125/100 - 1
        = 0.25 exactly, matching pop_tolerance=0.25 exactly.
        """
        result = check_population_feasibility(
            {"U1": 125, "U2": 100, "U3": 100, "U4": 75},
            n_districts=4,
            pop_tolerance=0.25,
        )
        assert result.minimum_required_tolerance == 0.25
        assert result.feasible is True
        assert result.reason is None

    def test_infeasible_case(self):
        """One unit with 90% of total population makes n_districts=4 impossible under ±5%."""
        result = check_population_feasibility(
            {"U1": 900, "U2": 33, "U3": 33, "U4": 34},
            n_districts=4,
            pop_tolerance=0.05,
        )
        assert result.feasible is False
        assert result.reason == REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND
        assert result.largest_indivisible_unit_id == "U1"
        assert result.largest_indivisible_unit == pytest.approx(900.0)
        assert result.minimum_required_tolerance > result.requested_tolerance
        assert "inviable" in result.diagnostic_message().lower()

    def test_rm_santiago_reproduction(self):
        """
        Reproduces the real RM scenario: decision_unit=CUT, n_distritos=8,
        total_pop=267629, with CUT 13101 (Santiago) = 66697.

        ideal_pop = 267629 / 8 = 33453.625
        min_required_tolerance = 66697 / 33453.625 - 1 ~= 0.9937
        Requested pop_tolerance = 0.05 -> structurally infeasible.
        """
        total_pop = 267629
        santiago_pop = 66697
        other_pop = total_pop - santiago_pop
        # Split the remaining population across several other comunas so
        # none individually exceeds Santiago's — mirrors the real RM data,
        # where Santiago (13101) is the single largest comuna even though
        # the *sum* of all others is naturally bigger than any one of them.
        n_other = 5
        base_share = other_pop // n_other
        unit_populations = {
            f"OTHER_CUT_{i}": base_share for i in range(n_other - 1)
        }
        unit_populations["13101"] = santiago_pop
        unit_populations[f"OTHER_CUT_{n_other - 1}"] = (
            other_pop - base_share * (n_other - 1)
        )

        result = check_population_feasibility(
            unit_populations, n_districts=8, pop_tolerance=0.05
        )

        assert result.feasible is False
        assert result.reason == REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND
        assert result.total_population == pytest.approx(267629)
        assert result.ideal_population == pytest.approx(33453.625)
        assert result.largest_indivisible_unit_id == "13101"
        assert result.largest_indivisible_unit == pytest.approx(66697)
        assert result.minimum_required_tolerance == pytest.approx(0.9937, abs=1e-4)
        assert result.requested_tolerance == pytest.approx(0.05)

    def test_diagnostic_message_mentions_no_amount_of_seeds(self):
        """The diagnostic must make clear that seeds/init attempts can't fix this."""
        result = check_population_feasibility(
            {"U1": 900, "U2": 100}, n_districts=4, pop_tolerance=0.05
        )
        msg = result.diagnostic_message().lower()
        assert "semillas" in msg or "inicializaci" in msg

    def test_empty_unit_populations_raises(self):
        with pytest.raises(ValueError):
            check_population_feasibility({}, n_districts=4, pop_tolerance=0.05)

    def test_zero_districts_raises(self):
        with pytest.raises(ValueError):
            check_population_feasibility(
                {"U1": 100}, n_districts=0, pop_tolerance=0.05
            )

    def test_as_dict_contains_required_fields(self):
        result = check_population_feasibility(
            {"U1": 900, "U2": 100}, n_districts=4, pop_tolerance=0.05
        )
        d = result.as_dict()
        for key in (
            "feasible", "reason", "total_population", "n_districts",
            "ideal_population", "largest_indivisible_unit",
            "largest_indivisible_unit_id", "minimum_required_tolerance",
            "requested_tolerance",
        ):
            assert key in d
