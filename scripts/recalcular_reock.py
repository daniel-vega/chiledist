"""
scripts/recalcular_reock.py
============================
Recalcula la columna `reock` de ensemble_stats.csv tras el fix de
_minimum_bounding_circle_area() en chiledist/metrics.py: antes de ese fix,
el import de minimum_bounding_circle fallaba en shapely >= 2.0 y el cálculo
caía al fallback de minimum_rotated_rectangle (área/rectángulo en vez de
área/círculo).

Solo recalcula sobre los planes que ya tienen `pp_promedio` (la muestra de
~30 planes elegida al generar el ensemble) -- no sobre los 50.000 draws
completos, por costo computacional. polsby_popper no está afectado por el
bug; no se toca.

Uso:
    python scripts/recalcular_reock.py --base-dir . --regiones 13 --scenario legal
    python scripts/recalcular_reock.py --base-dir . --regiones 13 \\
        --scenarios legal,apc_free,apc_soft
"""

import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS_DIR)

import numpy as np
import pandas as pd

import chiledist as cd
from chiledist.rules.scenario_rules import SCENARIOS
# REGION_NOMBRES y parse_regiones ya existen en redistritaje.py -- se
# reutilizan aquí en vez de reimplementar la resolución de rutas/regiones.
from redistritaje import REGION_NOMBRES, parse_regiones


def _find_latest_run_dir(scenario_dir: str) -> str:
    """
    Run más reciente de un escenario. Convención ya establecida en
    redistritaje.py: run_{YYYYMMDD_HHMMSS}_{run_id[:8]} -- orden
    lexicográfico de los nombres de carpeta == orden cronológico.
    """
    candidatos = sorted(
        d for d in os.listdir(scenario_dir)
        if d.startswith("run_") and os.path.isdir(os.path.join(scenario_dir, d))
    )
    if not candidatos:
        raise FileNotFoundError(f"Ningún run_* encontrado en {scenario_dir}")
    return os.path.join(scenario_dir, candidatos[-1])


def _construir_gdf_decision(base_dir: str, region_code: int, decision_unit: str):
    """
    GDF a nivel de unidad de decisión (CUT o ID_DIST) en CRS métrico, con
    columna __unit_id__ que empata directamente contra unit_id de
    assignments.parquet. Replica la bifurcación de redistritaje.py
    (decision_unit == "CUT" -> contract_to_decision_units), sin la
    agregación de población (irrelevante para reock, que solo usa geometría).
    """
    distritos = cd.load_layer("distrital", base_dir=base_dir, regions=[region_code])
    if decision_unit == "CUT":
        gdf_dec = cd.contract_to_decision_units(distritos, decision_unit="CUT")
        # CUT es int64 en la capa cruda; unit_id en assignments.parquet es
        # string zero-padded a 5 dígitos -- normalize_cut() empareja ambos
        # formatos sin asumir que la región no tiene ceros a la izquierda.
        gdf_dec["__unit_id__"] = gdf_dec["CUT"].map(cd.normalize_cut)
    else:
        gdf_dec = distritos.copy()
        gdf_dec["__unit_id__"] = gdf_dec["ID_DIST"].astype(str)
    return gdf_dec.to_crs("EPSG:32719")


def _reock_de_plan(gdf_dec, assignments: pd.DataFrame, plan_id: int) -> float:
    """Reock promedio (media sobre distritos) del plan `plan_id`."""
    sub = assignments[assignments["draw"] == plan_id]
    asignacion = dict(zip(sub["unit_id"], sub["district"]))

    gdf_m = gdf_dec.copy()
    gdf_m["__d__"] = gdf_m["__unit_id__"].map(asignacion)
    df_p = gdf_m[gdf_m["__d__"].notna()]
    if df_p.empty:
        return np.nan

    dissolved = df_p.dissolve("__d__")
    r = cd.reock(dissolved)
    return float(r.mean()) if len(r) else np.nan


