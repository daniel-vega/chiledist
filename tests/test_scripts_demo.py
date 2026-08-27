"""
tests/test_scripts_demo.py
===========================
Integration tests for analysis scripts.

Covered scenarios:
    1. malapportionment.py --demo  (fully self-contained, synthetic data)
    2. electoral_analysis.py --demo (fully self-contained, synthetic data)
    3. pareto_sweep.py --skip-run  (reads pre-created fixture CSVs)
    4. run_chains.py: load_chain_metrics + run_convergence_diagnostics
       tested as direct function calls with synthetic DataFrames.

None of these tests require SHP_APC2023, Censo 2024, or SERVEL data.

Note on run_chains.py subprocess:
    _chain_output_dir() used to import `REGIONES_APC` from `chiledist.data`,
    a symbol that didn't exist at the time, making the full CLI
    non-functional even via --skip-run (see tests/test_entrypoints_n_distritos.py
    for the n_distritos audit this was found alongside). `chiledist.domain.data`
    (formerly `chiledist.data`) now exports REGIONES_APC (see
    tests/test_regiones_apc.py), and
    run_chains.py/smc_pipeline.py use it for region directory names. The
    internal functions are still tested directly here rather than via
    subprocess, since a full run requires real SHP_APC2023 data.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless rendering for direct function tests

import numpy as np
import pandas as pd
import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _run_script(script_name: str, extra_args: list[str],
                tmpdir: str) -> subprocess.CompletedProcess:
    """Run a script as a subprocess with MPLBACKEND=Agg."""
    env = {**os.environ, "MPLBACKEND": "Agg"}
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + extra_args
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(SCRIPTS_DIR.parent))


# ── 1. malapportionment.py --demo ─────────────────────────────────────────────

class TestMalapportionmentDemo:

    def test_exit_code_zero(self, tmp_path):
        result = _run_script(
            "malapportionment.py",
            ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
            str(tmp_path),
        )
        assert result.returncode == 0, (
            f"malapportionment.py --demo failed:\n{result.stderr}"
        )

    def test_pxe_csv_exists(self, tmp_path):
        _run_script("malapportionment.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "malapportionment" / "malapportionment_pxe.csv").exists()

    def test_comparacion_csv_exists(self, tmp_path):
        _run_script("malapportionment.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "malapportionment" / "malapportionment_comparacion.csv").exists()

    def test_umbrales_csv_exists(self, tmp_path):
        _run_script("malapportionment.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "malapportionment" / "malapportionment_umbrales.csv").exists()

    def test_electoral_csv_exists(self, tmp_path):
        _run_script("malapportionment.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "malapportionment" / "malapportionment_electoral.csv").exists()

    def test_pxe_csv_has_required_columns(self, tmp_path):
        _run_script("malapportionment.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        df = pd.read_csv(tmp_path / "malapportionment" / "malapportionment_pxe.csv")
        for col in ("distrito", "magnitud_vigente", "personas_x_escano",
                    "peso_relativo"):
            assert col in df.columns, f"Missing column: {col}"

    def test_comparacion_csv_delta_col(self, tmp_path):
        _run_script("malapportionment.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        df = pd.read_csv(tmp_path / "malapportionment" / "malapportionment_comparacion.csv")
        assert "delta" in df.columns


# ── 2. electoral_analysis.py --demo ───────────────────────────────────────────

class TestElectoralAnalysisDemo:

    def test_exit_code_zero(self, tmp_path):
        result = _run_script(
            "electoral_analysis.py",
            ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
            str(tmp_path),
        )
        assert result.returncode == 0, (
            f"electoral_analysis.py --demo failed:\n{result.stderr}"
        )

    def test_b1_csv_exists(self, tmp_path):
        _run_script("electoral_analysis.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "electoral_analysis" / "electoral_b1_distrito.csv").exists()

    def test_b2_csv_exists(self, tmp_path):
        _run_script("electoral_analysis.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "electoral_analysis" / "electoral_b2_matrix.csv").exists()

    def test_b3_csv_exists(self, tmp_path):
        _run_script("electoral_analysis.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "electoral_analysis" / "electoral_b3_ensemble.csv").exists()

    def test_b4_csv_exists(self, tmp_path):
        _run_script("electoral_analysis.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        assert (tmp_path / "electoral_analysis" / "electoral_b4_bonus.csv").exists()

    def test_b2_matrix_has_modo_cols(self, tmp_path):
        _run_script("electoral_analysis.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        df = pd.read_csv(tmp_path / "electoral_analysis" / "electoral_b2_matrix.csv")
        assert "gallagher" in df.columns
        assert "modo_dhondt" in df.columns

    def test_b4_bonus_values(self, tmp_path):
        _run_script("electoral_analysis.py",
                    ["--demo", "--skip-viz", "--output-dir", str(tmp_path)],
                    str(tmp_path))
        df = pd.read_csv(tmp_path / "electoral_analysis" / "electoral_b4_bonus.csv")
        assert len(df) > 0
        assert "partido" in df.columns or "pacto" in df.columns


# ── 3. pareto_sweep.py --skip-run with fixture CSVs ───────────────────────────

def _make_ensemble_csv(path: Path, preserve_mode: str, seed: int = 0) -> None:
    """Create a minimal ensemble_stats.csv fixture."""
    rng = np.random.default_rng(seed)
    n = 20
    df = pd.DataFrame({
        "max_dev_pob_pct":    rng.uniform(1, 10, n),
        "n_comunas_partidas": rng.integers(0, 5, n),
        "split_severity":     rng.uniform(0, 0.5, n),
        "pp_promedio":        rng.uniform(0.3, 0.7, n),
        "pop_afectada_pct":   rng.uniform(0, 0.5, n),
        "cut_edges":          rng.integers(10, 50, n),
    })
    if preserve_mode == "soft":
        df["score"] = rng.uniform(0, 1, n)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


class TestParetoSweepSkipRun:

    def _setup_fixtures(self, output_base: Path, penalties: list[float]) -> None:
        region_name = "R13_METROPOLITANA"
        for p in penalties:
            p_str = f"{p:.2f}".replace(".", "_")
            name = f"apc_soft_p{p_str}"
            ens_path = output_base / region_name / "redistritaje" / name / "ensemble_stats.csv"
            _make_ensemble_csv(ens_path, preserve_mode="soft", seed=int(p * 100))

    def test_exit_code_zero_with_fixtures(self, tmp_path):
        penalties = [0.0, 0.25]
        self._setup_fixtures(tmp_path, penalties)
        result = _run_script(
            "pareto_sweep.py",
            [
                "--output-dir", str(tmp_path),
                "--region", "13",
                "--skip-run",
                "--skip-viz",
                "--no-anchors",
                "--penalties", "0.0,0.25",
            ],
            str(tmp_path),
        )
        assert result.returncode == 0, (
            f"pareto_sweep.py --skip-run failed:\n{result.stderr}"
        )

    def test_results_csv_created(self, tmp_path):
        penalties = [0.0, 0.25]
        self._setup_fixtures(tmp_path, penalties)
        _run_script(
            "pareto_sweep.py",
            [
                "--output-dir", str(tmp_path),
                "--region", "13",
                "--skip-run",
                "--skip-viz",
                "--no-anchors",
                "--penalties", "0.0,0.25",
            ],
            str(tmp_path),
        )
        results_path = tmp_path / "R13_METROPOLITANA" / "pareto_sweep" / "pareto_sweep_results.csv"
        assert results_path.exists(), "pareto_sweep_results.csv not created"

    def test_results_csv_has_expected_rows(self, tmp_path):
        penalties = [0.0, 0.25]
        self._setup_fixtures(tmp_path, penalties)
        _run_script(
            "pareto_sweep.py",
            [
                "--output-dir", str(tmp_path),
                "--region", "13",
                "--skip-run",
                "--skip-viz",
                "--no-anchors",
                "--penalties", "0.0,0.25",
            ],
            str(tmp_path),
        )
        df = pd.read_csv(
            tmp_path / "R13_METROPOLITANA" / "pareto_sweep" / "pareto_sweep_results.csv"
        )
        assert len(df) == 2  # one row per penalty
        assert "is_pareto" in df.columns
        assert "point_type" in df.columns

    def test_no_data_no_output(self, tmp_path):
        """With --skip-run and no fixture files, the script prints a warning and exits 0."""
        result = _run_script(
            "pareto_sweep.py",
            [
                "--output-dir", str(tmp_path),
                "--region", "13",
                "--skip-run",
                "--skip-viz",
                "--no-anchors",
                "--penalties", "0.0",
            ],
            str(tmp_path),
        )
        assert result.returncode == 0
        # No output CSV should be created
        results_path = tmp_path / "R13_METROPOLITANA" / "pareto_sweep" / "pareto_sweep_results.csv"
        assert not results_path.exists()


# ── 4. run_chains.py: direct function tests ───────────────────────────────────

def _import_run_chains():
    """Import run_chains.py as a module using importlib."""
    script_path = SCRIPTS_DIR / "run_chains.py"
    spec = importlib.util.spec_from_file_location("run_chains", str(script_path))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_metricas_df(n: int = 100, seed: int = 0) -> pd.DataFrame:
    """Synthetic metricas_cadena.csv fixture."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "step":         np.arange(n),
        "cut_edges":    rng.integers(10, 50, n).astype(float),
        "max_dev_pct":  rng.uniform(1, 10, n),
    })


