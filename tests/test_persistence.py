"""
tests/test_persistence.py
=========================
Tests de persistencia con datos sintéticos (no requieren shapefiles ni
gerrychain). Verifican el roundtrip de PlanEnsemble, el schema del parquet,
run_manifest y la carga por run_id.

Ejecutar:
    python -m pytest tests/test_persistence.py -v
"""

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import chiledist as cd
from chiledist.domain.persistence import (
    PlanEnsemble,
    build_run_manifest,
    get_package_versions,
    new_run_id,
    save_assignments_parquet,
    save_run_manifest,
    sha256_file,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_fake_planes(n_draws=20, n_units=8, n_districts=3, seed=0):
    """Genera planes sintéticos {unit_id: district}."""
    rng = np.random.default_rng(seed)
    unit_ids = [f"ID_{i:03d}" for i in range(n_units)]
    plans = []
    for _ in range(n_draws):
        assignment = {uid: int(rng.integers(0, n_districts))
                      for uid in unit_ids}
        plans.append(assignment)
    return plans, unit_ids


def _make_fake_stats(n_draws=20, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "plan_id":        list(range(n_draws)),
        "max_dev_pob_pct": rng.uniform(0, 10, n_draws).round(3),
        "pp_promedio":    rng.uniform(0.3, 0.8, n_draws).round(4),
        "cut_edges":      rng.integers(5, 30, n_draws).tolist(),
        "score":          rng.uniform(-1, 1, n_draws).round(4),
    })


def _make_fake_chain_metrics(n_steps=20):
    return pd.DataFrame({
        "step":        list(range(n_steps)),
        "cut_edges":   list(range(10, 10 + n_steps)),
        "max_dev_pct": [2.0] * n_steps,
    })


