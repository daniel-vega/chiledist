"""
tests/test_regiones_apc.py
============================
chiledist.domain.data.REGIONES_APC — {region_code: {"nombre", "nombre_carpeta"}}
for Chile's 16 regions.

This closes the gap tracked by tests/test_entrypoints_n_distritos.py and
tests/test_scripts_demo.py: REGIONES_APC used to be referenced but
undefined, breaking scripts/run_chains.py and scripts/smc_pipeline.py's
region-folder naming (they now fall back to a neutral "R{code:02d}" only
for region codes outside 1-16; within that range they use the real
nombre_carpeta from this dict). It carries no "n_distritos" key — that
parameter is resolved from ScenarioConfig.n_districts, unrelated to this
dict (see tests/test_entrypoints_n_distritos.py).
"""

import pytest

from chiledist.domain.data import REGIONES_APC


class TestRegionesApc:

    def test_has_all_sixteen_regions(self):
        assert set(REGIONES_APC.keys()) == set(range(1, 17))

    def test_region_13_matches_expected_shape(self):
        assert REGIONES_APC[13] == {
            "nombre": "Región Metropolitana",
            "nombre_carpeta": "R13_METROPOLITANA",
        }

    def test_nombre_carpeta_matches_redistritaje_convention(self):
        """
        nombre_carpeta must match the REGION_NOMBRES pattern already used
        by scripts/redistritaje.py, scripts/compare_scenarios.py,
        scripts/pareto_sweep.py and chiledist.domain.ensemble_store.
        """
        expected = {
            1: "R01_TARAPACA", 2: "R02_ANTOFAGASTA", 3: "R03_ATACAMA",
            4: "R04_COQUIMBO", 5: "R05_VALPARAISO", 6: "R06_OHIGGINS",
            7: "R07_MAULE", 8: "R08_BIOBIO", 9: "R09_ARAUCANIA",
            10: "R10_LOS_LAGOS", 11: "R11_AYSEN", 12: "R12_MAGALLANES",
            13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS", 15: "R15_ARICA",
            16: "R16_NUBLE",
        }
        actual = {code: v["nombre_carpeta"] for code, v in REGIONES_APC.items()}
        assert actual == expected

    def test_every_entry_has_nombre_and_nombre_carpeta(self):
        for code, entry in REGIONES_APC.items():
            assert "nombre" in entry, f"region {code} missing 'nombre'"
            assert "nombre_carpeta" in entry, f"region {code} missing 'nombre_carpeta'"
            assert entry["nombre"].strip() != ""
            assert entry["nombre_carpeta"].startswith(f"R{code:02d}_")

    def test_no_n_distritos_key(self):
        """
        REGIONES_APC must not carry an n_distritos field — that parameter
        comes from ScenarioConfig.n_districts, not from a region mapping
        (see the n_distritos consistency audit in
        tests/test_entrypoints_n_distritos.py).
        """
        for entry in REGIONES_APC.values():
            assert "n_distritos" not in entry
            assert "n_districts" not in entry

    def test_importable_via_documented_path(self):
        """The exact import path the affected scripts use."""
        from chiledist.domain.data import REGIONES_APC as imported
        assert imported is REGIONES_APC
