"""
tests/test_smoke.py
===================
Tests de humo sin dependencias externas (no gerrychain, no shapefiles).
Verifican que los módulos públicos importan, validan y calculan correctamente
con datos en memoria.

Ejecutar:
    python -m pytest tests/test_smoke.py -v
"""

import dataclasses
import sys
import unittest
import unittest.mock as mock

# ── Mock de gerrychain para que los imports no fallen ─────────────────────────
if "gerrychain" not in sys.modules:
    sys.modules["gerrychain"] = mock.MagicMock()

import chiledist as cd
from chiledist.config import ScenarioConfig, SCENARIO_LEGAL, SCENARIO_APC_FREE


class TestScenarioLegalValidates(unittest.TestCase):
    def test_legal_validates_without_error(self):
        sc = dataclasses.replace(SCENARIO_LEGAL)
        sc.validate()   # no debe lanzar excepción

    def test_apc_free_validates_without_error(self):
        sc = dataclasses.replace(SCENARIO_APC_FREE)
        sc.validate()

    def test_invalid_decision_unit_raises(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, decision_unit="INVALID")
        with self.assertRaises(ValueError):
            sc.validate()

    def test_invalid_preserve_mode_raises(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, preserve_mode="strong")
        with self.assertRaises(ValueError):
            sc.validate()

    def test_hard_mode_without_preserve_units_raises(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, preserve_units=[])
        with self.assertRaises(ValueError):
            sc.validate()

    def test_pop_tolerance_bounds(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, pop_tolerance=1.5)
        with self.assertRaises(ValueError):
            sc.validate()

    def test_pop_source_field_exists(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, pop_source="manzana")
        self.assertEqual(sc.pop_source, "manzana")

    def test_pop_source_serializes_yaml(self):
        import tempfile, os
        sc = dataclasses.replace(SCENARIO_LEGAL, pop_source="censo2024")
        with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
            path = f.name
        try:
            cd.save_scenario(sc, path)
            sc2 = cd.load_scenario(path)
            self.assertEqual(sc2.pop_source, "censo2024")
        finally:
            os.unlink(path)


class TestViviendosWarningFires(unittest.TestCase):
    def test_viviendas_with_hard_mode_warns(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, pop_col="viviendas")
        with self.assertWarns(UserWarning):
            sc.validate()

    def test_viviendas_with_none_mode_does_not_warn(self):
        sc = dataclasses.replace(SCENARIO_APC_FREE, pop_col="viviendas")
        # No debe emitir UserWarning sobre viviendas (preserve_mode='none')
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sc.validate()
        viviendas_warnings = [x for x in w if "viviendas" in str(x.message).lower()]
        self.assertEqual(len(viviendas_warnings), 0)

    def test_personas_with_hard_mode_does_not_warn(self):
        sc = dataclasses.replace(SCENARIO_LEGAL, pop_col="personas")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sc.validate()
        viviendas_warnings = [x for x in w if "viviendas" in str(x.message).lower()]
        self.assertEqual(len(viviendas_warnings), 0)


class TestDhondtSimpleCase(unittest.TestCase):
    def test_basic_allocation(self):
        votes = {"A": 100_000, "B": 80_000, "C": 30_000}
        result = cd.dhondt(votes, seats=5)
        total_seats = sum(result.values())
        self.assertEqual(total_seats, 5)
        # Partido más votado debe recibir al menos 1 escaño
        self.assertGreaterEqual(result["A"], 1)

    def test_single_party_gets_all(self):
        votes = {"A": 100_000, "B": 0, "C": 0}
        result = cd.dhondt(votes, seats=3)
        self.assertEqual(result["A"], 3)
        self.assertEqual(result.get("B", 0), 0)

    def test_empty_votes_returns_empty(self):
        result = cd.dhondt({}, seats=3)
        self.assertEqual(result, {})

    def test_magnitudes_sum_to_155(self):
        total = sum(cd.MAGNITUDES_LEGALES_LEY20840.values())
        self.assertEqual(total, 155)

    def test_magnitudes_2021_alias(self):
        self.assertEqual(cd.MAGNITUDES_LEGALES_LEY20840,
                         cd.MAGNITUDES_LEGALES_2021)


class TestParetoFrontierNd(unittest.TestCase):
    def _make_df(self):
        import pandas as pd
        return pd.DataFrame({
            "plan_id":        [0, 1, 2, 3, 4],
            "max_dev_pob_pct": [2.0, 5.0, 3.0, 1.0, 4.0],
            "pp_promedio":    [0.6, 0.3, 0.5, 0.4, 0.7],
            "cut_edges":      [10,  15,  12,  20,  8],
        })

    def test_pareto_returns_subset(self):
        df = self._make_df()
        idxs = cd.pareto_frontier_nd(
            df[["max_dev_pob_pct", "cut_edges"]],
            minimize={"max_dev_pob_pct": True, "cut_edges": True},
        )
        self.assertLessEqual(len(idxs), len(df))
        self.assertGreater(len(idxs), 0)

    def test_pareto_all_dominated_returns_one(self):
        import pandas as pd
        df = pd.DataFrame({
            "x": [1, 2, 3, 4],
            "y": [1, 2, 3, 4],
        })
        idxs = cd.pareto_frontier_nd(df, minimize={"x": True, "y": True})
        # Solo (1,1) es Pareto-óptimo
        self.assertEqual(len(idxs), 1)


class TestImportWithoutGerrychain(unittest.TestCase):
    def test_chiledist_version_accessible(self):
        self.assertIsNotNone(cd.__version__)

    def test_scenario_constants_exist(self):
        self.assertIsNotNone(cd.SCENARIO_LEGAL)
        self.assertIsNotNone(cd.SCENARIO_APC_FREE)
        self.assertIsNotNone(cd.SCENARIO_APC_SOFT)

    def test_plan_ensemble_importable(self):
        from chiledist.persistence import PlanEnsemble
        self.assertTrue(hasattr(PlanEnsemble, "load"))
        self.assertTrue(hasattr(PlanEnsemble, "save"))
        self.assertTrue(hasattr(PlanEnsemble, "filter"))
        self.assertTrue(hasattr(PlanEnsemble, "sample"))

    def test_chiledist_map_importable(self):
        from chiledist.map import ChileDistMap
        self.assertTrue(hasattr(ChileDistMap, "from_apc"))
        self.assertTrue(hasattr(ChileDistMap, "to_dict"))

    def test_run_recom_chain_importable(self):
        self.assertTrue(callable(cd.run_recom_chain))


if __name__ == "__main__":
    unittest.main(verbosity=2)
