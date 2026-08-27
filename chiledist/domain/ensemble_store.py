"""
domain.ensemble_store
========================
Carga de ensembles desde disco y visibilidad de su completitud — capa 0 (Domain).

I/O puro: lee ``ensemble_stats.csv`` y ``scenario_status.json`` por
escenario/región y describe qué tan completa está la comparación
resultante (``comparison_status``, ``ranking_scope``). No compara ni
puntúa — eso vive en ``inference.comparison`` y ``evaluation.scoring``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

_REGION_NOMBRES = {
    1: "R01_TARAPACA",    2: "R02_ANTOFAGASTA",
    3: "R03_ATACAMA",     4: "R04_COQUIMBO",
    5: "R05_VALPARAISO",  6: "R06_OHIGGINS",
    7: "R07_MAULE",       8: "R08_BIOBIO",
    9: "R09_ARAUCANIA",  10: "R10_LOS_LAGOS",
    11: "R11_AYSEN",     12: "R12_MAGALLANES",
    13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS",
    15: "R15_ARICA",     16: "R16_NUBLE",
}


# ──────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ──────────────────────────────────────────────────────────────────────────────

def load_ensembles_from_disk(
    output_base: str,
    region_code: Union[int, str],
    scenario_names: List[str],
    run_id: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Lee ensemble_stats.csv para cada escenario desde disco.

    Parameters
    ----------
    output_base : str
        Directorio base de salida (contiene datos/<REGION>/redistritaje/…).
    region_code : int | str
        Código de región (int) o nombre de subcarpeta (str).
    scenario_names : list[str]
        Nombres de escenarios (subcarpetas en redistritaje/).
    run_id : str, opcional
        Si se indica, carga solo el run cuyo directorio contiene ese run_id
        (busca subdirectorios run_*_{run_id[:8]} o run_id completo).
        Si es None (default), lee ensemble_stats.csv de la raíz del escenario
        (comportamiento retrocompatible).

    Returns
    -------
    dict {scenario_name: DataFrame} — solo los encontrados en disco.
    """
    if isinstance(region_code, int):
        region_name = _REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    else:
        region_name = str(region_code)

    ensembles: Dict[str, pd.DataFrame] = {}
    for sc_name in scenario_names:
        sc_dir = Path(output_base) / region_name / "redistritaje" / sc_name

        if run_id is not None:
            # Buscar el subdirectorio run_* que corresponde al run_id
            path = _find_run_ensemble(sc_dir, run_id)
        else:
            # Comportamiento retrocompatible: leer de la raíz del escenario
            path = sc_dir / "ensemble_stats.csv"

        if path is not None and path.exists():
            try:
                ensembles[sc_name] = pd.read_csv(path)
            except Exception as e:
                print(f"  ⚠ No se pudo leer {path}: {e}")
        else:
            if run_id is not None:
                print(f"  ⚠ No encontrado run_id={run_id[:8]}… en {sc_dir}")
            else:
                print(f"  ⚠ No encontrado: {sc_dir / 'ensemble_stats.csv'}")
    return ensembles