class TestAssignmentsParquetSchema(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_id = new_run_id()
        self.planes, self.unit_ids = _make_fake_planes()
        id_map = {uid: uid for uid in self.unit_ids}
        save_assignments_parquet(
            planes=self.planes,
            id_map=id_map,
            run_id=self.run_id,
            scenario_name="test_scenario",
            output_dir=self.tmpdir,
            chain_id=0,
        )

    def test_parquet_file_created(self):
        self.assertTrue((Path(self.tmpdir) / "assignments.parquet").exists())

    def test_required_columns_present(self):
        df = pd.read_parquet(Path(self.tmpdir) / "assignments.parquet")
        for col in ("run_id", "scenario", "chain_id", "draw", "unit_id", "district"):
            self.assertIn(col, df.columns, f"Columna requerida ausente: {col}")

    def test_run_id_matches(self):
        df = pd.read_parquet(Path(self.tmpdir) / "assignments.parquet")
        self.assertTrue((df["run_id"] == self.run_id).all())

    def test_draw_count_matches(self):
        df = pd.read_parquet(Path(self.tmpdir) / "assignments.parquet")
        self.assertEqual(df["draw"].nunique(), len(self.planes))

    def test_unit_id_count_matches(self):
        df = pd.read_parquet(Path(self.tmpdir) / "assignments.parquet")
        self.assertEqual(df["unit_id"].nunique(), len(self.unit_ids))

    def test_district_dtype(self):
        df = pd.read_parquet(Path(self.tmpdir) / "assignments.parquet")
        self.assertEqual(df["district"].dtype, "int16")

    def test_chain_id_dtype(self):
        df = pd.read_parquet(Path(self.tmpdir) / "assignments.parquet")
        self.assertEqual(df["chain_id"].dtype, "int8")


class TestPlanEnsembleSaveLoadRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_id = new_run_id()
        planes, unit_ids = _make_fake_planes()
        id_map = {uid: uid for uid in unit_ids}

        # Construir assignments DataFrame directamente
        rows = []
        for draw, plan in enumerate(planes):
            for uid, dist in plan.items():
                rows.append({
                    "run_id":   self.run_id,
                    "scenario": "test_scenario",
                    "chain_id": 0,
                    "draw":     draw,
                    "unit_id":  str(uid),
                    "district": int(dist),
                })
        assignments = pd.DataFrame(rows)
        assignments["chain_id"] = assignments["chain_id"].astype("int8")
        assignments["draw"]     = assignments["draw"].astype("int32")
        assignments["district"] = assignments["district"].astype("int16")

        stats         = _make_fake_stats()
        chain_metrics = _make_fake_chain_metrics()
        manifest      = {"run_id": self.run_id, "scenario": {"name": "test_scenario"}}

        self.ensemble = PlanEnsemble(
            run_id=self.run_id,
            scenario_name="test_scenario",
            assignments=assignments,
            stats=stats,
            chain_metrics=chain_metrics,
            manifest=manifest,
        )
        self.ensemble.save(self.tmpdir)

    def test_save_creates_parquet(self):
        self.assertTrue((Path(self.tmpdir) / "assignments.parquet").exists())

    def test_save_creates_ensemble_stats(self):
        self.assertTrue((Path(self.tmpdir) / "ensemble_stats.csv").exists())

    def test_save_creates_chain_metrics(self):
        self.assertTrue((Path(self.tmpdir) / "metricas_cadena.csv").exists())

    def test_save_creates_manifest(self):
        self.assertTrue((Path(self.tmpdir) / "run_manifest.json").exists())

    def test_load_roundtrip_run_id(self):
        loaded = PlanEnsemble.load(self.tmpdir)
        self.assertEqual(loaded.run_id, self.run_id)

    def test_load_roundtrip_scenario_name(self):
        loaded = PlanEnsemble.load(self.tmpdir)
        self.assertEqual(loaded.scenario_name, "test_scenario")

    def test_load_roundtrip_draws(self):
        loaded = PlanEnsemble.load(self.tmpdir)
        self.assertEqual(loaded.n_draws, self.ensemble.n_draws)

    def test_load_roundtrip_units(self):
        loaded = PlanEnsemble.load(self.tmpdir)
        self.assertEqual(loaded.n_units, self.ensemble.n_units)

    def test_load_stats_shape(self):
        loaded = PlanEnsemble.load(self.tmpdir)
        self.assertEqual(len(loaded.stats), len(self.ensemble.stats))

    def test_load_missing_parquet_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                PlanEnsemble.load(d)

    def test_repr_contains_run_id_prefix(self):
        r = repr(self.ensemble)
        self.assertIn(self.run_id[:8], r)


class TestPlanEnsembleFilter(unittest.TestCase):
    def setUp(self):
        planes, unit_ids = _make_fake_planes(n_draws=50)
        id_map = {uid: uid for uid in unit_ids}
        rows = []
        for draw, plan in enumerate(planes):
            for uid, dist in plan.items():
                rows.append({
                    "run_id": "test", "scenario": "s", "chain_id": 0,
                    "draw": draw, "unit_id": uid, "district": dist,
                })
        assignments = pd.DataFrame(rows)
        assignments["chain_id"] = assignments["chain_id"].astype("int8")
        assignments["draw"]     = assignments["draw"].astype("int32")
        assignments["district"] = assignments["district"].astype("int16")
        stats = _make_fake_stats(n_draws=50)

        self.ensemble = PlanEnsemble(
            run_id="test-run-id",
            scenario_name="s",
            assignments=assignments,
            stats=stats,
            chain_metrics=pd.DataFrame(),
        )

    def test_filter_max_dev_reduces_plans(self):
        filtered = self.ensemble.filter(max_dev=5.0)
        self.assertLessEqual(filtered.n_draws, self.ensemble.n_draws)

    def test_filter_returns_new_instance(self):
        filtered = self.ensemble.filter(max_dev=5.0)
        self.assertIsNot(filtered, self.ensemble)

    def test_filter_max_dev_zero_returns_empty_or_small(self):
        filtered = self.ensemble.filter(max_dev=0.0)
        self.assertEqual(filtered.n_draws, 0)

    def test_filter_large_threshold_returns_all(self):
        filtered = self.ensemble.filter(max_dev=100.0)
        self.assertEqual(filtered.n_draws, self.ensemble.n_draws)

    def test_sample_reduces_draws(self):
        sampled = self.ensemble.sample(n=10, seed=42)
        self.assertEqual(sampled.n_draws, 10)

    def test_sample_reproducible(self):
        s1 = self.ensemble.sample(n=10, seed=99)
        s2 = self.ensemble.sample(n=10, seed=99)
        draws1 = set(s1.assignments["draw"].unique())
        draws2 = set(s2.assignments["draw"].unique())
        self.assertEqual(draws1, draws2)

    def test_sample_larger_than_total_returns_all(self):
        sampled = self.ensemble.sample(n=999, seed=0)
        self.assertEqual(sampled.n_draws, self.ensemble.n_draws)


class TestRunManifestContainsRequiredFields(unittest.TestCase):
    def test_manifest_has_required_keys(self):
        sc = dataclasses.replace(cd.SCENARIO_LEGAL)
        manifest = build_run_manifest(
            run_id=new_run_id(),
            timestamp_start="2026-06-20T14:00:00",
            timestamp_end="2026-06-20T15:00:00",
            scenario=sc,
            pop_source="viviendas",
            pop_col_effective="viviendas",
            pop_tolerance_requested=0.05,
            pop_tolerance_effective=0.05,
            pop_tolerance_fallback_used=False,
            n_steps_requested=1000,
            n_steps_executed=1000,
            n_steps_warmup=50,
            n_plans_generated=1000,
            n_plans_valid=850,
            region_code=13,
            region_name="R13_METROPOLITANA",
            n_units=345,
        )

        required_top = ["run_id", "chiledist_version", "timestamp_start",
                        "timestamp_end", "scenario", "data", "algorithm",
                        "environment", "outputs"]
        for key in required_top:
            self.assertIn(key, manifest, f"Clave requerida ausente: {key}")

        required_scenario = [
            "name", "pop_source", "pop_col_effective",
            "pop_tolerance_requested", "pop_tolerance_effective",
            "pop_tolerance_fallback_used",
        ]
        for key in required_scenario:
            self.assertIn(key, manifest["scenario"],
                          f"Clave scenario ausente: {key}")

        required_algorithm = [
            "n_steps_requested", "n_steps_executed", "n_steps_warmup",
            "n_plans_generated", "n_plans_valid",
        ]
        for key in required_algorithm:
            self.assertIn(key, manifest["algorithm"],
                          f"Clave algorithm ausente: {key}")

        env = manifest["environment"]
        self.assertIn("python_version", env)
        self.assertIn("packages", env)

    def test_manifest_serializes_to_json(self):
        sc = dataclasses.replace(cd.SCENARIO_LEGAL)
        manifest = build_run_manifest(
            run_id=new_run_id(),
            timestamp_start="2026-06-20T14:00:00",
            timestamp_end="2026-06-20T15:00:00",
            scenario=sc,
            pop_source="viviendas",
            pop_col_effective="viviendas",
            pop_tolerance_requested=0.05,
            pop_tolerance_effective=0.05,
            pop_tolerance_fallback_used=False,
            n_steps_requested=100,
            n_steps_executed=100,
            n_steps_warmup=10,
            n_plans_generated=100,
            n_plans_valid=80,
            region_code=5,
            region_name="R05_VALPARAISO",
            n_units=50,
        )
        # Debe poder serializarse sin errores
        serialized = json.dumps(manifest, default=str)
        loaded = json.loads(serialized)
        self.assertEqual(loaded["run_id"], manifest["run_id"])

    def test_manifest_saves_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            sc = dataclasses.replace(cd.SCENARIO_LEGAL)
            manifest = build_run_manifest(
                run_id=new_run_id(),
                timestamp_start="2026-06-20T14:00:00",
                timestamp_end="2026-06-20T15:00:00",
                scenario=sc,
                pop_source="viviendas",
                pop_col_effective="viviendas",
                pop_tolerance_requested=0.05,
                pop_tolerance_effective=0.05,
                pop_tolerance_fallback_used=False,
                n_steps_requested=100,
                n_steps_executed=100,
                n_steps_warmup=10,
                n_plans_generated=100,
                n_plans_valid=80,
                region_code=1,
                region_name="R01_TARAPACA",
                n_units=20,
            )
            path = save_run_manifest(manifest, d)
            self.assertTrue(Path(path).exists())
            with open(path) as f:
                loaded = json.load(f)
            self.assertEqual(loaded["run_id"], manifest["run_id"])


class TestLoadEnsemblesByRunId(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_id = new_run_id()
        ts = "20260620_140000"
        rid_short = self.run_id[:8]

        # Simular estructura de directorios de redistritaje
        scenario_dir = (Path(self.tmpdir) / "R13_METROPOLITANA"
                        / "redistritaje" / "legal_comunas")
        run_dir = scenario_dir / f"run_{ts}_{rid_short}"
        run_dir.mkdir(parents=True)

        # ensemble_stats.csv en run_dir (canónico)
        self.stats = _make_fake_stats(n_draws=10)
        self.stats.to_csv(run_dir / "ensemble_stats.csv", index=False)

        # También en la raíz del escenario (retrocompatibilidad)
        self.stats.to_csv(scenario_dir / "ensemble_stats.csv", index=False)

    def test_load_without_run_id_reads_root(self):
        ensembles = cd.load_ensembles_from_disk(
            self.tmpdir, region_code=13,
            scenario_names=["legal_comunas"],
        )
        self.assertIn("legal_comunas", ensembles)
        self.assertEqual(len(ensembles["legal_comunas"]), len(self.stats))

    def test_load_with_run_id_reads_run_dir(self):
        ensembles = cd.load_ensembles_from_disk(
            self.tmpdir, region_code=13,
            scenario_names=["legal_comunas"],
            run_id=self.run_id,
        )
        self.assertIn("legal_comunas", ensembles)

    def test_load_wrong_run_id_returns_empty(self):
        wrong_id = new_run_id()
        ensembles = cd.load_ensembles_from_disk(
            self.tmpdir, region_code=13,
            scenario_names=["legal_comunas"],
            run_id=wrong_id,
        )
        self.assertNotIn("legal_comunas", ensembles)

    def test_load_missing_scenario_returns_empty(self):
        ensembles = cd.load_ensembles_from_disk(
            self.tmpdir, region_code=13,
            scenario_names=["no_existe"],
        )
        self.assertNotIn("no_existe", ensembles)


class TestHelpers(unittest.TestCase):
    def test_new_run_id_is_uuid_format(self):
        import uuid
        rid = new_run_id()
        parsed = uuid.UUID(rid)    # lanza si no es UUID válido
        self.assertEqual(str(parsed), rid)

    def test_sha256_nonexistent_returns_empty(self):
        result = sha256_file("/no/such/file/exists.parquet")
        self.assertEqual(result, "")

    def test_sha256_real_file(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"chiledist test content")
            path = f.name
        try:
            h = sha256_file(path)
            self.assertEqual(len(h), 64)   # SHA-256 hex = 64 chars
        finally:
            os.unlink(path)

    def test_get_package_versions_returns_dict(self):
        versions = get_package_versions()
        self.assertIsInstance(versions, dict)
        self.assertIn("numpy", versions)
        self.assertIn("pandas", versions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
