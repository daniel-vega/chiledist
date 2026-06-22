"""
scripts/electoral_analysis.py
==============================
Análisis de proporcionalidad D'Hondt binivel para H4.

Pregunta: bajo el sistema chileno real (D'Hondt binivel: pactos compiten
entre sí, partidos dentro de cada pacto), ¿cómo cambia la proporcionalidad
respecto al modelo uninivel?  ¿Cuánto afecta la geografía distrital al índice
de Gallagher cuando se fijan los votos?

Cuatro bloques
--------------
    B1  Comparación uninivel vs binivel en un solo distrito (verificación)
    B2  Matriz 4-combinaciones: (magnitudes fijas/calculadas) × (uni/binivel)
        sobre el mapa completo vigente
    B3  Distribución de Gallagher sobre un ensemble de planes
        (requiere assignments.parquet de redistritaje.py o --demo)
    B4  Seat bonus por partido: detalle completo uni vs binivel

Datos externos requeridos
--------------------------
    --servel-path     CSV SERVEL 2021: columnas CUT, partido, votos
    --assignment-path JSON {CUT_str: n_circunscripcion (1-28)}  [mapa vigente]
    --census-path     CSV Censo 2024: columnas CUT, personas      [para pop]
    --pacto-path      JSON {partido: pacto}                       [binivel]
    --run-dir         run_dir de redistritaje.py con assignments.parquet [B3]

Usa --demo para correr todos los bloques con datos sintéticos.

Salidas en <output-dir>/electoral_analysis/:
    electoral_b1_distrito.csv         — uninivel vs binivel, distrito ejemplo
    electoral_b2_matrix.csv           — 4 combinaciones: índices completos
    electoral_b3_ensemble.csv         — Gallagher / bonus por plan del ensemble
    electoral_b4_bonus.csv            — seat bonus por partido (uni y binivel)
    figuras/
        b1_distrito_ejemplo.png
        b2_combinaciones.png
        b3_gallagher_ensemble.png
        b4_seat_bonus.png

Uso:
    # Todos los datos reales
    python scripts/electoral_analysis.py \\
        --servel-path    datos/servel_2021_por_cut.csv \\
        --assignment-path datos/asignacion_vigente.json \\
        --census-path    datos/poblacion_comunal_censo2024.csv \\
        --pacto-path     datos/pactos_2021.json \\
        --run-dir        datos/R13_METROPOLITANA/redistritaje/legal_comunas

    # Solo B1-B2 (sin ensemble)
    python scripts/electoral_analysis.py \\
        --servel-path datos/servel_2021_por_cut.csv \\
        --assignment-path datos/asignacion_vigente.json \\
        --census-path datos/poblacion_comunal_censo2024.csv \\
        --pacto-path datos/pactos_2021.json

    # Demo completo
    python scripts/electoral_analysis.py --demo
"""

import argparse
import json
import os
import sys
import warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

import chiledist as cd
from chiledist.data import servel as sv
from chiledist.data import census2024 as c24
from chiledist.persistence import PlanEnsemble

BG          = "#F8F7F4"
C_UNI       = "#1A5C8A"   # uninivel
C_BI        = "#D85A30"   # binivel
C_FIJAS     = "#1D9E75"   # magnitudes fijas
C_CALC      = "#BA7517"   # magnitudes calculadas
C_NEG       = "#D85A30"   # bonus negativo
C_POS       = "#1D9E75"   # bonus positivo


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Análisis D'Hondt binivel H4 — proporcionalidad electoral Chile."
    )
    p.add_argument("--servel-path",    default=None,
                   help="CSV SERVEL 2021: columnas CUT, partido, votos")
    p.add_argument("--assignment-path", default=None,
                   help="JSON {CUT_str: n_circunscripcion} — asignación vigente")
    p.add_argument("--census-path",    default=None,
                   help="CSV Censo 2024: columnas CUT, personas")
    p.add_argument("--pacto-path",     default=None,
                   help="JSON {partido: pacto} — pactos electorales 2021")
    p.add_argument("--run-dir",        default=None,
                   help="run_dir de redistritaje.py con assignments.parquet (B3)")
    p.add_argument("--n-ensemble",     type=int, default=200,
                   help="Planes a analizar en B3 (default: 200)")
    p.add_argument("--output-dir",     default=None,
                   help="Directorio de salida")
    p.add_argument("--base-dir",       default=".",
                   help="Raíz del proyecto para buscar datos/")
    p.add_argument("--demo",           action="store_true",
                   help="Datos sintéticos — todos los bloques sin archivos externos")
    p.add_argument("--skip-viz",       action="store_true")
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Datos sintéticos (--demo)
# ──────────────────────────────────────────────────────────────────────────────

