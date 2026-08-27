"""
tests/test_redistritaje_status.py
===================================
Tests for the distinction between "infeasible_population" (a mathematical
proof, from chiledist.check_population_feasibility) and "sin_particion"
(an exhausted initialization search) in scripts/redistritaje.py.

scripts/redistritaje.py is not a package module, so it's loaded directly
from its file path via importlib, the same pattern used by
tests/test_scripts_demo.py for run_chains.py.
"""

import importlib.util
import os
import re

import pytest

import chiledist as cd
from chiledist.rules.feasibility import REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND


def _import_redistritaje():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(root, "scripts", "redistritaje.py")
    spec = importlib.util.spec_from_file_location("redistritaje", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def redistritaje():
    return _import_redistritaje()


# ─── Preflight: infeasible_population ──────────────────────────────────────

class TestInfeasiblePopulation:

    def test_infeasible_preflight_carries_reason(self):
        """
        Reproduces the RM/Santiago scenario: preflight must report
        feasible=False with the stable reason
        'indivisible_unit_exceeds_population_bound'.
        """
        total_pop = 267629
        santiago_pop = 66697
        other_pop = total_pop - santiago_pop
        n_other = 5
        base_share = other_pop // n_other
        unit_populations = {
            f"OTHER_CUT_{i}": base_share for i in range(n_other - 1)
        }
        unit_populations["13101"] = santiago_pop
        unit_populations[f"OTHER_CUT_{n_other - 1}"] = (
            other_pop - base_share * (n_other - 1)
        )

        result = cd.check_population_feasibility(
            unit_populations, n_districts=8, pop_tolerance=0.05
        )
        assert result.feasible is False
        assert result.reason == REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND
        assert result.reason == "indivisible_unit_exceeds_population_bound"

    def test_feasible_preflight_has_no_reason(self):
        result = cd.check_population_feasibility(
            {"U1": 100, "U2": 100}, n_districts=2, pop_tolerance=0.05
        )
        assert result.feasible is True
        assert result.reason is None


# ─── buscar_particion_inicial: search exhaustion vs. success ───────────────

class _FakeGraph:
    """Minimal stand-in for a gerrychain Graph: only .nodes[node].get(col) is used."""

    def __init__(self, pops):
        self.nodes = {i: {"pop": p} for i, p in enumerate(pops)}


class TestBuscarParticionInicial:

    def test_success_returns_assignment_without_exhausting_ladder(self, redistritaje):
        """A recursive_tree_part that succeeds immediately should return a
        non-None assignment and not need to try every tolerance/seed."""
        calls = []

        def fake_recursive_tree_part(graph, parts, pop_target, pop_col,
                                      epsilon, node_repeats):
            calls.append(epsilon)
            # 4 nodes of pop 100 each, perfectly split into 2 parts of 2 nodes
            return {0: 0, 1: 0, 2: 1, 3: 1}

        graph = _FakeGraph([100, 100, 100, 100])
        best_assignment, best_dev, best_tol = redistritaje.buscar_particion_inicial(
            graph, n_distritos_eff=2, pop_col="pop", ideal_pop=200,
            node_repeats=10, seed=42,
            recursive_tree_part=fake_recursive_tree_part,
        )

        assert best_assignment is not None
        assert best_dev == pytest.approx(0.0)
        assert best_tol == redistritaje.TOLERANCIA_INICIAL_ESCALERA[0]
        # Broke out after the first successful (well-balanced) try.
        assert len(calls) == 1

    def test_exhausted_search_returns_none_and_reason_is_search_not_proof(
        self, redistritaje
    ):
        """
        A recursive_tree_part that always fails must exhaust the FULL
        tolerance ladder and all seed retries (no shortcuts), then report
        best_assignment=None. This is the 'sin_particion' path — it must
        never be conflated with a mathematical infeasibility proof.
        """
        calls = []

        def always_failing_recursive_tree_part(graph, parts, pop_target,
                                                 pop_col, epsilon, node_repeats):
            calls.append(epsilon)
            raise RuntimeError("Failed to find a balanced cut")

        graph = _FakeGraph([100, 100, 100, 100])
        best_assignment, best_dev, best_tol = redistritaje.buscar_particion_inicial(
            graph, n_distritos_eff=2, pop_col="pop", ideal_pop=200,
            node_repeats=10, seed=42,
            recursive_tree_part=always_failing_recursive_tree_part,
        )

        assert best_assignment is None
        assert best_dev == float("inf")
        assert best_tol is None
        # Exhausted every (tolerance, seed) combination — proves the search
        # actually ran out of options rather than giving up early.
        expected_calls = (
            len(redistritaje.TOLERANCIA_INICIAL_ESCALERA)
            * redistritaje.N_SEED_TRIES_INICIALIZACION
        )
        assert len(calls) == expected_calls

    def test_diagnostico_busqueda_agotada_disclaims_mathematical_proof(
        self, redistritaje
    ):
        """
        The sin_particion diagnostic must explicitly say this is a search
        failure, not a proof the plan space is mathematically empty, and
        must point to infeasible_population as the actual proof mechanism.
        """
        msg = redistritaje.diagnostico_busqueda_agotada().lower()
        assert "fallo" in msg
        assert "no" in msg and "matemáticamente vacío" in msg
        assert "infeasible_population" in msg
        # Must not itself claim the scenario is proven impossible.
        assert "estructuralmente inviable" not in msg
        assert "imposible" not in msg


# ─── Both statuses carry a stable, distinguishable `reason` in the source ──

class TestStatusReasonWiring:

    def test_infeasible_population_return_includes_reason(self, redistritaje):
        source = importlib_getsource(redistritaje.analizar_region)
        # The infeasible_population branch must set reason from the
        # feasibility result, not hardcode/omit it.
        assert re.search(
            r'"status":\s*"infeasible_population".*?"reason":\s*feasibility\.reason',
            source, re.S,
        )

    def test_sin_particion_return_includes_reason(self, redistritaje):
        source = importlib_getsource(redistritaje.analizar_region)
        assert re.search(
            r'"status":\s*"sin_particion".*?"reason":\s*REASON_INITIALIZATION_SEARCH_EXHAUSTED',
            source, re.S,
        )

    def test_preflight_runs_before_initial_partition_search(self, redistritaje):
        """
        Structural guard: the population-feasibility preflight must appear
        (and therefore run, since it's an unconditional early return on
        failure) strictly before buscar_particion_inicial / recursive_tree_part
        are invoked in analizar_region — i.e. infeasible_population always
        terminates before recursive_tree_part is attempted.
        """
        source = importlib_getsource(redistritaje.analizar_region)
        preflight_pos = source.index("check_population_feasibility(")
        search_pos = source.index("buscar_particion_inicial(")
        assert preflight_pos < search_pos

    def test_reasons_are_distinct_stable_strings(self, redistritaje):
        assert (
            redistritaje.REASON_INITIALIZATION_SEARCH_EXHAUSTED
            != REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND
        )
        assert redistritaje.REASON_INITIALIZATION_SEARCH_EXHAUSTED == (
            "initialization_search_exhausted"
        )


def importlib_getsource(func):
    import inspect
    return inspect.getsource(func)
