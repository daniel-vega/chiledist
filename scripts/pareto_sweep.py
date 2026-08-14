"""
scripts/pareto_sweep.py
=======================
Análisis de la frontera Pareto en el espacio (balance poblacional × comunas
partidas) variando el parámetro split_penalty del escenario apc_soft.

Implementa H2: ¿Existe un tradeoff Pareto-eficiente entre balance poblacional
e integridad comunal? ¿Qué región del espacio de diseño es Pareto-dominada?

Cada punto del espacio es una configuración (escenario, penalización). El
valor representativo de cada punto es la mediana del ensemble generado por
esa configuración. Los puntos no-dominados en el sentido de Pareto forman
la frontera eficiente.

Configuraciones evaluadas
--------------------------
    Anclajes fijos (márgenes del tradeoff):
        legal          → 0 comunas partidas, balance puntual de la ley vigente
        apc_strict     → 0 comunas partidas, balance APC con restricción hard
        apc_free       → máxima flexibilidad, mayor riesgo de partición
    Barrido continuo (pendiente de la frontera):
        apc_soft_p{X}  → apc_soft con split_penalty = X

Salidas en datos/<REGION>/pareto_sweep/:
    pareto_sweep_results.csv    — tabla completa (todas configuraciones + is_pareto)
    pareto_frontier.csv         — solo configuraciones Pareto-óptimas
    pareto_tradeoff.png         — scatter + frontera Pareto + anclajes
    pareto_pop_afectada.png     — si pop_afectada_pct está disponible

Uso:
    python scripts/pareto_sweep.py --base-dir . --region 13
    python scripts/pareto_sweep.py --base-dir . --region 13 \\
        --penalties 0.0,0.1,0.25,0.5,1.0,2.0 \\
        --n-steps 5000 --n-distritos 8
    python scripts/pareto_sweep.py --base-dir . --region 13 \\
        --skip-run    # solo leer resultados existentes y graficar
"""

import argparse
import dataclasses
import os
import sys
import warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib.util
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

import chiledist as cd
from chiledist.config import ScenarioConfig, SCENARIOS

REGION_NOMBRES = {
    1:  "R01_TARAPACA",    2:  "R02_ANTOFAGASTA",
    3:  "R03_ATACAMA",     4:  "R04_COQUIMBO",
    5:  "R05_VALPARAISO",  6:  "R06_OHIGGINS",
    7:  "R07_MAULE",       8:  "R08_BIOBIO",
    9:  "R09_ARAUCANIA",   10: "R10_LOS_LAGOS",
    11: "R11_AYSEN",       12: "R12_MAGALLANES",
    13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS",
    15: "R15_ARICA",       16: "R16_NUBLE",
}

PENALTIES_DEFAULT = [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]

# Marcadores por tipo de escenario para el scatter
MARKER_MAP = {
    "vigente":                "s",    # cuadrado
    "contrafactual_fuerte":   "^",    # triángulo arriba
    "contrafactual_intermedio": "o",  # círculo
    "control_metodologico":   "D",    # diamante
}
COLOR_MAP = {
    "vigente":                "#1A5C8A",
    "contrafactual_fuerte":   "#D85A30",
    "contrafactual_intermedio": "#1D9E75",
    "control_metodologico":   "#BA7517",
}


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Barrido Pareto: balance poblacional vs. comunas partidas."
    )
    p.add_argument("--base-dir",    default=".",
                   help="Directorio raíz con SHP_APC2023_R*")
    p.add_argument("--output-dir",  default=None,
                   help="Directorio base de salida (default: <base-dir>/datos)")
    p.add_argument("--region",      type=int, default=13,
                   help="Código de región (default: 13)")
    p.add_argument("--penalties",   default=None,
                   help="Lista de split_penalty para apc_soft, "
                        "separados por coma (default: 0.0,0.1,0.25,0.5,1.0,2.0)")
    p.add_argument("--n-distritos", type=int, default=None,
                   help="Número de particiones territoriales a generar (NO "
                        "la magnitud electoral 3-8 de Ley 20.840). Default: "
                        "n_districts de cada escenario/anclaje del barrido — "
                        "no se homogeneiza entre configuraciones salvo que "
                        "se pase este flag explícitamente.")
    p.add_argument("--pop-tol",     type=float, default=0.15)
    p.add_argument("--n-steps",     type=int, default=5000)
    p.add_argument("--seed",        type=int, default=42)
    p.add_argument("--skip-run",    action="store_true",
                   help="Solo leer resultados existentes (no correr redistritaje)")
    p.add_argument("--skip-viz",    action="store_true")
    p.add_argument("--no-anchors",  action="store_true",
                   help="Omitir escenarios anclaje (legal, apc_strict, apc_free)")
    return p.parse_args()