# Pactos electorales Chile 2021 (simplificado, 3 bloques)
PACTO_DEMO = {
    "UDI": "ChileVamos", "RN": "ChileVamos", "Evopoli": "ChileVamos",
    "PDC": "NuevaUnidad", "PS": "NuevaUnidad", "PPD": "NuevaUnidad",
    "FA":  "Apruebo",    "RD": "Apruebo",     "CS":  "Apruebo",
    "Ind": "Ind",
}

# Población aproximada por distrito (miles)
_POP_DIST = {
    1:280, 2:390, 3:680, 4:320, 5:430, 6:380, 7:420, 8:560, 9:490,
    10:680, 11:580, 12:590, 13:720, 14:640, 15:730, 16:620, 17:590, 18:640,
    19:430, 20:390, 21:370, 22:330, 23:540, 24:480, 25:430, 26:410,
    27:560, 28:200,
}


def _demo_data(rng=None) -> tuple:
    """
    Devuelve (pop_por_distrito, assignment, votes_df, pacto_map) sintéticos.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    partidos = list(PACTO_DEMO.keys())
    pop = pd.Series({d: v * 1000 + rng.integers(-15000, 15000)
                     for d, v in _POP_DIST.items()}).astype(int)
    assignment = {d: d for d in range(1, 29)}

    rows = []
    for d in range(1, 29):
        total_v = int(pop[d] * rng.uniform(0.35, 0.55))
        shares  = rng.dirichlet([2.5, 2, 1.5, 0.8, 1, 0.8, 1.5, 1, 0.5, 0.4])
        for partido, share in zip(partidos, shares):
            rows.append({"CUT": d, "partido": partido,
                         "votos": max(1, int(total_v * share))})
    votes_df = pd.DataFrame(rows)
    return pop, assignment, votes_df, PACTO_DEMO


# ──────────────────────────────────────────────────────────────────────────────
# Carga de datos reales
# ──────────────────────────────────────────────────────────────────────────────

def _load_assignment(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {str(k): int(v) for k, v in raw.items()}
    except Exception as e:
        print(f"  ⚠ asignación no cargada: {e}")
        return None


def _load_population(census_path: str, assignment: dict) -> pd.Series | None:
    try:
        census = c24.load_census2024(census_path)
        census["CUT"] = census["CUT"].astype(str)
        pop_map = census.set_index("CUT")["personas"].to_dict()
        pop_dist: dict[int, int] = {}
        for cut, d in assignment.items():
            pop_dist[int(d)] = pop_dist.get(int(d), 0) + int(pop_map.get(str(cut), 0))
        return pd.Series(pop_dist).sort_index()
    except Exception as e:
        print(f"  ⚠ población no cargada: {e}")
        return None


def _load_votes(servel_path: str) -> pd.DataFrame | None:
    try:
        df = sv.load_resultados_electorales(servel_path)
        return sv.votos_por_comuna(df)
    except Exception:
        try:
            df = pd.read_csv(servel_path)
            required = {"CUT", "partido", "votos"}
            if not required.issubset(df.columns):
                print(f"  ⚠ {servel_path}: faltan columnas {required - set(df.columns)}")
                return None
            return df[["CUT", "partido", "votos"]]
        except Exception as e:
            print(f"  ⚠ SERVEL no cargado: {e}")
            return None


def _load_pacto_map(pacto_path: str | None) -> dict | None:
    if pacto_path is None:
        return None
    try:
        with open(pacto_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ pacto_map no cargado: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# B1 — Uninivel vs binivel en un solo distrito
# ──────────────────────────────────────────────────────────────────────────────

def bloque_b1(votes_df, assignment, pop_por_distrito, pacto_map) -> pd.DataFrame:
    """
    Compara uninivel vs binivel en el distrito con mayor variación esperada:
    el que tiene el mayor número de partidos chicos en el pacto ganador.
    Complementa con métricas del mapa completo.
    """
    # Elegir el distrito con más partidos en el bloque mayoritario
    votos_dist = cd.aggregate_votes(votes_df, assignment, unit_col="CUT")
    magnitudes = pd.Series(
        {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
         if k in set(assignment.values())}
    )

    if pacto_map is None:
        print("  [B1] Sin pacto_map — se omite binivel (solo uninivel)")
        pacto_map = {p: p for p in votes_df["partido"].unique()}

    # Seleccionar el distrito más grande (mayor magnitud o más votos)
    by_votos = (votos_dist.groupby("district")["votos"].sum()
                .reindex(magnitudes.index, fill_value=0))
    d_ejemplo = int(by_votos.idxmax())
    grp = votos_dist[votos_dist["district"] == d_ejemplo].copy()
    mag_ej = int(magnitudes.get(d_ejemplo, 5))

    votos_ej = dict(zip(grp["partido"], grp["votos"]))
    uni_ej   = cd.dhondt(votos_ej, mag_ej)
    bi_ej    = cd.dhondt_binivel(votos_ej, pacto_map, mag_ej)

    partidos = sorted(set(votos_ej.keys()))
    rows = []
    for p in partidos:
        rows.append({
            "partido":   p,
            "pacto":     pacto_map.get(p, p),
            "votos":     votos_ej[p],
            "votos_pct": round(votos_ej[p] / sum(votos_ej.values()) * 100, 2),
            "escanos_uninivel": uni_ej.get(p, 0),
            "escanos_binivel":  bi_ej.get(p, 0),
            "delta":     bi_ej.get(p, 0) - uni_ej.get(p, 0),
        })
    df = pd.DataFrame(rows).sort_values("votos", ascending=False).reset_index(drop=True)

    diffs = (df["delta"] != 0).sum()
    print(f"\n  [B1] Distrito D{d_ejemplo:02d}  (M={mag_ej}):")
    print(f"    Partidos que cambian de escaños: {diffs}/{len(df)}")
    print(f"    Ganan con binivel (δ>0): {(df['delta']>0).sum()}")
    print(f"    Pierden con binivel (δ<0): {(df['delta']<0).sum()}")
    print(df[["partido","pacto","votos_pct","escanos_uninivel",
              "escanos_binivel","delta"]].to_string(index=False))

    df.attrs["distrito"] = d_ejemplo
    df.attrs["magnitud"] = mag_ej
    return df


# ──────────────────────────────────────────────────────────────────────────────
# B2 — Matriz 4-combinaciones sobre el mapa completo
# ──────────────────────────────────────────────────────────────────────────────

def bloque_b2(votes_df, assignment, pop_por_distrito, pacto_map) -> pd.DataFrame:
    """
    Ejecuta plan_electoral_metrics en las 4 combinaciones:
    (magnitudes: fijas|calculadas) × (modo: uninivel|binivel)
    """
    magnitudes = pd.Series(
        {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
         if k in set(assignment.values())}
    )

    combos = [
        ("fijas",      None,      "Fijas + Uninivel"),
        ("fijas",      pacto_map, "Fijas + Binivel"),
        ("calculadas", None,      "Calculadas + Uninivel"),
        ("calculadas", pacto_map, "Calculadas + Binivel"),
    ]
    if pacto_map is None:
        combos = [c for c in combos if c[1] is None]
        print("  [B2] Sin pacto_map — solo combinaciones uninivel")

    METRICAS = [
        "gallagher", "loosemore_hanby", "rae",
        "enp_votos", "enp_escanos",
        "escanos_mayor_partido", "n_partidos_con_escanos",
        "ratio_max_min_pxe", "peso_relativo_max", "peso_relativo_min",
        "seat_bonus_max", "modo_dhondt", "modo_magnitudes",
    ]
    rows = []
    for mag_modo, pm, label in combos:
        kwargs = dict(
            assignment=assignment,
            votes_df=votes_df,
            pop_by_unit=pop_por_distrito,
            total_seats=155, min_seats=3, max_seats=8,
            pacto_map=pm,
        )
        if mag_modo == "fijas":
            kwargs["magnitudes_fijas"] = magnitudes
        m = cd.plan_electoral_metrics(**kwargs)
        row = {"combinacion": label}
        row.update({k: m.get(k) for k in METRICAS})
        rows.append(row)

    df = pd.DataFrame(rows)

    print(f"\n  [B2] Matriz de combinaciones — mapa completo:")
    cols = ["combinacion", "gallagher", "loosemore_hanby",
            "n_partidos_con_escanos", "seat_bonus_max", "ratio_max_min_pxe"]
    print(df[[c for c in cols if c in df.columns]].to_string(index=False))

    # Efecto del sistema de pactos (binivel - uninivel) con magnitudes fijas
    if len(df) >= 2:
        fi_uni = df[df["combinacion"] == "Fijas + Uninivel"]
        fi_bi  = df[df["combinacion"] == "Fijas + Binivel"]
        if len(fi_uni) and len(fi_bi):
            delta_g = (float(fi_bi["gallagher"].iloc[0])
                       - float(fi_uni["gallagher"].iloc[0]))
            delta_p = (int(fi_bi["n_partidos_con_escanos"].iloc[0])
                       - int(fi_uni["n_partidos_con_escanos"].iloc[0]))
            print(f"\n    Efecto del sistema de pactos (binivel vs uninivel, fijas):")
            print(f"      Δ Gallagher:             {delta_g:+.4f}")
            print(f"      Δ partidos con escaños:  {delta_p:+d}")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# B3 — Distribución de Gallagher sobre el ensemble
# ──────────────────────────────────────────────────────────────────────────────

def bloque_b3(
    votes_df, pop_por_distrito, pacto_map,
    run_dir: str | None, n_ensemble: int,
    is_demo: bool,
) -> pd.DataFrame:
    """
    Para cada plan del ensemble: calcula Gallagher binivel con magnitudes fijas.
    Cuantifica cuánto varía la proporcionalidad según la geografía distrital
    (con los votos congelados en la elección 2021).
    """
    magnitudes = pd.Series(
        {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()}
    )

    def _metrics_for_plan(asgn: dict) -> dict:
        m_bi = cd.plan_electoral_metrics(
            asgn, votes_df, pop_por_distrito,
            magnitudes_fijas=magnitudes,
            pacto_map=pacto_map,
        )
        m_uni = cd.plan_electoral_metrics(
            asgn, votes_df, pop_por_distrito,
            magnitudes_fijas=magnitudes,
            pacto_map=None,
        )
        return {
            "gallagher_bi":  m_bi["gallagher"],
            "gallagher_uni": m_uni["gallagher"],
            "lh_bi":         m_bi["loosemore_hanby"],
            "lh_uni":        m_uni["loosemore_hanby"],
            "bonus_max_bi":  m_bi["seat_bonus_max"],
            "bonus_max_uni": m_uni["seat_bonus_max"],
            "n_partidos_bi": m_bi["n_partidos_con_escanos"],
            "n_partidos_uni": m_uni["n_partidos_con_escanos"],
        }

    rows = []

    # ── Fuente: assignments.parquet de un run real ─────────────────────────
    if run_dir is not None and os.path.exists(
            os.path.join(run_dir, "assignments.parquet")):
        print(f"  [B3] Cargando ensemble desde {run_dir}...")
        try:
            ensemble = PlanEnsemble.load(run_dir)
            # Limitar a n_ensemble plans
            if ensemble.n_draws > n_ensemble:
                ensemble = ensemble.sample(n_ensemble, seed=42)
            total = ensemble.n_draws
            print(f"    {total} planes cargados")

            for draw_id, grp in ensemble.assignments.groupby("draw"):
                asgn = dict(zip(
                    grp["unit_id"].astype(type(list(votes_df["CUT"])[0])),
                    grp["district"].astype(int),
                ))
                try:
                    r = _metrics_for_plan(asgn)
                    r["plan_id"] = int(draw_id)
                    r["source"]  = "ensemble"
                    rows.append(r)
                except Exception:
                    pass
        except Exception as e:
            print(f"  ⚠ No se pudo cargar ensemble: {e}")

    # ── Fuente: permutaciones sintéticas (demo o sin run-dir) ──────────────
    if not rows:
        n = n_ensemble if not is_demo else 150
        lbl = "demo" if is_demo else "sintético"
        print(f"  [B3] Generando {n} asignaciones sintéticas ({lbl})...")
        rng = np.random.default_rng(42)
        districts = list(range(1, 29))
        units = sorted(votes_df["CUT"].unique())
        n_units = len(units)
        # Usar el mismo tipo de clave que votes_df["CUT"] para que aggregate_votes
        # pueda hacer el map correctamente.
        cut_type = type(units[0])
        for i in range(n):
            # Permutación: cada unidad recibe un distrito de los 28
            labels = rng.choice(districts, size=n_units, replace=True)
            asgn = {cut_type(u): int(d) for u, d in zip(units, labels)}
            try:
                r = _metrics_for_plan(asgn)
                r["plan_id"] = i
                r["source"]  = lbl
                rows.append(r)
            except Exception:
                pass

    df = pd.DataFrame(rows)
    if df.empty:
        print("  [B3] Sin resultados.")
        return df

    print(f"\n  [B3] Distribución de Gallagher sobre {len(df)} planes:")
    for col, lbl in [("gallagher_bi", "binivel"), ("gallagher_uni", "uninivel")]:
        if col not in df.columns:
            continue
        v = df[col].dropna()
        print(f"    Gallagher {lbl:9s}: "
              f"mediana={v.median():.4f}  "
              f"IQR={v.quantile(0.75)-v.quantile(0.25):.4f}  "
              f"[p10={v.quantile(0.1):.4f}, p90={v.quantile(0.9):.4f}]")

    if "source" in df.columns and df["source"].iloc[0] in ("demo", "sintético"):
        print("    ⚠ Fuente sintética: los valores reflejan el pipeline, "
              "no datos geográficos reales.")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# B4 — Seat bonus por partido (uninivel vs binivel)
# ──────────────────────────────────────────────────────────────────────────────

def bloque_b4(votes_df, assignment, pacto_map) -> pd.DataFrame:
    """
    Desglosa el seat bonus por partido en ambos modos.
    Usa run_electoral_plan / run_electoral_plan_binivel directamente para
    obtener el resultado completo (plan_electoral_metrics solo devuelve el máx).
    """
    magnitudes = pd.Series(
        {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
         if k in set(assignment.values())}
    )

    votos_dist = cd.aggregate_votes(votes_df, assignment, unit_col="CUT")

    # Uninivel
    res_uni  = cd.run_electoral_plan(votos_dist, magnitudes)
    v_uni, s_uni = cd.national_shares(res_uni)
    bonus_uni    = cd.seat_bonus(v_uni, s_uni)

    rows_uni = pd.DataFrame({
        "partido":      bonus_uni.index,
        "votos_pct":    (v_uni.reindex(bonus_uni.index, fill_value=0) * 100).round(2),
        "escanos_pct":  (s_uni.reindex(bonus_uni.index, fill_value=0) * 100).round(2),
        "seat_bonus":   bonus_uni.values.round(4),
        "modo":         "uninivel",
    })

    if pacto_map is not None:
        votos_dist["pacto"] = (votos_dist["partido"].map(pacto_map)
                               .fillna(votos_dist["partido"]))
        res_bi   = cd.run_electoral_plan_binivel(votos_dist, magnitudes)
        v_bi, s_bi = cd.national_shares(res_bi)
        bonus_bi = cd.seat_bonus(v_bi, s_bi)

        rows_bi = pd.DataFrame({
            "partido":     bonus_bi.index,
            "votos_pct":   (v_bi.reindex(bonus_bi.index, fill_value=0) * 100).round(2),
            "escanos_pct": (s_bi.reindex(bonus_bi.index, fill_value=0) * 100).round(2),
            "seat_bonus":  bonus_bi.values.round(4),
            "modo":        "binivel",
        })
        # Pacto para cada partido
        rows_bi["pacto"] = rows_bi["partido"].map(pacto_map).fillna(rows_bi["partido"])
        rows_uni["pacto"] = rows_uni["partido"].map(pacto_map).fillna(rows_uni["partido"])
        df = pd.concat([rows_uni, rows_bi], ignore_index=True)
    else:
        rows_uni["pacto"] = rows_uni["partido"]
        df = rows_uni

    print(f"\n  [B4] Seat bonus por partido:")
    pivot = df.pivot(index="partido", columns="modo", values="seat_bonus")
    if "uninivel" in pivot and "binivel" in pivot:
        pivot["delta_bi_uni"] = (pivot["binivel"] - pivot["uninivel"]).round(4)
    print(pivot.sort_values("uninivel", ascending=False).to_string())

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Visualizaciones
# ──────────────────────────────────────────────────────────────────────────────

def _ax_style(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor(BG)
    ax.spines[["top", "right"]].set_visible(False)
    if title:  ax.set_title(title, fontsize=10, fontweight="bold", pad=7)
    if xlabel: ax.set_xlabel(xlabel, fontsize=9)
    if ylabel: ax.set_ylabel(ylabel, fontsize=9)


def plot_b1(df: pd.DataFrame, out_dir: str, demo: bool) -> None:
    d_num = df.attrs.get("distrito", "?")
    mag   = df.attrs.get("magnitud", "?")
    suffix = " (DEMO)" if demo else ""

    fig, axes = plt.subplots(1, 2, figsize=(14, max(6, len(df) * 0.5)))
    fig.patch.set_facecolor(BG)

    partidos = df["partido"].tolist()
    x = np.arange(len(partidos))
    w = 0.35

    for ax, col_u, col_b, title in [
        (axes[0], "escanos_uninivel", "escanos_binivel",
         f"D{d_num:02d} (M={mag}) — Escaños{suffix}"),
        (axes[1], "votos_pct", None,
         f"D{d_num:02d} — Votos (%)"),
    ]:
        if col_b:
            ax.bar(x - w/2, df[col_u], w, color=C_UNI,
                   label="Uninivel", alpha=0.85)
            ax.bar(x + w/2, df[col_b], w, color=C_BI,
                   label="Binivel", alpha=0.85)
            ax.legend(fontsize=8)
        else:
            ax.bar(x, df["votos_pct"], color="#7B9EC0", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(partidos, rotation=30, ha="right", fontsize=8)
        _ax_style(ax, title)

    # Resaltar diferencias
    for i, (_, row) in enumerate(df.iterrows()):
        if row["delta"] != 0:
            axes[0].text(i, max(row["escanos_uninivel"], row["escanos_binivel"]) + 0.05,
                         f"Δ{row['delta']:+d}", ha="center", fontsize=7.5,
                         color=C_BI, fontweight="bold")

    fig.suptitle("H4 — Uninivel vs Binivel: ejemplo distrital",
                 fontsize=12, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(out_dir, "b1_distrito_ejemplo.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


def plot_b2(df: pd.DataFrame, out_dir: str, demo: bool) -> None:
    metricas = ["gallagher", "loosemore_hanby", "rae",
                "n_partidos_con_escanos", "seat_bonus_max"]
    labels   = ["Gallagher", "Loosemore-Hanby", "Rae",
                 "N partidos c/escaños", "Seat bonus máx (pp)"]
    suffix = " (DEMO)" if demo else ""

    available = [(m, l) for m, l in zip(metricas, labels) if m in df.columns]
    n = len(available)
    if n == 0:
        return

    combos = df["combinacion"].tolist()
    colors = [C_UNI, C_BI, C_FIJAS, C_CALC][:len(combos)]
    x = np.arange(n)
    w = 0.8 / len(combos)

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor(BG)
    for i, (combo, color) in enumerate(zip(combos, colors)):
        vals = [float(df.loc[df["combinacion"] == combo, m].iloc[0])
                if m in df.columns else 0 for m, _ in available]
        ax.bar(x + (i - len(combos)/2 + 0.5) * w, vals, w,
               label=combo, color=color, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([l for _, l in available], rotation=15, ha="right", fontsize=9)
    ax.legend(fontsize=8, loc="upper right")
    _ax_style(ax,
              f"H4 — Matriz de combinaciones: proporcionalidad{suffix}",
              ylabel="Valor del índice")
    fig.tight_layout()
    path = os.path.join(out_dir, "b2_combinaciones.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


def plot_b3(df: pd.DataFrame, out_dir: str, demo: bool) -> None:
    if df.empty:
        return
    suffix = " (DEMO — sintético)" if demo else ""
    has_bi  = "gallagher_bi"  in df.columns and df["gallagher_bi"].notna().sum() > 1
    has_uni = "gallagher_uni" in df.columns and df["gallagher_uni"].notna().sum() > 1
    if not has_bi and not has_uni:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(BG)

    for ax, col, color, label in [
        (axes[0], "gallagher_bi",  C_BI,  "Binivel"),
        (axes[1], "gallagher_uni", C_UNI, "Uninivel"),
    ]:
        vals = df[col].dropna()
        if vals.empty or vals.nunique() < 2:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                    transform=ax.transAxes)
            ax.axis("off")
            continue
        ax.hist(vals, bins=min(25, max(5, len(vals)//4)),
                color=color, edgecolor="white", linewidth=0.5, alpha=0.85)
        ax.axvline(vals.median(), color="#333333", linewidth=1.5, linestyle="--",
                   label=f"Mediana: {vals.median():.4f}")
        iqr = vals.quantile(0.75) - vals.quantile(0.25)
        ax.set_title(f"Gallagher {label}  IQR={iqr:.4f}{suffix}",
                     fontsize=10, fontweight="bold")
        ax.set_xlabel("Gallagher")
        ax.set_ylabel("Frecuencia")
        ax.legend(fontsize=8)
        ax.set_facecolor(BG)
        ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle(
        "H4 — Variabilidad de proporcionalidad según geografía distrital\n"
        "(votos SERVEL 2021 congelados, distintos mapas)",
        fontsize=11, fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(out_dir, "b3_gallagher_ensemble.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


def plot_b4(df: pd.DataFrame, out_dir: str, demo: bool) -> None:
    if df.empty:
        return
    suffix = " (DEMO)" if demo else ""

    modos = df["modo"].unique().tolist()
    has_bi  = "binivel"  in modos
    has_uni = "uninivel" in modos

    # Tabla pivot por partido
    partidos = df["partido"].unique()
    bonus_uni = df[df["modo"] == "uninivel"].set_index("partido")["seat_bonus"]
    bonus_bi  = (df[df["modo"] == "binivel"].set_index("partido")["seat_bonus"]
                 if has_bi else pd.Series(dtype=float))

    # Ordenar por bonus uninivel absoluto
    orden = bonus_uni.abs().sort_values(ascending=False).index

    fig, axes = plt.subplots(1, 1 + has_bi, figsize=(8 + 6 * has_bi, max(6, len(orden) * 0.5)))
    if not has_bi:
        axes = [axes]
    fig.patch.set_facecolor(BG)

    for ax, bonus, color, label in [
        (axes[0], bonus_uni, C_UNI, "Uninivel"),
        *([(axes[1], bonus_bi, C_BI, "Binivel")] if has_bi else []),
    ]:
        vals = bonus.reindex(orden, fill_value=0)
        colors = [C_POS if v >= 0 else C_NEG for v in vals]
        ax.barh(orden, vals, color=colors, height=0.7)
        ax.axvline(0, color="#333333", linewidth=1)
        _ax_style(ax,
                  f"Seat bonus {label}{suffix}",
                  xlabel="Escaños% − Votos% (pp)")
        for i, (p, v) in enumerate(zip(orden, vals)):
            if abs(v) > 0.1:
                ax.text(v + (0.05 if v >= 0 else -0.05), i,
                        f"{v:+.1f}", va="center", fontsize=7,
                        ha="left" if v >= 0 else "right", color="#333333")

    # Leyenda de colores
    handles = [mpatches.Patch(color=C_POS, label="Sobrerepresentado (+)"),
               mpatches.Patch(color=C_NEG, label="Subrepresentado (−)")]
    axes[-1].legend(handles=handles, fontsize=8, loc="lower right")

    fig.suptitle("H4 — Seat bonus por partido: exceso de escaños vs votos",
                 fontsize=12, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(out_dir, "b4_seat_bonus.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    base_datos = args.output_dir or os.path.join(args.base_dir, "datos")
    out_dir    = os.path.join(base_datos, "electoral_analysis")
    fig_dir    = os.path.join(out_dir, "figuras")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)

    print(f"\nchiledist — Análisis Electoral (H4)")
    print(f"  output: {out_dir}")

    # ── Cargar datos ──────────────────────────────────────────────────────────
    if args.demo:
        pop, assignment, votes_df, pacto_map = _demo_data()
        print("  Modo DEMO: datos sintéticos (28 circunscripciones, 10 partidos).")
    else:
        def _default(provided, *candidates):
            if provided:
                return provided
            for c in candidates:
                p = os.path.join(args.base_dir, c)
                if os.path.exists(p):
                    print(f"  Auto-detectado: {p}")
                    return p
            return None

        assignment_path = _default(args.assignment_path, "datos/asignacion_vigente.json")
        census_path     = _default(args.census_path,     "datos/poblacion_comunal_censo2024.csv")
        servel_path     = _default(args.servel_path,     "datos/servel_2021_por_cut.csv")

        assignment = _load_assignment(assignment_path) if assignment_path else None
        if assignment is None:
            print("\n  ⚠ Se requiere --assignment-path. Usa --demo para datos sintéticos.")
            sys.exit(1)

        pop = _load_population(census_path, assignment) if census_path else None
        if pop is None:
            # Fallback: pesos iguales por distrito
            districts = sorted(set(assignment.values()))
            pop = pd.Series({d: 400_000 for d in districts})
            print("  ⚠ Sin Censo 2024 — usando población uniforme por distrito")

        votes_df = _load_votes(servel_path) if servel_path else None
        if votes_df is None:
            print("\n  ⚠ Se requieren votos SERVEL (--servel-path). "
                  "Usa --demo para datos sintéticos.")
            sys.exit(1)

        pacto_map = _load_pacto_map(args.pacto_path)
        if pacto_map is None:
            print("  ⚠ Sin pacto_map (--pacto-path) — bloques binivel omitidos.")

    # ── B1 ────────────────────────────────────────────────────────────────────
    df_b1 = bloque_b1(votes_df, assignment, pop, pacto_map)
    df_b1.to_csv(os.path.join(out_dir, "electoral_b1_distrito.csv"), index=False)

    # ── B2 ────────────────────────────────────────────────────────────────────
    df_b2 = bloque_b2(votes_df, assignment, pop, pacto_map)
    df_b2.to_csv(os.path.join(out_dir, "electoral_b2_matrix.csv"), index=False)

    # ── B3 ────────────────────────────────────────────────────────────────────
    df_b3 = bloque_b3(
        votes_df, pop, pacto_map,
        run_dir=args.run_dir,
        n_ensemble=args.n_ensemble,
        is_demo=args.demo,
    )
    if not df_b3.empty:
        df_b3.to_csv(os.path.join(out_dir, "electoral_b3_ensemble.csv"), index=False)

    # ── B4 ────────────────────────────────────────────────────────────────────
    df_b4 = bloque_b4(votes_df, assignment, pacto_map)
    df_b4.to_csv(os.path.join(out_dir, "electoral_b4_bonus.csv"), index=False)

    print(f"\n  CSVs guardados en {out_dir}/")

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not args.skip_viz:
        plot_b1(df_b1, fig_dir, args.demo)
        plot_b2(df_b2, fig_dir, args.demo)
        if not df_b3.empty:
            plot_b3(df_b3, fig_dir, args.demo)
        plot_b4(df_b4, fig_dir, args.demo)

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESUMEN H4 — D'Hondt binivel"
          + (" (DEMO)" if args.demo else ""))
    print(f"{'='*60}")
    cols = ["combinacion", "gallagher", "n_partidos_con_escanos",
            "seat_bonus_max", "modo_dhondt"]
    print(df_b2[[c for c in cols if c in df_b2.columns]].to_string(index=False))


if __name__ == "__main__":
    main()