def _find_run_ensemble(sc_dir: Path, run_id: str) -> Optional[Path]:
    """
    Busca ensemble_stats.csv dentro del subdirectorio run_* que coincide
    con run_id (primeros 8 caracteres o UUID completo).
    """
    if not sc_dir.exists():
        return None

    run_id_short = run_id[:8]
    run_id_full  = run_id.replace("-", "")[:8]  # UUID sin guiones, primeros 8

    for entry in sorted(sc_dir.iterdir(), reverse=True):  # más reciente primero
        if not entry.is_dir() or not entry.name.startswith("run_"):
            continue
        name = entry.name
        # Acepta tanto run_id completo como prefijo de 8 chars
        if run_id in name or run_id_short in name or run_id_full in name:
            candidate = entry / "ensemble_stats.csv"
            if candidate.exists():
                return candidate

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Visibilidad de escenarios sin ensemble válido (infeasible_population,
# sin_particion, u otro status != "ok") y completitud de la comparación
# ──────────────────────────────────────────────────────────────────────────────

def load_scenario_statuses_from_disk(
    output_base: str,
    region_code: Union[int, str],
    scenario_names: List[str],
) -> Dict[str, dict]:
    """
    Lee scenario_status.json para escenarios que no produjeron un
    ensemble_stats.csv válido (ej. infeasible_population, sin_particion).

    scripts/compare_scenarios.py escribe este archivo con el dict de
    resultado completo de analizar_region() cada vez que status != "ok",
    preservando status, reason y el resto del diagnóstico (ej. los campos
    del preflight de factibilidad poblacional).

    Returns
    -------
    dict {scenario_name: status_dict} — solo los que tienen el archivo.
    """
    if isinstance(region_code, int):
        region_name = _REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    else:
        region_name = str(region_code)

    statuses: Dict[str, dict] = {}
    for sc_name in scenario_names:
        path = Path(output_base) / region_name / "redistritaje" / sc_name / "scenario_status.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    statuses[sc_name] = json.load(f)
            except Exception as e:
                print(f"  ⚠ No se pudo leer {path}: {e}")
    return statuses


def build_scenario_overview(
    scenario_names: List[str],
    ensembles: Dict[str, pd.DataFrame],
    statuses: Optional[Dict[str, dict]] = None,
) -> pd.DataFrame:
    """
    Tabla con una fila por cada escenario ESPERADO (`scenario_names`),
    visible tenga o no un ensemble válido.

    Columnas: escenario, status, reason, included_in_scoring, n_planes.

    Un escenario con ensemble válido tiene status="ok" e
    included_in_scoring=True. Uno sin ensemble válido conserva su status y
    reason reales (desde `statuses`, ver load_scenario_statuses_from_disk)
    y queda con included_in_scoring=False — nunca recibe score artificial,
    NaN relleno, ni entra al ranking de rank_scenarios().
    """
    statuses = statuses or {}
    rows = []
    for sc_name in scenario_names:
        if sc_name in ensembles:
            rows.append({
                "escenario":           sc_name,
                "status":              "ok",
                "reason":              None,
                "included_in_scoring": True,
                "n_planes":            len(ensembles[sc_name]),
            })
        else:
            st = statuses.get(sc_name, {})
            rows.append({
                "escenario":           sc_name,
                "status":              st.get("status", "sin_datos"),
                "reason":              st.get("reason"),
                "included_in_scoring": False,
                "n_planes":            0,
            })
    return pd.DataFrame(rows)


def assess_comparison_completeness(
    scenario_names: List[str],
    ensembles: Dict[str, pd.DataFrame],
    baseline: str = "legal_comunas",
) -> Dict[str, Any]:
    """
    Resume si la comparación entre `scenario_names` está completa.

    comparison_status="COMPLETE" solo si TODOS los escenarios esperados
    tienen ensemble válido; en cualquier otro caso "INCOMPLETE". El ranking
    entre los escenarios con ensemble válido puede calcularse igual
    (rank_scenarios sigue recibiendo solo esos), pero ranking_scope queda
    en "partial" — es descriptivo, no la comparación H1 completa — en vez
    de "full".

    Returns
    -------
    dict con comparison_status, expected_scenarios, valid_ensembles,
    missing_baseline (nombre del baseline si le falta ensemble válido, o
    None) y ranking_scope.
    """
    expected = len(scenario_names)
    valid    = sum(1 for s in scenario_names if s in ensembles)
    complete = valid == expected

    missing_baseline = (
        baseline if (baseline in scenario_names and baseline not in ensembles)
        else None
    )

    return {
        "comparison_status":  "COMPLETE" if complete else "INCOMPLETE",
        "expected_scenarios": expected,
        "valid_ensembles":    valid,
        "missing_baseline":   missing_baseline,
        "ranking_scope":      "full" if complete else "partial",
    }