def parse_penalties(s: str | None) -> list[float]:
    if s is None:
        return PENALTIES_DEFAULT
    return [float(x.strip()) for x in s.split(",")]


# ──────────────────────────────────────────────────────────────────────────────
# Construir lista de escenarios del barrido
# ──────────────────────────────────────────────────────────────────────────────

def build_sweep_scenarios(penalties: list[float], include_anchors: bool) -> list[ScenarioConfig]:
    scenarios = []

    if include_anchors:
        # legal: régimen vigente (comunas intactas por ley)
        scenarios.append(SCENARIOS["legal"])
        # apc_strict: control metodológico (APC, comunas preservadas hard)
        scenarios.append(SCENARIOS["apc_strict"])
        # apc_free: contrafactual fuerte (sin restricción de partición)
        scenarios.append(SCENARIOS["apc_free"])

    # Barrido de apc_soft con distintas penalizaciones
    base_soft = SCENARIOS["apc_soft"]
    for penalty in sorted(set(penalties)):
        # Nombre distinto por penalización para tener directorios separados
        p_str = f"{penalty:.2f}".replace(".", "_")
        variant = dataclasses.replace(
            base_soft,
            name=f"apc_soft_p{p_str}",
            description=(
                f"Barrido Pareto: apc_soft con split_penalty={penalty:.2f}"
            ),
            split_penalty=penalty,
        )
        scenarios.append(variant)

    return scenarios


# ──────────────────────────────────────────────────────────────────────────────
# Cargar analizar_region desde redistritaje.py
# ──────────────────────────────────────────────────────────────────────────────

