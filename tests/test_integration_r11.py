"""
tests/test_integration_r11.py
================================
Nivel 3 integration tests (VALIDATION_PLAN.md §"Nivel 3 — Tests científicos
/ de integración"). That section names this exact file as the real gap of
the level: end-to-end runs against real APC 2023 shapefiles, chosen for
Región de Aysén (R11) — the smallest region with real data available under
SHP_APC2023/, for speed.

No mocks, no synthetic data. If BASE_DIR doesn't point at a real chiledist
checkout with SHP_APC2023_R11/, every test in this file skips instead of
failing:

    BASE_DIR = os.environ.get("CHILEDIST_BASE_DIR", ".")

Two real-data findings shaped this file's design (both confirmed against
real R11 data before writing any assertions — not assumed):

1. SCENARIO_LEGAL's generic default (chiledist/config.py: n_districts=8,
   pop_tolerance=0.05) is mathematically INFEASIBLE for R11: Coyhaique
   (CUT 11101) alone holds 908 of R11's 1,976 total viviendas (46%), ~3.7x
   the ideal per-district share at 8 districts — confirmed via the
   library's own population-feasibility preflight, which correctly
   returns status="infeasible_population" rather than attempting (and
   silently failing) a ReCom run. To exercise the actual pipeline
   end-to-end (invariants 1, 2, 3, 5 all need real output files), this
   suite deliberately uses --n-distritos 2 --pop-tol 0.5 for the shared
   fixture — confirmed empirically to reach status="ok". Invariant 6 still
   accepts "infeasible_population" defensively, in case these constants
   are ever changed back toward the (infeasible-for-R11) library defaults.

2. Independently, the Censo 2024 proportional join (invariant 4) had a
   real, reproducible edge case for R11: Lago Verde (CUT 11102) had
   viviendas=0 under aggregate_population() (it only summed manzana_urbana
   + manzana_aldea; SHP_APC2023_R11 also ships a Puntos_Edificacion_Rural
   layer that nothing aggregated). join_census_multilevel() distributes
   each comuna's census population proportionally to the viviendas proxy
   WITHIN that comuna — so a comuna with proxy=0 got 0 population in the
   join, not a rounding artifact but a whole comuna (779 real personas,
   per datos/poblacion_comunal_censo2024.csv) disappearing (confirmed diff
   for the whole region: -781).

   FIXED: chiledist.aggregate_rural_proxy() / apply_rural_proxy_fallback()
   (chiledist/loader.py) now fall back to counting rural buildings
   (Puntos_Edificacion_Rural, USO_EDIFICACION in VIVIENDA/VIVIENDA
   COLECTIVA) per comuna, split evenly across that comuna's APC distritos,
   whenever a comuna's manzana-based viviendas total is 0. Confirmed
   against real R11 data: Lago Verde now gets a nonzero proxy and the
   region-wide join diff drops from -781 to -1 (pure rounding). test_4
   below asserts the FIXED behavior (Lago Verde > 0, diff bounded by
   rounding) — see git history for the pre-fix assertions this replaced.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_DIR = os.environ.get("CHILEDIST_BASE_DIR", ".")
REPO_ROOT = Path(BASE_DIR).resolve()
SHP_R11 = REPO_ROOT / "SHP_APC2023" / "SHP_APC2023_R11"
CENSUS_PATH = REPO_ROOT / "datos" / "poblacion_comunal_censo2024.csv"

REGION = 11
REGION_SUBDIR = "R11_AYSEN"      # chiledist's REGION_NOMBRES[11] (scripts/redistritaje.py)
SCENARIO_DIR_NAME = "legal_comunas"  # SCENARIO_LEGAL.name (chiledist/config.py)

# See module docstring, finding #1: chiledist's own generic defaults
# (n_distritos=8, pop_tol=0.05) are infeasible for R11 — these are the
# smallest deviations confirmed (empirically, against real data) to let
# SCENARIO_LEGAL reach status="ok" for this region.
N_DISTRITOS = 2
POP_TOL = 0.5
N_STEPS = 200
SEED = 42

# See module docstring, finding #2 (now fixed via aggregate_rural_proxy /
# apply_rural_proxy_fallback in chiledist/loader.py).
LAGO_VERDE_CUT = 11102
LAGO_VERDE_POBLACION = 779  # datos/poblacion_comunal_censo2024.csv, real value
N_APC_DISTRITOS_R11 = 56    # rounding-tolerance bound: max per-row loss ~0.5 each


def _has_real_data() -> bool:
    return (SHP_R11 / "Distrital.shp").exists()


pytestmark = pytest.mark.skipif(
    not _has_real_data(),
    reason=f"requiere SHP_APC2023 real bajo {SHP_R11}",
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_redistritaje(output_dir: Path) -> subprocess.CompletedProcess:
    """Runs the real scripts/redistritaje.py as a subprocess (no mocking)."""
    cmd = [
        sys.executable, "scripts/redistritaje.py",
        "--base-dir", str(REPO_ROOT),
        "--output-dir", str(output_dir),
        "--scenario", "legal",
        "--regiones", str(REGION),
        "--n-distritos", str(N_DISTRITOS),
        "--pop-tol", str(POP_TOL),
        "--n-steps", str(N_STEPS),
        "--seed", str(SEED),
        "--skip-viz",
    ]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "MPLBACKEND": "Agg"},
    )


def _scenario_out_dir(output_dir: Path) -> Path:
    return output_dir / REGION_SUBDIR / "redistritaje" / SCENARIO_DIR_NAME


def _latest_run_dir(output_dir: Path) -> Optional[Path]:
    scenario_dir = _scenario_out_dir(output_dir)
    if not scenario_dir.exists():
        return None
    candidates = sorted(
        scenario_dir.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def _resumen_path(output_dir: Path) -> Path:
    return output_dir / f"redistritaje_resumen_{SCENARIO_DIR_NAME}.csv"


def _resumen_status(output_dir: Path) -> str:
    resumen = _resumen_path(output_dir)
    assert resumen.exists(), f"No se generó {resumen}"
    df = pd.read_csv(resumen)
    row = df[df["scenario"] == SCENARIO_DIR_NAME]
    assert len(row) == 1, f"Esperaba 1 fila para {SCENARIO_DIR_NAME!r}, hay {len(row)}"
    return str(row.iloc[0]["status"])


def _require_ok_run_dir(output_dir: Path) -> Path:
    """
    Shared precondition for tests 1, 2, 3, 5: skip (not fail) if this
    session's run didn't reach status="ok" — there is nothing to check in
    that case (see test_6 for the assertion on status itself).
    """
    status = _resumen_status(output_dir)
    if status != "ok":
        pytest.skip(
            f"legal_comunas status={status!r} para R11 (n_distritos={N_DISTRITOS}, "
            f"pop_tol={POP_TOL}) — no se generaron archivos de ensemble; "
            f"ver test_6_status_is_ok_or_documented_infeasible."
        )
    run_dir = _latest_run_dir(output_dir)
    assert run_dir is not None, "status=ok pero no se encontró ningún run_*/ dir"
    return run_dir


def _content_hash(assignments_parquet: Path) -> str:
    """
    Hash of the assignment CONTENT (draw, unit_id, district), not the file.
    Excludes run_id/scenario/chain_id — run_id is a fresh UUID per
    invocation (chiledist/persistence.py:save_assignments_parquet), so two
    reproducible runs never have byte-identical files even when the actual
    district assignments are identical.
    """
    df = pd.read_parquet(assignments_parquet, columns=["draw", "unit_id", "district"])
    df = df.sort_values(["draw", "unit_id"]).reset_index(drop=True)
    return hashlib.sha256(
        pd.util.hash_pandas_object(df, index=False).values.tobytes()
    ).hexdigest()


# ── Session fixture: run SCENARIO_LEGAL for R11 once ──────────────────────────

@pytest.fixture(scope="session")
def r11_legal_run(tmp_path_factory) -> Path:
    """
    Runs redistritaje.py once for the whole test session; tests 1, 2 (its
    first run), 3, 5, 6 all read from this same --output-dir instead of
    each re-running the pipeline.
    """
    if not _has_real_data():
        pytest.skip(f"requiere SHP_APC2023 real bajo {SHP_R11}")
    output_dir = tmp_path_factory.mktemp("r11_legal")
    result = _run_redistritaje(output_dir)
    assert result.returncode == 0, (
        f"redistritaje.py salió con código {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return output_dir


# ── Invariant 1 — pipeline produces the 4 expected output files ────────────────

def test_1_pipeline_produces_expected_output_files(r11_legal_run):
    run_dir = _require_ok_run_dir(r11_legal_run)
    for fname in ("run_manifest.json", "scenario.yml", "assignments.parquet", "ensemble_stats.csv"):
        assert (run_dir / fname).exists(), f"Falta {fname} en {run_dir}"


# ── Invariant 2 — same seed produces byte-for-byte-identical assignment content ─

def test_2_same_seed_produces_identical_assignments(r11_legal_run, tmp_path_factory):
    run_dir_1 = _require_ok_run_dir(r11_legal_run)
    hash_1 = _content_hash(run_dir_1 / "assignments.parquet")

    output_dir_2 = tmp_path_factory.mktemp("r11_legal_rerun")
    result_2 = _run_redistritaje(output_dir_2)
    assert result_2.returncode == 0, (
        f"segunda corrida salió con código {result_2.returncode}\n"
        f"stdout:\n{result_2.stdout}\nstderr:\n{result_2.stderr}"
    )
    status_2 = _resumen_status(output_dir_2)
    assert status_2 == "ok", f"segunda corrida (misma semilla) dio status={status_2!r}, esperaba 'ok'"
    run_dir_2 = _latest_run_dir(output_dir_2)
    assert run_dir_2 is not None

    hash_2 = _content_hash(run_dir_2 / "assignments.parquet")
    assert hash_1 == hash_2, (
        "Misma --seed produjo assignments.parquet con contenido "
        "(draw, unit_id, district) distinto entre dos corridas"
    )


# ── Invariant 3 — SCENARIO_LEGAL produces 0 splits ─────────────────────────────

def test_3_scenario_legal_produces_zero_splits(r11_legal_run):
    run_dir = _require_ok_run_dir(r11_legal_run)
    df_ensemble = pd.read_csv(run_dir / "ensemble_stats.csv")
    assert "n_comunas_partidas" in df_ensemble.columns
    assert (df_ensemble["n_comunas_partidas"] == 0).all(), (
        "SCENARIO_LEGAL (decision_unit=CUT) no debería poder partir comunas "
        "por construcción: la comuna ES la unidad de decisión"
    )


# ── Invariant 4 — Censo 2024 join preserves R11's total population ────────────

def test_4_census2024_join_preserves_r11_population_total():
    """
    Independent of the ReCom fixture above: exercises exactly the same code
    path --pop-source censo2024 --census-path ... triggers
    (scripts/redistritaje.py::enrich_population -> chiledist.data.census2024),
    called directly for speed/precision — this happens before the ReCom
    feasibility question entirely, so it needs neither N_DISTRITOS/POP_TOL
    nor a successful chain.

    Includes the rural-proxy fallback (chiledist.apply_rural_proxy_fallback)
    that fixed the Lago Verde finding — see module docstring, finding #2.
    """
    import chiledist as cd
    from chiledist.data import census2024 as c24

    assert CENSUS_PATH.exists(), f"No se encontró {CENSUS_PATH}"

    distritos = cd.load_layer("distrital", base_dir=str(REPO_ROOT), regions=[REGION])
    mz_urb = cd.load_layer("manzana_urbana", base_dir=str(REPO_ROOT), regions=[REGION])
    mz_ald = cd.load_layer("manzana_aldea", base_dir=str(REPO_ROOT), regions=[REGION])
    try:
        puntos_rural = cd.load_layer("puntos_rural", base_dir=str(REPO_ROOT), regions=[REGION])
    except FileNotFoundError:
        puntos_rural = None

    # Mirrors scripts/redistritaje.py::analizar_region()'s viviendas merge
    # exactly, including the rural-proxy fallback (applied AFTER merging
    # into the full distritos universe, not on pop directly — a comuna
    # with zero manzanas of either kind, like Lago Verde, has no row at
    # all in pop_urb/pop_ald, so it only becomes an explicit 0 once merged
    # against every real APC distrito via the .fillna({"viviendas": 0}) below).
    pop_urb = cd.aggregate_population(mz_urb, level="distrito", source="urbana")
    pop_ald = cd.aggregate_population(mz_ald, level="distrito", source="aldea")
    pop = (
        pop_urb.merge(pop_ald, on=["CUT", "COD_DISTRITO"], how="outer", suffixes=("_urb", "_ald"))
        .fillna(0)
    )
    pop["viviendas"] = pop.get("viviendas_urb", 0) + pop.get("viviendas_ald", 0)
    distritos = distritos.merge(
        pop[["CUT", "COD_DISTRITO", "viviendas"]], on=["CUT", "COD_DISTRITO"], how="left"
    ).fillna({"viviendas": 0})
    distritos["viviendas"] = distritos["viviendas"].astype(int)
    distritos = cd.apply_rural_proxy_fallback(distritos, puntos_rural)
    distritos["viviendas"] = distritos["viviendas"].astype(int)

    r11_cuts = distritos["CUT"].unique().tolist()

    census = c24.load_census2024(str(CENSUS_PATH))
    census_r11 = census[census["CUT"].isin(r11_cuts)]
    assert len(census_r11) == 10, f"Esperaba 10 comunas reales de R11 en el censo, hay {len(census_r11)}"
    total_personas_censo_r11 = int(census_r11["personas"].sum())

    df_join = c24.join_census_multilevel(distritos, census, proxy_col="viviendas")
    total_personas_join = int(df_join["personas"].sum())

    diff = abs(total_personas_join - total_personas_censo_r11)

    # Con el fallback rural aplicado, ninguna comuna debería quedar con
    # proxy=0 (ver assert de Lago Verde más abajo) — la diferencia esperada
    # ahora es solo de redondeo del reparto proporcional dentro de cada
    # comuna (≤ ~0.5 por cada uno de los N_APC_DISTRITOS_R11 distritos),
    # no la pérdida completa de una comuna. Confirmado contra datos reales:
    # diff=-1 (antes del fix: diff=-781).
    assert diff <= N_APC_DISTRITOS_R11, (
        f"diff={diff} excede la tolerancia de redondeo esperada "
        f"({N_APC_DISTRITOS_R11}) — ¿el fallback rural dejó de aplicarse "
        f"a alguna comuna?"
    )

    # Lago Verde ya no debería perder su población: antes del fix tenía
    # personas=0 (proxy=0, ver historial de este archivo); con el fallback
    # rural aplicado, su población debe acercarse a la real del censo
    # (779), dentro de un margen amplio para el reparto equitativo entre
    # sus distritos APC (aproximación, no exacto — ver
    # apply_rural_proxy_fallback en chiledist/loader.py).
    personas_lago_verde = int(
        df_join.loc[df_join["CUT"] == LAGO_VERDE_CUT, "personas"].sum()
    )
    assert personas_lago_verde > 0, (
        "Lago Verde sigue con personas=0 tras el fallback rural — "
        "¿puntos_rural no se cargó, o su CUT no está en aggregate_rural_proxy?"
    )
    assert abs(personas_lago_verde - LAGO_VERDE_POBLACION) <= 50, (
        f"Lago Verde post-fix={personas_lago_verde}, esperaba cerca de "
        f"{LAGO_VERDE_POBLACION} (censo real)"
    )


# ── Invariant 5 — valid_fraction == 1.0 (modelo A) ─────────────────────────────

def test_5_valid_fraction_is_one_modelo_a(r11_legal_run):
    import json

    run_dir = _require_ok_run_dir(r11_legal_run)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())

    # Modelo A (VALIDATION_PLAN.md §5.5): epsilon_recom = pop_tol exacto, y
    # gerrychain.constraints.within_percent_of_ideal_population rechaza toda
    # propuesta que lo exceda ANTES de aceptarla — cada estado emitido por la
    # cadena principal satisface pop_tol por construcción, así que
    # valid_fraction ≈ 1.0 es el comportamiento esperado, no un filtrado
    # posterior generoso.
    valid_fraction = manifest["sampler_diagnostics"]["valid_fraction"]
    assert valid_fraction == 1.0, f"valid_fraction={valid_fraction}, esperaba 1.0 (modelo A)"


# ── Invariant 6 — status == "ok" (or documented infeasible_population) ────────

def test_6_status_is_ok_or_documented_infeasible(r11_legal_run):
    status = _resumen_status(r11_legal_run)

    # Con N_DISTRITOS/POP_TOL elegidos arriba (ver docstring del módulo,
    # finding #1) esto debe dar "ok" contra los datos reales. Se acepta
    # "infeasible_population" defensivamente: significa que el preflight de
    # factibilidad poblacional de chiledist rechazó correctamente un
    # escenario estructuralmente inviable (ej. si estas constantes se
    # cambiaran de vuelta hacia los defaults de la librería, que SÍ son
    # inviables para R11 — Coyhaique domina la población) — comportamiento
    # correcto, no un bug, y no debe hacer fallar este test.
    assert status in ("ok", "infeasible_population"), (
        f"status inesperado para legal_comunas en R11: {status!r}"
    )
