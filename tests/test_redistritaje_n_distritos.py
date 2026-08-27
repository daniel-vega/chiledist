"""
tests/test_redistritaje_n_distritos.py
========================================
Regression tests for the n_distritos CLI override bug in
scripts/redistritaje.py.

Background
----------
`n_distritos` means "number of territorial partitions to generate in the
ReCom simulation" everywhere it appears (ScenarioConfig.n_districts,
chiledist.rules.feasibility, chiledist.engines.metrics.ideal_population). It is
unrelated to the Ley 20.840 electoral magnitude (seats per legal district,
MAGNITUDES_LEGALES_LEY20840) — that lives in chiledist/rules/electoral_rules.py
and is untouched here.

ScenarioConfig.n_districts is the authoritative field for this parameter.
Before this fix, `--n-distritos` defaulted to 8 (not None), so
`build_scenario()`'s `if args.n_distritos:` was always truthy and silently
clobbered any n_districts coming from a scenario/YAML — even when the user
never passed --n-distritos. Separately, `main()` forwarded the raw CLI
value (`args.n_distritos`) to `analizar_region()` instead of the merged
`scenario.n_districts`, bypassing the scenario a second time.
"""

import argparse
import importlib.util
import os
import sys
import tempfile

import pytest


def _import_redistritaje():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(root, "scripts", "redistritaje.py")
    spec = importlib.util.spec_from_file_location(
        "redistritaje_ndistritos", script_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def redistritaje():
    return _import_redistritaje()


def _fake_args(**overrides):
    base = dict(
        scenario_file=None,
        scenario=None,
        decision_unit=None,
        preserve_mode=None,
        preserve_units=None,
        split_penalty=None,
        n_distritos=None,
        pop_tol=None,
        n_steps=None,
        seed=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _write_custom_scenario(path, n_districts=7):
    with open(path, "w") as f:
        f.write(
            "name: custom_scenario\n"
            "decision_unit: CUT\n"
            "preserve:\n"
            "  units: [CUT]\n"
            "  mode: hard\n"
            f"districts:\n  n_districts: {n_districts}\n"
        )


class TestNDistritosCLIDefault:

    def test_argparse_default_is_none(self, redistritaje):
        """
        The CLI default must be None, not a number — otherwise
        build_scenario() cannot distinguish "user didn't pass
        --n-distritos" from "user explicitly asked for the default value".
        """
        old_argv = sys.argv
        try:
            sys.argv = ["redistritaje.py"]
            args = redistritaje.parse_args()
        finally:
            sys.argv = old_argv
        assert args.n_distritos is None


class TestBuildScenarioDoesNotOverrideSilently:

    def test_custom_scenario_n_districts_survives_when_flag_not_passed(
        self, redistritaje
    ):
        """
        Regression test for the silent-override bug: a custom scenario YAML
        with n_districts=7 must come through build_scenario() unchanged
        when --n-distritos is not passed on the CLI.
        """
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "custom.yml")
            _write_custom_scenario(path, n_districts=7)
            cfg = redistritaje.build_scenario(_fake_args(scenario_file=path))
        assert cfg.n_districts == 7

    def test_explicit_flag_still_overrides_scenario(self, redistritaje):
        """When the user DOES pass --n-distritos, it must win over the scenario."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "custom.yml")
            _write_custom_scenario(path, n_districts=7)
            cfg = redistritaje.build_scenario(
                _fake_args(scenario_file=path, n_distritos=10)
            )
        assert cfg.n_districts == 10

    def test_predefined_scenario_n_districts_not_forced(self, redistritaje):
        """A predefined --scenario keeps its own n_districts when the flag
        is absent, instead of being forced to a CLI-level constant."""
        from chiledist.rules.scenario_rules import SCENARIO_LEGAL

        cfg = redistritaje.build_scenario(_fake_args(scenario="legal"))
        assert cfg.n_districts == SCENARIO_LEGAL.n_districts


class TestMainWiresScenarioNDistritos:

    def test_main_forwards_scenario_n_districts_not_raw_cli_arg(
        self, redistritaje, monkeypatch
    ):
        """
        End-to-end wiring check: analizar_region() must receive
        scenario.n_districts (post build_scenario merge), not the raw
        args.n_distritos — this catches the second override point in
        main(), independent of the build_scenario() fix.
        analizar_region is monkeypatched out so this test needs no
        shapefiles/gerrychain.
        """
        captured = {}

        def fake_analizar_region(**kwargs):
            captured.update(kwargs)
            return {"region": kwargs["region_code"], "status": "ok"}

        monkeypatch.setattr(redistritaje, "analizar_region", fake_analizar_region)

        with tempfile.TemporaryDirectory() as scenario_dir, \
             tempfile.TemporaryDirectory() as out_dir:
            yml_path = os.path.join(scenario_dir, "custom.yml")
            _write_custom_scenario(yml_path, n_districts=7)

            argv = [
                "redistritaje.py",
                "--base-dir", ".",
                "--output-dir", out_dir,
                "--regiones", "13",
                "--scenario-file", yml_path,
                "--skip-viz",
            ]
            old_argv = sys.argv
            sys.argv = argv
            try:
                redistritaje.main()
            finally:
                sys.argv = old_argv

        assert captured["n_distritos"] == 7