def _load_analizar_region():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "redistritaje.py")
    spec = importlib.util.spec_from_file_location("redistritaje", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.analizar_region


# ──────────────────────────────────────────────────────────────────────────────
# Ejecutar o cargar un escenario
# ──────────────────────────────────────────────────────────────────────────────

def run_or_load(
    scenario: ScenarioConfig,
    region_code: int,
    base_dir: str,
    output_base: str,
    n_distritos: int | None,
    pop_tol: float,
    n_steps: int,
    seed: int,
    skip_run: bool,
    skip_viz: bool,
    analizar_region,
) -> pd.DataFrame | None:
    """
    Ejecuta redistritaje para el escenario (o carga el CSV existente si
    skip_run=True o el archivo ya existe).
    Devuelve el DataFrame de ensemble_stats, o None si falló.

    n_distritos: si es None, se usa scenario.n_districts (cada punto del
    barrido — anclajes y variantes apc_soft_pX — conserva el suyo); si se
    pasa explícito, se aplica a este escenario también.
    """
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    ens_path = os.path.join(
        output_base, region_name, "redistritaje", scenario.name,
        "ensemble_stats.csv",
    )

    if skip_run and not os.path.exists(ens_path):
        print(f"  ⚠ {scenario.name}: sin datos existentes (--skip-run activo)")
        return None

    if not skip_run:
        n_distritos_efectivo = (
            n_distritos if n_distritos is not None else scenario.n_districts
        )
        sc = dataclasses.replace(
            scenario,
            n_districts=n_distritos_efectivo,
            pop_tolerance=pop_tol,
            n_steps=n_steps,
            seed=seed,
        )
        try:
            analizar_region(
                region_code=region_code,
                base_dir=base_dir,
                output_base=output_base,
                n_distritos=n_distritos_efectivo,
                pop_tol=pop_tol,
                n_steps=n_steps,
                seed=seed,
                skip_viz=skip_viz,
                scenario=sc,
            )
        except Exception as e:
            import traceback
            print(f"  ⚠ Error en {scenario.name}: {e}")
            traceback.print_exc()
            return None

    if not os.path.exists(ens_path):
        print(f"  ⚠ {scenario.name}: no se generó ensemble_stats.csv")
        return None

    return pd.read_csv(ens_path)


# ──────────────────────────────────────────────────────────────────────────────
# Calcular punto representativo (medianas) de cada ensemble
# ──────────────────────────────────────────────────────────────────────────────

SWEEP_METRICS = [
    "max_dev_pob_pct",
    "n_comunas_partidas",
    "split_severity",
    "pp_promedio",
    "pop_afectada_pct",
    "cut_edges",
]


def ensemble_medians(df: pd.DataFrame, scenario: ScenarioConfig) -> dict:
    row = {
        "escenario":    scenario.name,
        "tipo_reforma": scenario.tipo_reforma,
        "penalty":      getattr(scenario, "split_penalty", 0.0),
        "n_planes":     len(df),
    }

    # split_penalty biases the scoring of plans (score column) but NOT the chain
    # sampling: all apc_soft_pX variants produce the same plan distribution.
    # Using the reference plan (argmax of score) lets different penalties select
    # genuinely different plans and trace a meaningful Pareto frontier.
    use_ref = (
        scenario.preserve_mode == "soft"
        and "score" in df.columns
        and df["score"].notna().any()
    )

    if use_ref:
        ref = df.loc[df["score"].idxmax()]
        row["point_type"] = "reference_plan"
        for col in SWEEP_METRICS:
            if col in df.columns and pd.notna(ref[col]):
                row[f"{col}_median"] = round(float(ref[col]), 4)
            else:
                row[f"{col}_median"] = None
    else:
        row["point_type"] = "ensemble_median"
        for col in SWEEP_METRICS:
            if col in df.columns:
                vals = df[col].dropna()
                row[f"{col}_median"] = round(float(vals.median()), 4) if len(vals) else None
            else:
                row[f"{col}_median"] = None

    return row


# ──────────────────────────────────────────────────────────────────────────────
# Frontera Pareto sobre los puntos del barrido
# ──────────────────────────────────────────────────────────────────────────────

def compute_pareto(df_pts: pd.DataFrame) -> pd.DataFrame:
    """
    Marca los puntos Pareto-óptimos en (max_dev_pob_pct_median,
    n_comunas_partidas_median) — ambas dimensiones a minimizar.
    """
    x = "max_dev_pob_pct_median"
    y = "n_comunas_partidas_median"

    mask  = df_pts[[x, y]].notna().all(axis=1)
    valid = df_pts[mask].copy()

    if valid.empty:
        df_pts["is_pareto"] = False
        return df_pts

    pts = valid[[x, y]].values.astype(float)
    pareto_idx = cd.pareto_frontier_nd(pts, minimize=[True, True])

    df_pts["is_pareto"] = False
    valid_indices = valid.index[pareto_idx]
    df_pts.loc[valid_indices, "is_pareto"] = True
    return df_pts


# ──────────────────────────────────────────────────────────────────────────────
# Visualización
# ──────────────────────────────────────────────────────────────────────────────

def plot_pareto(df_pts: pd.DataFrame, out_dir: str, region_name: str) -> None:
    BG = "#F8F7F4"
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.spines[["top", "right"]].set_visible(False)

    x_col = "max_dev_pob_pct_median"
    y_col = "n_comunas_partidas_median"

    plotted_tipos = set()
    for _, row in df_pts.iterrows():
        if pd.isna(row.get(x_col)) or pd.isna(row.get(y_col)):
            continue
        tipo   = row.get("tipo_reforma", "contrafactual_intermedio")
        marker = MARKER_MAP.get(tipo, "o")
        color  = COLOR_MAP.get(tipo, "#888880")
        zorder = 4 if row.get("is_pareto") else 3
        size   = 100 if row.get("is_pareto") else 60
        edge   = "#1a1a18" if row.get("is_pareto") else "none"
        lw     = 1.5 if row.get("is_pareto") else 0

        ax.scatter(
            row[x_col], row[y_col],
            s=size, c=color, marker=marker,
            edgecolors=edge, linewidths=lw, zorder=zorder,
            label=tipo if tipo not in plotted_tipos else "_",
        )
        plotted_tipos.add(tipo)

        # Etiqueta solo para anclajes y puntos Pareto
        label_col = row.get("escenario", "")
        if row.get("is_pareto") or row.get("tipo_reforma") in (
                "vigente", "contrafactual_fuerte", "control_metodologico"):
            penalty = row.get("penalty")
            lbl = (label_col if row.get("tipo_reforma") != "contrafactual_intermedio"
                   else f"p={penalty:.2f}")
            ax.annotate(
                lbl, (row[x_col], row[y_col]),
                textcoords="offset points", xytext=(6, 4),
                fontsize=7, color="#333333",
            )

    # Trazar línea de frontera Pareto (ordenada por x)
    pareto = df_pts[df_pts["is_pareto"] == True].dropna(
        subset=[x_col, y_col]
    ).sort_values(x_col)
    if len(pareto) >= 2:
        ax.step(
            pareto[x_col].values, pareto[y_col].values,
            where="post", color="#1A5C8A", linewidth=1.5,
            linestyle="--", zorder=2, alpha=0.7, label="Frontera Pareto",
        )

    ax.set_xlabel("Desviación pob. máx — mediana (%)", fontsize=10)
    ax.set_ylabel("Comunas partidas — mediana", fontsize=10)
    ax.set_title(
        f"{region_name} — Frontera Pareto\n"
        "Balance poblacional × Integridad comunal (H2)",
        fontsize=11, fontweight="bold",
    )

    # Leyenda
    handles = [
        mpatches.Patch(color=COLOR_MAP[t], label=t.replace("_", " "))
        for t in MARKER_MAP if t in plotted_tipos
    ]
    handles.append(plt.Line2D(
        [0], [0], color="#1A5C8A", lw=1.5, linestyle="--", label="Frontera Pareto"
    ))
    ax.legend(handles=handles, fontsize=8, loc="upper right")

    plt.tight_layout()
    path = os.path.join(out_dir, "pareto_tradeoff.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura guardada: {path}")


def plot_pop_afectada(df_pts: pd.DataFrame, out_dir: str, region_name: str) -> None:
    """Scatter: max_dev_pob_pct_median vs pop_afectada_pct_median."""
    x_col = "max_dev_pob_pct_median"
    y_col = "pop_afectada_pct_median"

    valid = df_pts[[x_col, y_col]].notna().all(axis=1)
    if valid.sum() < 2:
        return

    BG = "#F8F7F4"
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.spines[["top", "right"]].set_visible(False)

    for _, row in df_pts[valid].iterrows():
        tipo   = row.get("tipo_reforma", "contrafactual_intermedio")
        color  = COLOR_MAP.get(tipo, "#888880")
        marker = MARKER_MAP.get(tipo, "o")
        ax.scatter(row[x_col], row[y_col] * 100,
                   s=70, c=color, marker=marker, zorder=3)
        ax.annotate(
            row.get("escenario", ""),
            (row[x_col], row[y_col] * 100),
            textcoords="offset points", xytext=(5, 3),
            fontsize=7, color="#333333",
        )

    ax.set_xlabel("Desviación pob. máx — mediana (%)", fontsize=10)
    ax.set_ylabel("Población en comunas partidas — mediana (%)", fontsize=10)
    ax.set_title(
        f"{region_name} — Balance vs. Población afectada\n"
        "Indicador de integridad comunal real (H2/H3)",
        fontsize=11, fontweight="bold",
    )

    plt.tight_layout()
    path = os.path.join(out_dir, "pareto_pop_afectada.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura guardada: {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args        = parse_args()
    base_dir    = args.base_dir
    output_base = args.output_dir or os.path.join(base_dir, "datos")
    region_code = args.region
    region_name = REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    penalties   = parse_penalties(args.penalties)
    out_dir     = os.path.join(output_base, region_name, "pareto_sweep")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\nchiledist — Barrido Pareto (H2)")
    print(f"  región      : {region_code} ({region_name})")
    print(f"  penalties   : {penalties}")
    if args.n_distritos is not None:
        print(f"  n_distritos : {args.n_distritos}  "
              f"(--n-distritos explícito, aplica a todas las configuraciones)")
    else:
        print(f"  n_distritos : según cada escenario/anclaje (scenario.n_districts)")
    print(f"  n_steps     : {args.n_steps}")
    print(f"  output      : {out_dir}")

    scenarios = build_sweep_scenarios(penalties, include_anchors=not args.no_anchors)
    print(f"  escenarios  : {[s.name for s in scenarios]}")

    analizar_region = None
    if not args.skip_run:
        analizar_region = _load_analizar_region()

    # ── Ejecutar o cargar cada configuración ─────────────────────────────────
    rows = []
    for sc in scenarios:
        print(f"\n{'─'*50}")
        print(f"  Configuración: {sc.name}  (penalty={sc.split_penalty})")

        df_ens = run_or_load(
            scenario=sc,
            region_code=region_code,
            base_dir=base_dir,
            output_base=output_base,
            n_distritos=args.n_distritos,
            pop_tol=args.pop_tol,
            n_steps=args.n_steps,
            seed=args.seed,
            skip_run=args.skip_run,
            skip_viz=args.skip_viz,
            analizar_region=analizar_region,
        )

        if df_ens is None:
            print(f"  ⚠ Omitido: {sc.name}")
            continue

        row = ensemble_medians(df_ens, sc)
        rows.append(row)
        print(f"  n_planes={row['n_planes']}  "
              f"dev={row['max_dev_pob_pct_median']}%  "
              f"splits={row['n_comunas_partidas_median']}  "
              f"pop_afect={row['pop_afectada_pct_median']}")

    if not rows:
        print("\n⚠ Sin datos para analizar. Abortando.")
        return

    # ── Tabla resumen + frontera Pareto ───────────────────────────────────────
    df_pts = pd.DataFrame(rows)
    df_pts = compute_pareto(df_pts)

    # Guardar tabla completa
    full_path = os.path.join(out_dir, "pareto_sweep_results.csv")
    df_pts.to_csv(full_path, index=False)
    print(f"\nTabla completa guardada: {full_path}")

    # Guardar solo frontera
    pareto_path = os.path.join(out_dir, "pareto_frontier.csv")
    df_pts[df_pts["is_pareto"]].to_csv(pareto_path, index=False)

    # ── Imprimir resumen ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTADOS DEL BARRIDO — {region_name}")
    print(f"{'='*60}")
    cols_show = ["escenario", "penalty", "point_type",
                 "max_dev_pob_pct_median", "n_comunas_partidas_median",
                 "pop_afectada_pct_median", "is_pareto"]
    print(df_pts[[c for c in cols_show if c in df_pts.columns]]
          .sort_values("max_dev_pob_pct_median")
          .to_string(index=False))

    n_pareto = df_pts["is_pareto"].sum()
    print(f"\nConfiguraciones Pareto-óptimas: {n_pareto}/{len(df_pts)}")
    print(f"Tabla guardada: {full_path}")
    print(f"Frontera Pareto guardada: {pareto_path}")

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not args.skip_viz:
        plot_pareto(df_pts, out_dir, region_name)

        if df_pts["pop_afectada_pct_median"].notna().sum() >= 2:
            plot_pop_afectada(df_pts, out_dir, region_name)


if __name__ == "__main__":
    main()