class TestRunChainsDirectFunctions:

    @pytest.fixture
    def mod(self):
        return _import_run_chains()

    def test_load_chain_metrics_reads_csv(self, tmp_path, mod):
        """load_chain_metrics returns one DataFrame per found seed directory."""
        chain_dir = str(tmp_path / "chains")
        n_chains = 2
        base_seed = 42
        for k in range(n_chains):
            seed = base_seed + k
            run_dir = tmp_path / "chains" / f"seed_{seed:04d}"
            run_dir.mkdir(parents=True)
            _make_metricas_df(seed=seed).to_csv(run_dir / "metricas_cadena.csv", index=False)

        cadenas = mod.load_chain_metrics(chain_dir, n_chains, base_seed)
        assert len(cadenas) == n_chains
        for df in cadenas:
            assert "cut_edges" in df.columns
            assert "max_dev_pct" in df.columns

    def test_load_chain_metrics_missing_files_skipped(self, tmp_path, mod):
        """Missing seed directories are silently skipped (not an error)."""
        cadenas = mod.load_chain_metrics(str(tmp_path / "nonexistent"), 3, 42)
        assert cadenas == []

    def test_run_convergence_diagnostics_produces_csv(self, tmp_path, mod):
        """run_convergence_diagnostics saves convergencia_diagnosticos.csv."""
        cadenas = [_make_metricas_df(seed=i) for i in range(3)]
        out_dir = str(tmp_path / "diag_out")

        mod.run_convergence_diagnostics(cadenas, out_dir)

        diag_csv = tmp_path / "diag_out" / "convergencia_diagnosticos.csv"
        assert diag_csv.exists(), "convergencia_diagnosticos.csv not created"

    def test_run_convergence_diagnostics_csv_columns(self, tmp_path, mod):
        cadenas = [_make_metricas_df(seed=i) for i in range(3)]
        out_dir = str(tmp_path / "diag_cols")
        df_diag = mod.run_convergence_diagnostics(cadenas, out_dir)

        assert isinstance(df_diag, pd.DataFrame)
        for col in ("metrica", "rhat", "convergido"):
            assert col in df_diag.columns, f"Missing column: {col}"

    def test_run_convergence_diagnostics_produces_trace_png(self, tmp_path, mod):
        cadenas = [_make_metricas_df(seed=i) for i in range(2)]
        out_dir = str(tmp_path / "diag_png")
        mod.run_convergence_diagnostics(cadenas, out_dir)
        assert (tmp_path / "diag_png" / "trace_plot.png").exists()