def procesar_escenario(base_dir: str, region_code: int, scenario_key: str) -> None:
    scenario_cfg = SCENARIOS[scenario_key]
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    scenario_dir = os.path.join(
        base_dir, "datos", region_name, "redistritaje", scenario_cfg.name
    )

    if not os.path.isdir(scenario_dir):
        print(f"  ⚠ No existe {scenario_dir} -- omitiendo.")
        return

    run_dir = _find_latest_run_dir(scenario_dir)
    print(f"\n{'='*70}")
    print(f"  {region_name} / {scenario_key} ({scenario_cfg.name})")
    print(f"  run: {os.path.basename(run_dir)}")
    print(f"{'='*70}")

    stats_path_run = os.path.join(run_dir, "ensemble_stats.csv")
    stats_path_out = os.path.join(scenario_dir, "ensemble_stats.csv")
    assignments_path = os.path.join(run_dir, "assignments.parquet")
    manifest_path = os.path.join(run_dir, "run_manifest.json")

    for p in (stats_path_run, assignments_path):
        if not os.path.exists(p):
            raise FileNotFoundError(p)

    stats = pd.read_csv(stats_path_run)
    n_filas_original = len(stats)
    assignments = pd.read_parquet(assignments_path)

    muestra = stats[stats["pp_promedio"].notna()]
    if muestra.empty:
        print("  ⚠ Ningún plan con pp_promedio -- nada que recalcular.")
        return

    if "reock" in stats.columns:
        reock_antes = stats["reock"].copy()
    else:
        reock_antes = pd.Series(np.nan, index=stats.index)
        stats["reock"] = np.nan

    gdf_dec = _construir_gdf_decision(base_dir, region_code, scenario_cfg.decision_unit)

    nuevos = {}
    for idx, plan_id in zip(muestra.index, muestra["plan_id"]):
        nuevos[idx] = _reock_de_plan(gdf_dec, assignments, int(plan_id))

    reock_despues = reock_antes.copy()
    for idx, valor in nuevos.items():
        reock_despues.loc[idx] = valor

    # ── Validaciones ─────────────────────────────────────────────────────
    calculados = pd.Series(nuevos).dropna()
    fuera_de_rango = calculados[(calculados < 0) | (calculados > 1 + 1e-6)]
    if not fuera_de_rango.empty:
        raise ValueError(
            f"reock fuera de [0,1] en plan_id={list(fuera_de_rango.index)}: "
            f"{fuera_de_rango.tolist()}"
        )

    if len(stats) != n_filas_original:
        raise AssertionError(
            "El número de filas de ensemble_stats.csv cambió -- abortando sin escribir."
        )

    idx_muestreados = list(nuevos.keys())
    comparables = pd.DataFrame({
        "antes": reock_antes.loc[idx_muestreados],
        "despues": reock_despues.loc[idx_muestreados],
    }).dropna()
    if not comparables.empty and np.allclose(
        comparables["antes"], comparables["despues"], atol=1e-9
    ):
        print(
            "  WARNING: reock_antes == reock_despues en todos los planes "
            "muestreados. ¿El bug ya estaba corregido antes de correr este "
            "script? No se sobreescribe ensemble_stats.csv."
        )
        return

    # ── Tabla antes/después (muestra de 5) ──────────────────────────────
    tabla = pd.DataFrame({
        "plan_id": muestra["plan_id"].values,
        "reock_antes": reock_antes.loc[muestra.index].values,
        "reock_despues": reock_despues.loc[muestra.index].values,
        "pp_promedio": muestra["pp_promedio"].values,
    })
    print(f"\n  Muestra (5 de {len(tabla)} planes recalculados):")
    print(tabla.head(5).to_string(index=False))

    # ── Escribir ─────────────────────────────────────────────────────────
    stats["reock"] = reock_despues
    stats.to_csv(stats_path_run, index=False)
    stats.to_csv(stats_path_out, index=False)
    print(f"\n  Sobreescrito: {stats_path_run}")
    print(f"  Sobreescrito: {stats_path_out}")

    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["reock_recalculated"] = True
        manifest["reock_fix_date"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds")
        manifest["reock_fix_reason"] = (
            "metrics.py bug: minimum_bounding_circle import fallback usaba "
            "minimum_rotated_rectangle en shapely >= 2.0"
        )
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
        print(f"  Actualizado: {manifest_path}")
    else:
        print(f"  ⚠ No existe {manifest_path} -- no se actualizó metadata de fix.")


def main():
    p = argparse.ArgumentParser(
        description="Recalcula reock en ensemble_stats.csv tras el fix de metrics.py."
    )
    p.add_argument("--base-dir", default=".",
                   help="Directorio raíz con SHP_APC2023_R* y datos/")
    p.add_argument("--regiones", default="13",
                   help="Regiones: número o lista separada por coma (5,8,13)")
    p.add_argument("--scenario", default=None, choices=list(SCENARIOS.keys()))
    p.add_argument("--scenarios", default=None,
                   help="Lista separada por coma, ej. legal,apc_free,apc_soft")
    args = p.parse_args()

    if not args.scenario and not args.scenarios:
        p.error("Debes pasar --scenario o --scenarios")
    if args.scenario and args.scenarios:
        p.error("Usa --scenario o --scenarios, no ambos")

    scenario_keys = (
        [args.scenario] if args.scenario
        else [s.strip() for s in args.scenarios.split(",")]
    )
    for key in scenario_keys:
        if key not in SCENARIOS:
            p.error(f"Escenario desconocido: {key!r}. Opciones: {list(SCENARIOS.keys())}")

    regiones = parse_regiones(args.regiones)

    for region_code in regiones:
        for scenario_key in scenario_keys:
            procesar_escenario(args.base_dir, region_code, scenario_key)


if __name__ == "__main__":
    main()
