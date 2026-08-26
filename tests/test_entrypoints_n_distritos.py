"""
tests/test_entrypoints_n_distritos.py
=======================================
Regression tests: n_distritos consistency across the parallel entrypoints
scripts/compare_scenarios.py, scripts/pareto_sweep.py, scripts/run_chains.py
and scripts/smc_pipeline.py.

Precedence rule enforced everywhere a ScenarioConfig is involved:
    1. --n-distritos (or --n-districts) explicit CLI value, if given
    2. scenario.n_districts

No argparse default=8 may silently override the scenario, and multi-scenario
experiments must not homogenize distinct scenarios' n_districts onto a
single global value unless the user explicitly asked for that.

REGIONES_APC was, at the time this test module was first written, a dead
symbol referenced but never defined in chiledist.data — used as a silent
fallback source for n_distritos
(`REGIONES_APC.get(region_code, {}).get("n_distritos", 8)`) in run_chains.py
and smc_pipeline.py, always landing on the hardcoded 8 fallback via a
broad `except Exception`. That n_distritos dependency is removed here in
favor of scenario.n_districts and stays removed.

chiledist.data.REGIONES_APC now exists (added separately, for region
display names — {region_code: {"nombre", "nombre_carpeta"}}), and
run_chains.py/smc_pipeline.py use it for output directory naming
(_chain_output_dir/_smc_output_dir). That dict has no "n_distritos" key,
so it cannot reintroduce the old fallback — the guard below checks for the
n_distritos-specific access pattern, not for the import itself.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _import_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(SCRIPTS_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_custom_scenario(path, n_districts=6):
    with open(path, "w") as f:
        f.write(
            "name: custom_scenario\n"
            "decision_unit: CUT\n"
            "preserve:\n"
            "  units: [CUT]\n"
            "  mode: hard\n"
            f"districts:\n  n_districts: {n_districts}\n"
        )


class _ArgvGuard:
    """Context manager: temporarily replace sys.argv."""

    def __init__(self, argv):
        self.argv = argv

    def __enter__(self):
        self._old = sys.argv
        sys.argv = self.argv

    def __exit__(self, *exc):
        sys.argv = self._old


# ─── Static guard: no magic 8 / REGIONES_APC left as an n_distritos source ──

class TestNoHiddenDefaultsAcrossEntrypoints:

    AFFECTED_SCRIPTS = [
        "compare_scenarios.py",
        "pareto_sweep.py",
        "run_chains.py",
        "smc_pipeline.py",
    ]

    def test_no_default_eight_in_any_affected_script(self):
        for name in self.AFFECTED_SCRIPTS:
            content = (SCRIPTS_DIR / name).read_text()
            assert "default=8" not in content, (
                f"{name} still has an argparse default=8 — this is exactly "
                "the silent-override anti-pattern being removed."
            )

    def test_no_regiones_apc_used_to_resolve_n_distritos(self):
        """
        REGIONES_APC now exists (region display names), and run_chains.py /
        smc_pipeline.py legitimately import it for directory naming — that's
        fine. What must never come back is using it as an n_distritos
        source: REGIONES_APC has no "n_distritos" key, so this specific
        access pattern is the tell for the old silent-8 fallback.
        """
        for name in ("run_chains.py", "smc_pipeline.py"):
            content = (SCRIPTS_DIR / name).read_text()
            assert '.get("n_distritos"' not in content, (
                f"{name} still reads n_distritos off REGIONES_APC — the "
                "removed silent-fallback-to-8 anti-pattern."
            )

    def test_electoral_magnitudes_constant_untouched(self):
        """
        Sanity guard: this change must not touch Ley 20.840 magnitudes.
        MAGNITUDES_LEGALES_LEY20840 still sums to 155 seats across 28
        districts (asserted at import time in chiledist/electoral/constants.py;
        re-checked here as a canary specific to this change).
        """
        import chiledist as cd
        assert len(cd.MAGNITUDES_LEGALES_LEY20840) == 28
        assert sum(cd.MAGNITUDES_LEGALES_LEY20840.values()) == 155


# ─── compare_scenarios.py ──────────────────────────────────────────────────

class TestCompareScenariosNDistritos:

    @pytest.fixture(scope="module")
    def mod(self):
        return _import_script("compare_scenarios.py", "compare_scenarios_ndist")

    def test_argparse_default_is_none(self, mod):
        with _ArgvGuard(["compare_scenarios.py"]):
            args = mod.parse_args()
        assert args.n_distritos is None

    def test_scenario_n_districts_used_without_cli_override(self, mod, monkeypatch, tmp_path):
        """A scenario with n_districts=6 must reach analizar_region as 6
        when --n-distritos is not passed."""
        import dataclasses
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL

        captured_calls = []

        def fake_analizar_region(**kwargs):
            captured_calls.append(kwargs)
            return {"region": kwargs["region_code"], "status": "ok",
                    "scenario": kwargs["scenario"].name}

        monkeypatch.setattr(mod, "_import_analizar_region", lambda: fake_analizar_region)
        monkeypatch.setattr(
            mod, "load_scenarios_list",
            lambda args: [dataclasses.replace(SCENARIO_LEGAL, name="sc_six", n_districts=6)],
        )

        with _ArgvGuard([
            "compare_scenarios.py",
            "--base-dir", str(tmp_path),
            "--output-dir", str(tmp_path),
            "--regiones", "13",
        ]):
            mod.main()

        assert len(captured_calls) == 1
        assert captured_calls[0]["n_distritos"] == 6
        assert captured_calls[0]["scenario"].n_districts == 6

    def test_explicit_cli_override_wins(self, mod, monkeypatch, tmp_path):
        import dataclasses
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL

        captured_calls = []

        def fake_analizar_region(**kwargs):
            captured_calls.append(kwargs)
            return {"region": kwargs["region_code"], "status": "ok",
                    "scenario": kwargs["scenario"].name}

        monkeypatch.setattr(mod, "_import_analizar_region", lambda: fake_analizar_region)
        monkeypatch.setattr(
            mod, "load_scenarios_list",
            lambda args: [dataclasses.replace(SCENARIO_LEGAL, name="sc_six", n_districts=6)],
        )

        with _ArgvGuard([
            "compare_scenarios.py",
            "--base-dir", str(tmp_path),
            "--output-dir", str(tmp_path),
            "--regiones", "13",
            "--n-distritos", "7",
        ]):
            mod.main()

        assert captured_calls[0]["n_distritos"] == 7
        assert captured_calls[0]["scenario"].n_districts == 7

    def test_multi_scenario_not_homogenized_without_override(self, mod, monkeypatch, tmp_path):
        """
        Two scenarios with different n_districts (6 and 9) must each keep
        their own value when --n-distritos is not passed — the CLI must not
        silently force both to the same number.
        """
        import dataclasses
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL

        captured_calls = []

        def fake_analizar_region(**kwargs):
            captured_calls.append(kwargs)
            return {"region": kwargs["region_code"], "status": "ok",
                    "scenario": kwargs["scenario"].name}

        scenarios = [
            dataclasses.replace(SCENARIO_LEGAL, name="sc_six", n_districts=6),
            dataclasses.replace(SCENARIO_LEGAL, name="sc_nine", n_districts=9),
        ]
        monkeypatch.setattr(mod, "_import_analizar_region", lambda: fake_analizar_region)
        monkeypatch.setattr(mod, "load_scenarios_list", lambda args: scenarios)

        with _ArgvGuard([
            "compare_scenarios.py",
            "--base-dir", str(tmp_path),
            "--output-dir", str(tmp_path),
            "--regiones", "13",
        ]):
            mod.main()

        n_by_scenario = {c["scenario"].name: c["n_distritos"] for c in captured_calls}
        assert n_by_scenario == {"sc_six": 6, "sc_nine": 9}


# ─── pareto_sweep.py ────────────────────────────────────────────────────────

class TestParetoSweepNDistritos:

    @pytest.fixture(scope="module")
    def mod(self):
        return _import_script("pareto_sweep.py", "pareto_sweep_ndist")

    def test_argparse_default_is_none(self, mod):
        with _ArgvGuard(["pareto_sweep.py"]):
            args = mod.parse_args()
        assert args.n_distritos is None

    def test_run_or_load_uses_scenario_n_districts_without_override(self, mod, tmp_path):
        import dataclasses
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL

        captured = {}

        def fake_analizar_region(**kwargs):
            captured.update(kwargs)

        scenario = dataclasses.replace(SCENARIO_LEGAL, name="sc_six", n_districts=6)
        mod.run_or_load(
            scenario=scenario,
            region_code=13,
            base_dir=str(tmp_path),
            output_base=str(tmp_path),
            n_distritos=None,
            pop_tol=0.15,
            n_steps=100,
            seed=42,
            skip_run=False,
            skip_viz=True,
            analizar_region=fake_analizar_region,
        )

        assert captured["n_distritos"] == 6
        assert captured["scenario"].n_districts == 6

    def test_run_or_load_explicit_override_wins(self, mod, tmp_path):
        import dataclasses
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL

        captured = {}

        def fake_analizar_region(**kwargs):
            captured.update(kwargs)

        scenario = dataclasses.replace(SCENARIO_LEGAL, name="sc_six", n_districts=6)
        mod.run_or_load(
            scenario=scenario,
            region_code=13,
            base_dir=str(tmp_path),
            output_base=str(tmp_path),
            n_distritos=7,
            pop_tol=0.15,
            n_steps=100,
            seed=42,
            skip_run=False,
            skip_viz=True,
            analizar_region=fake_analizar_region,
        )

        assert captured["n_distritos"] == 7
        assert captured["scenario"].n_districts == 7

    def test_sweep_configurations_not_homogenized(self, mod, tmp_path):
        """
        Two configurations (anchors/variants) with different n_districts
        must each keep their own value when no override is given.
        """
        import dataclasses
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL, SCENARIO_APC_FREE

        captured_by_name = {}

        def fake_analizar_region(**kwargs):
            captured_by_name[kwargs["scenario"].name] = kwargs["n_distritos"]

        sc_a = dataclasses.replace(SCENARIO_LEGAL, name="anchor_legal", n_districts=6)
        sc_b = dataclasses.replace(SCENARIO_APC_FREE, name="anchor_free", n_districts=9)

        for sc in (sc_a, sc_b):
            mod.run_or_load(
                scenario=sc,
                region_code=13,
                base_dir=str(tmp_path),
                output_base=str(tmp_path),
                n_distritos=None,
                pop_tol=0.15,
                n_steps=100,
                seed=42,
                skip_run=False,
                skip_viz=True,
                analizar_region=fake_analizar_region,
            )

        assert captured_by_name == {"anchor_legal": 6, "anchor_free": 9}


# ─── run_chains.py ──────────────────────────────────────────────────────────

class TestRunChainsNDistritos:

    @pytest.fixture(scope="module")
    def mod(self):
        return _import_script("run_chains.py", "run_chains_ndist")

    def test_argparse_default_is_none(self, mod):
        parser = mod.build_parser()
        args = parser.parse_args([])
        assert args.n_distritos is None

    def test_chain_output_dir_uses_regiones_apc_nombre_carpeta(self, mod):
        """
        _chain_output_dir() now resolves the real region folder name from
        chiledist.data.REGIONES_APC (which exists — see
        tests/test_regiones_apc.py), not a bare "R{code}" placeholder.
        """
        path = mod._chain_output_dir("/tmp/base", 13, "legal_comunas")
        assert path == os.path.join(
            "/tmp/base", "datos", "R13_METROPOLITANA", "chains", "legal_comunas"
        )

    def test_chain_output_dir_falls_back_for_unknown_region_code(self, mod):
        """Region codes outside 1-16 still degrade to a deterministic path."""
        path = mod._chain_output_dir("/tmp/base", 99, "legal_comunas")
        assert path == os.path.join("/tmp/base", "datos", "R99", "chains", "legal_comunas")

    def test_no_hidden_fallback_to_eight(self, mod, tmp_path, monkeypatch):
        """
        End-to-end (main()) check: with no --n-distritos and a custom
        scenario file carrying n_districts=6, run_chains() must be called
        with n_distritos=6 — never a hardcoded 8 from a broken REGIONES_APC
        lookup.
        """
        captured = {}

        def fake_run_chains(**kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(mod, "run_chains", fake_run_chains)

        yml_path = tmp_path / "custom.yml"
        _write_custom_scenario(str(yml_path), n_districts=6)

        with _ArgvGuard([
            "run_chains.py",
            "--base-dir", str(tmp_path),
            "--regiones", "13",
            "--scenario-file", str(yml_path),
        ]):
            # main() exits(1) after the (faked) run because no chain metrics
            # were produced — expected; we only care what run_chains() got.
            with pytest.raises(SystemExit):
                mod.main()

        assert captured["n_distritos"] == 6
        assert captured["n_distritos"] != 8

    def test_explicit_cli_override_wins(self, mod, tmp_path, monkeypatch):
        captured = {}

        def fake_run_chains(**kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(mod, "run_chains", fake_run_chains)

        yml_path = tmp_path / "custom.yml"
        _write_custom_scenario(str(yml_path), n_districts=6)

        with _ArgvGuard([
            "run_chains.py",
            "--base-dir", str(tmp_path),
            "--regiones", "13",
            "--scenario-file", str(yml_path),
            "--n-distritos", "9",
        ]):
            with pytest.raises(SystemExit):
                mod.main()

        assert captured["n_distritos"] == 9


# ─── smc_pipeline.py ────────────────────────────────────────────────────────

class TestSmcPipelineNDistritos:

    @pytest.fixture(scope="module")
    def mod(self):
        return _import_script("smc_pipeline.py", "smc_pipeline_ndist")

    def test_argparse_default_is_none(self, mod):
        parser = mod.build_parser()
        args = parser.parse_args([])
        assert args.n_districts is None

    def test_output_dir_helpers_use_regiones_apc_nombre_carpeta(self, mod):
        assert mod._region_nombre(13) == "R13_METROPOLITANA"
        path = mod._smc_output_dir("/tmp/base", 13, "apc_soft")
        assert path == os.path.join(
            "/tmp/base", "datos", "R13_METROPOLITANA", "smc", "apc_soft"
        )

    def test_region_nombre_falls_back_for_unknown_region_code(self, mod):
        assert mod._region_nombre(99) == "R99"

    def test_no_hidden_fallback_to_eight(self, mod, tmp_path, monkeypatch):
        """
        With no --n-districts and --scenario resolving to a custom YAML
        (n_districts=6) via the existing scenarios/<name>.yml convention,
        export_and_generate_script() must receive n_districts=6 — never a
        hardcoded 8 from a broken REGIONES_APC lookup.
        """
        captured = {}

        monkeypatch.setattr(
            mod, "load_region_data",
            lambda **kwargs: (None, None, None, []),
        )

        def fake_export(**kwargs):
            captured.update(kwargs)
            return str(tmp_path / "fake_script.R")

        monkeypatch.setattr(mod, "export_and_generate_script", fake_export)

        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        _write_custom_scenario(str(scenarios_dir / "custom_smc.yml"), n_districts=6)

        with _ArgvGuard([
            "smc_pipeline.py",
            "--base-dir", str(tmp_path),
            "--regiones", "13",
            "--scenario", "custom_smc",
        ]):
            mod.main()

        assert captured["n_districts"] == 6
        assert captured["n_districts"] != 8

    def test_explicit_cli_override_wins(self, mod, tmp_path, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            mod, "load_region_data",
            lambda **kwargs: (None, None, None, []),
        )

        def fake_export(**kwargs):
            captured.update(kwargs)
            return str(tmp_path / "fake_script.R")

        monkeypatch.setattr(mod, "export_and_generate_script", fake_export)

        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        _write_custom_scenario(str(scenarios_dir / "custom_smc.yml"), n_districts=6)

        with _ArgvGuard([
            "smc_pipeline.py",
            "--base-dir", str(tmp_path),
            "--regiones", "13",
            "--scenario", "custom_smc",
            "--n-districts", "11",
        ]):
            mod.main()

        assert captured["n_districts"] == 11

    def test_unresolvable_scenario_raises_instead_of_silent_default(
        self, mod, tmp_path, monkeypatch
    ):
        """
        No fallback to 8 when --n-districts is absent AND --scenario can't
        be resolved to a ScenarioConfig via SCENARIOS or scenarios/<name>.yml
        — this must be reported (raised), not silently papered over.
        """
        monkeypatch.setattr(
            mod, "load_region_data",
            lambda **kwargs: (None, None, None, []),
        )
        monkeypatch.setattr(mod, "export_and_generate_script", lambda **kwargs: "unused.R")

        with _ArgvGuard([
            "smc_pipeline.py",
            "--base-dir", str(tmp_path),
            "--regiones", "13",
            "--scenario", "totally_unknown_scenario_xyz",
        ]):
            with pytest.raises(ValueError, match="n_districts"):
                mod.main()
