"""
scripts/malapportionment.py
===========================
Análisis de malapportionment para H3: ¿cuánto "vale" un voto en cada
circunscripción electoral bajo el mapa vigente y las magnitudes de la
Ley 20840?

Cuatro análisis
---------------
    A1  Personas por escaño y peso relativo del voto (estructura del mapa)
    A2  Comparación: magnitudes vigentes vs proporcionales al Censo 2024
    A3  Umbral efectivo por circunscripción (barrera de entrada D'Hondt)
    A4  Métricas electorales: magnitudes fijas vs calculadas (requiere SERVEL)

Fuentes de datos requeridas
----------------------------
    --census-path   : CSV Censo 2024 con columnas CUT, personas
    --assignment-path: JSON {CUT_str: n_circunscripcion (1-28)}
    --servel-path   : CSV SERVEL con columnas CUT, partido, votos  [A4]

Si algún archivo falta, el análisis correspondiente se omite con aviso.
Usa --demo para correr todos los análisis con datos sintéticos.

Salidas en <output-dir>/malapportionment/ (o --output-dir):
    malapportionment_pxe.csv        — personas/escaño y peso relativo (A1)
    malapportionment_comparacion.csv— magnitudes vigentes vs nuevas    (A2)
    malapportionment_umbrales.csv   — umbral efectivo por distrito     (A3)
    malapportionment_electoral.csv  — métricas electorales fijas/calc. (A4)
    figuras/personas_por_escano.png
    figuras/peso_relativo.png
    figuras/comparacion_magnitudes.png
    figuras/umbrales_efectivos.png

Uso:
    # Datos reales
    python scripts/malapportionment.py \\
        --census-path    datos/poblacion_comunal_censo2024.csv \\
        --assignment-path datos/asignacion_vigente.json \\
        --servel-path    datos/servel_2021_por_cut.csv

    # Demo con datos sintéticos
    python scripts/malapportionment.py --demo

    # Solo A1–A3 (sin electoral)
    python scripts/malapportionment.py \\
        --census-path datos/poblacion_comunal_censo2024.csv \\
        --assignment-path datos/asignacion_vigente.json
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

# ── Nombres cortos para los 28 distritos electorales vigentes ─────────────────
NOMBRES_DIST = {
    1: "Arica-Parinacota",  2: "Tarapacá",         3: "Antofagasta",
    4: "Atacama",           5: "Coquimbo Norte",    6: "Coquimbo Sur",
    7: "Aconcagua",         8: "Valparaíso Costa",  9: "Valparaíso Interior",
    10: "Santiago Nor",     11: "Santiago Cen",     12: "Santiago Nor-Or",
    13: "Santiago Or",      14: "Santiago Sur-Or",  15: "Santiago Sur",
    16: "Santiago Pon-Nor", 17: "Santiago Pon-Sur", 18: "Santiago Sur2",
    19: "O'Higgins Nor",    20: "O'Higgins Sur",    21: "Maule Norte",
    22: "Maule Sur",        23: "Biobío Nor",        24: "Biobío Sur",
    25: "Araucanía Nor",    26: "Araucanía Sur",    27: "Los Ríos-Los Lagos",
    28: "Magallanes-Aysén",
}

# ── Paleta del proyecto ───────────────────────────────────────────────────────
BG           = "#F8F7F4"
C_BASE       = "#1A5C8A"
C_HIGHLIGHT  = "#D85A30"
C_OK         = "#1D9E75"
C_WARN       = "#BA7517"


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Análisis de malapportionment H3 — mapa electoral vigente Chile."
    )
    p.add_argument("--census-path",    default=None,
                   help="CSV Censo 2024: columnas CUT, personas")
    p.add_argument("--assignment-path", default=None,
                   help="JSON {CUT_str: n_circunscripcion} — asignación vigente")
    p.add_argument("--servel-path",    default=None,
                   help="CSV SERVEL 2021: columnas CUT, partido, votos")
    p.add_argument("--pacto-path",     default=None,
                   help="JSON {partido: pacto} para D'Hondt binivel (opcional)")
    p.add_argument("--output-dir",     default=None,
                   help="Directorio de salida (default: datos/malapportionment)")
    p.add_argument("--base-dir",       default=".",
                   help="Raíz del proyecto, para buscar datos/ si no se especifican rutas")
    p.add_argument("--demo",           action="store_true",
                   help="Datos sintéticos para todos los análisis (no requiere archivos externos)")
    p.add_argument("--skip-viz",       action="store_true")
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Datos sintéticos (modo --demo)
# ──────────────────────────────────────────────────────────────────────────────

def _demo_data() -> tuple:
    """
    Devuelve (pop_por_distrito, assignment, votes_df) sintéticos para los 28
    distritos electorales chilenos, con distribución de población que refleja
    la heterogeneidad real del sistema (distritos chicos vs RM).
    """
    rng = np.random.default_rng(42)

    # Población aproximada por distrito (en miles; refleja heterogeneidad real)
    pop_approx = {
        1: 280,  2: 390,  3: 680,  4: 320,  5: 430,  6: 380,
        7: 420,  8: 560,  9: 490, 10: 680, 11: 580, 12: 590,
        13: 720, 14: 640, 15: 730, 16: 620, 17: 590, 18: 640,
        19: 430, 20: 390, 21: 370, 22: 330, 23: 540, 24: 480,
        25: 430, 26: 410, 27: 560, 28: 200,
    }

    pop_por_distrito = pd.Series(
        {d: v * 1000 + rng.integers(-20000, 20000)
         for d, v in pop_approx.items()}
    ).astype(int)

    # Asignación trivial: una "comuna" = un distrito (para plan_electoral_metrics)
    assignment = {d: d for d in range(1, 29)}

    # Votos sintéticos por distrito (5 partidos, distribución random)
    partidos = ["UDI", "RN", "PS", "PPD", "FA"]
    rows = []
    for d in range(1, 29):
        total_v = int(pop_por_distrito[d] * rng.uniform(0.35, 0.55))
        shares  = rng.dirichlet([2, 2, 1.5, 1.5, 1])
        for partido, share in zip(partidos, shares):
            rows.append({"CUT": d, "partido": partido,
                         "votos": max(1, int(total_v * share))})
    votes_df = pd.DataFrame(rows)

    print("  Modo DEMO: datos sintéticos para 28 circunscripciones.")
    return pop_por_distrito, assignment, votes_df


# ──────────────────────────────────────────────────────────────────────────────
# Carga de datos reales
# ──────────────────────────────────────────────────────────────────────────────

def _load_population(census_path: str, assignment: dict) -> pd.Series | None:
    """
    Carga población comunal y agrega a nivel de circunscripción usando
    el assignment (CUT → n_circunscripcion).
    Devuelve pd.Series {n_dist: personas} o None si falla.
    """
    try:
        census = c24.load_census2024(census_path)
        # Normalizar CUT a 5 dígitos: load_census2024 devuelve CUT como int
        # (sin cero a la izquierda), mientras que `assignment` (desde
        # asignacion_vigente.json) usa strings de 5 dígitos. No importa cuál
        # de las dos fuentes use 4 o 5 dígitos — normalize_cut() las hace
        # comparables en ambos casos.
        census["CUT"] = census["CUT"].map(cd.normalize_cut)
        pop_map = census.set_index("CUT")["personas"].to_dict()

        pop_por_dist: dict[int, int] = {}
        for cut_str, dist_num in assignment.items():
            pop = pop_map.get(cd.normalize_cut(cut_str), 0)
            pop_por_dist[int(dist_num)] = pop_por_dist.get(int(dist_num), 0) + int(pop)
        return pd.Series(pop_por_dist).sort_index()
    except Exception as e:
        print(f"  ⚠ No se pudo cargar población: {e}")
        return None


def _load_population_by_unit(census_path: str) -> pd.Series | None:
    """
    Carga población comunal SIN agregar a nivel de circunscripción.

    A diferencia de _load_population() (que agrega a nivel de distrito,
    usada por A1-A3), analisis_electoral() (A4) necesita población
    indexada por unidad — la misma clave que `assignment` — porque
    plan_electoral_metrics() hace su propia agregación a distrito
    internamente a partir de `assignment`. CUT se normaliza a 5 dígitos
    (chiledist.normalize_cut) para que calce con esas claves sin importar
    si la fuente de origen usa CUT de 4 o 5 dígitos.
    """
    try:
        census = c24.load_census2024(census_path)
        census["CUT"] = census["CUT"].map(cd.normalize_cut)
        return census.set_index("CUT")["personas"]
    except Exception as e:
        print(f"  ⚠ No se pudo cargar población por unidad: {e}")
        return None


def _load_assignment(path: str) -> dict | None:
    """
    Carga asignación vigente desde JSON {CUT_str: n_circunscripcion}.
    Devuelve dict o None si falla.
    """
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        # Normalizar: claves a CUT canónico (5 dígitos), valores a int.
        # Tolera que el JSON de origen tenga claves de 4 o 5 dígitos.
        return {cd.normalize_cut(k): int(v) for k, v in raw.items()}
    except Exception as e:
        print(f"  ⚠ No se pudo cargar asignación: {e}")
        return None


def _load_votes(servel_path: str) -> pd.DataFrame | None:
    """
    Carga resultados SERVEL 2021 por CUT.
    El CSV debe tener columnas CUT, partido, votos (o alias reconocidos).
    """
    try:
        df = sv.load_resultados_electorales(servel_path)
        return sv.votos_por_comuna(df)
    except Exception as e:
        # Intentar lectura directa si no encaja con load_resultados_electorales
        try:
            df = pd.read_csv(servel_path)
            required = {"CUT", "partido", "votos"}
            if not required.issubset(df.columns):
                print(f"  ⚠ {servel_path}: faltan columnas {required - set(df.columns)}")
                return None
            return df[["CUT", "partido", "votos"]]
        except Exception as e2:
            print(f"  ⚠ No se pudo cargar SERVEL: {e2}")
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
# Análisis A1 — Personas por escaño y peso relativo del voto
# ──────────────────────────────────────────────────────────────────────────────

def analisis_pxe(
    pop_por_distrito: pd.Series,
    magnitudes: pd.Series,
) -> pd.DataFrame:
    """
    Construye tabla completa de malapportionment por circunscripción.
    """
    pxe = cd.personas_por_escano(pop_por_distrito, magnitudes)
    prv = cd.peso_relativo_del_voto(pop_por_distrito, magnitudes)

    media_nacional = (pop_por_distrito.sum() / magnitudes.sum()
                      if magnitudes.sum() > 0 else float("nan"))

    df = pd.DataFrame({
        "distrito":          pxe.index,
        "nombre":            [NOMBRES_DIST.get(d, f"D{d:02d}") for d in pxe.index],
        "magnitud_vigente":  magnitudes.reindex(pxe.index).astype(int),
        "poblacion":         pop_por_distrito.reindex(pxe.index).astype(int),
        "personas_x_escano": pxe.values.round(0).astype(int),
        "peso_relativo":     prv.reindex(pxe.index).round(4),
    }).sort_values("personas_x_escano", ascending=False).reset_index(drop=True)

    # Indicadores
    df["sobrerepresentado"] = df["peso_relativo"] < 1.0
    df["infra_representado"] = df["peso_relativo"] > 1.0

    ratio = df["personas_x_escano"].max() / df["personas_x_escano"].min()
    print(f"\n  [A1] Malapportionment estructural:")
    print(f"    Media nacional       : {media_nacional:,.0f} personas/escaño")
    print(f"    Máximo pxe           : {df['personas_x_escano'].max():,}  "
          f"(D{df.loc[df['personas_x_escano'].idxmax(),'distrito']})")
    print(f"    Mínimo pxe           : {df['personas_x_escano'].min():,}  "
          f"(D{df.loc[df['personas_x_escano'].idxmin(),'distrito']})")
    print(f"    Ratio max/min        : {ratio:.2f}x")
    print(f"    Distritos peso < 0.5 : {(df['peso_relativo'] < 0.5).sum()} "
          f"(voto vale >2x la media)")
    print(f"    Distritos peso > 2.0 : {(df['peso_relativo'] > 2.0).sum()} "
          f"(voto vale <0.5x la media)")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Análisis A2 — Comparación magnitudes vigentes vs proporcionales
# ──────────────────────────────────────────────────────────────────────────────

def analisis_comparacion(pop_por_distrito: pd.Series) -> pd.DataFrame:
    """
    Tabla: magnitudes vigentes vs proporcionales al Censo 2024.
    """
    mag_dict = {k: v for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
                if k in pop_por_distrito.index}
    df = cd.comparar_magnitudes(
        pop_por_distrito,
        magnitudes_vigentes=mag_dict,
        total_seats=155,
        min_seats=3,
        max_seats=8,
    )
    df["nombre"] = df["distrito"].map(NOMBRES_DIST).fillna(df["distrito"].apply(lambda d: f"D{d:02d}"))

    gana = (df["delta"] > 0).sum()
    pierde = (df["delta"] < 0).sum()
    igual  = (df["delta"] == 0).sum()

    print(f"\n  [A2] Comparación magnitudes vigentes vs proporcionales (Censo 2024):")
    print(f"    Distritos que GANAN escaños : {gana}")
    print(f"    Distritos que PIERDEN escaños: {pierde}")
    print(f"    Distritos sin cambio          : {igual}")
    cambio_max = df.loc[df["delta"].abs().idxmax()]
    print(f"    Mayor cambio: D{int(cambio_max['distrito'])} "
          f"({int(cambio_max['magnitud_vigente'])} → {int(cambio_max['magnitud_nueva'])}, "
          f"delta={int(cambio_max['delta']):+d})")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Análisis A3 — Umbral efectivo por circunscripción
# ──────────────────────────────────────────────────────────────────────────────

def analisis_umbrales() -> pd.DataFrame:
    """
    Tabla de umbral efectivo para cada circunscripción según Ley 20840.
    """
    rows = []
    for dist, mag in sorted(cd.MAGNITUDES_LEGALES_LEY20840.items()):
        mag_int = int(mag)
        T_U     = cd.umbral_efectivo(mag_int)
        T_L     = 1 / (2 * mag_int) if mag_int > 0 else 1.0
        T_e     = round((T_L * T_U) ** 0.5, 4)   # umbral geométrico (Taagepera 1998)
        categoria = ("Bajo"   if T_U <= 0.125 else
                     "Medio"  if T_U <= 0.167 else
                     "Alto")
        rows.append({
            "distrito":  dist,
            "nombre":    NOMBRES_DIST.get(dist, f"D{dist:02d}"),
            "magnitud":  mag_int,
            "T_U":       T_U,     # umbral superior
            "T_L":       round(T_L, 4),   # umbral inferior
            "T_e":       T_e,     # umbral geométrico
            "categoria": categoria,
        })

    df = pd.DataFrame(rows).sort_values("T_U", ascending=False).reset_index(drop=True)

    umbral_desc = {"Alto": "T_U > 16.7%  (M ≤ 4)",
                   "Medio": "12.5% < T_U ≤ 16.7% (M=5–6)",
                   "Bajo": "T_U ≤ 12.5%  (M ≥ 7)"}
    print(f"\n  [A3] Umbrales efectivos:")
    for cat in ["Alto", "Medio", "Bajo"]:
        n = (df["categoria"] == cat).sum()
        mags = sorted(int(m) for m in df[df["categoria"] == cat]["magnitud"].unique())
        print(f"    {cat:6s} ({umbral_desc[cat]}): {n} distritos  "
              f"magnitudes={mags}")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Análisis A4 — plan_electoral_metrics con magnitudes fijas vs calculadas
# ──────────────────────────────────────────────────────────────────────────────

def analisis_electoral(
    assignment: dict,
    votes_df: pd.DataFrame,
    pop_by_unit: pd.Series,
    pacto_map: dict | None,
) -> pd.DataFrame:
    """
    Ejecuta plan_electoral_metrics en modo 'fijas' y 'calculadas' y compara.

    pop_by_unit debe estar indexada por la misma clave que `assignment`
    (unit_id — CUT de 5 dígitos en modo real, número de distrito en
    --demo), NO por distrito: plan_electoral_metrics() hace su propia
    agregación a nivel de circunscripción internamente a partir de
    `assignment`. Pasar población ya agregada por distrito (ej. la salida
    de _load_population(), usada por A1-A3) hace que esa agregación
    interna nunca encuentre las claves y las métricas de malapportionment
    (pxe_max, pxe_min, ratio_max_min_pxe, peso_relativo_*) salgan en 0/NaN
    sin ningún error — usa _load_population_by_unit() en su lugar.
    """
    # Normalizar CUT en votes_df para que coincida con las claves de
    # `assignment`, sin tocar `assignment` (pop_by_unit más abajo depende
    # de que sus claves no cambien). En modo real, `assignment` ya viene
    # normalizado a CUT de 5 dígitos por _load_assignment() (desde
    # asignacion_vigente.json), pero votes_df["CUT"] llega como int desde
    # SERVEL — igualar solo el tipo (str(int) -> "1101") no basta si falta
    # el cero a la izquierda ("01101"); normalize_cut() sí los hace
    # comparables sin importar si la fuente usa CUT de 4 o 5 dígitos. En
    # modo --demo, `assignment` usa enteros (unidad == número de distrito)
    # y el comportamiento previo de igualar el tipo se mantiene intacto.
    votes_df = votes_df.copy()
    sample_key = next(iter(assignment.keys()))
    if isinstance(sample_key, str):
        votes_df["CUT"] = votes_df["CUT"].map(cd.normalize_cut)
    else:
        votes_df["CUT"] = votes_df["CUT"].astype(type(sample_key))

    mag_series = pd.Series(
        {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
         if k in set(assignment.values())}
    )

    m_fijas = cd.plan_electoral_metrics(
        assignment, votes_df, pop_by_unit,
        magnitudes_fijas=mag_series,
        pacto_map=pacto_map,
    )
    m_calc = cd.plan_electoral_metrics(
        assignment, votes_df, pop_by_unit,
        total_seats=155, min_seats=3, max_seats=8,
        pacto_map=pacto_map,
    )

    metricas = [
        "ratio_max_min_pxe", "peso_relativo_max", "peso_relativo_min",
        "pxe_max", "pxe_min",
        "gallagher", "loosemore_hanby", "rae",
        "enp_votos", "enp_escanos", "escanos_mayor_partido",
        "n_partidos_con_escanos", "seat_bonus_max",
        "modo_dhondt", "modo_magnitudes",
    ]

    rows = []
    for m in metricas:
        v_f = m_fijas.get(m)
        v_c = m_calc.get(m)
        delta = None
        if isinstance(v_f, (int, float)) and isinstance(v_c, (int, float)):
            try:
                delta = round(float(v_f) - float(v_c), 4)
            except Exception:
                pass
        rows.append({"metrica": m, "fijas": v_f, "calculadas": v_c, "delta": delta})
    df = pd.DataFrame(rows)

    print(f"\n  [A4] Métricas electorales — magnitudes fijas vs calculadas:")
    print(f"    ratio_max_min_pxe: fijas={m_fijas['ratio_max_min_pxe']:.2f}x  "
          f"calculadas={m_calc['ratio_max_min_pxe']:.2f}x")
    print(f"    gallagher:         fijas={m_fijas['gallagher']:.4f}  "
          f"calculadas={m_calc['gallagher']:.4f}")
    print(f"    modo_dhondt:       {m_fijas['modo_dhondt']}")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Visualizaciones
# ──────────────────────────────────────────────────────────────────────────────

def _ax_style(ax, title: str = "", xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(BG)
    ax.spines[["top", "right"]].set_visible(False)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)


def plot_pxe(df_pxe: pd.DataFrame, out_dir: str, demo: bool) -> None:
    suffix = " (DEMO)" if demo else ""
    fig, axes = plt.subplots(1, 2, figsize=(16, 10))
    fig.patch.set_facecolor(BG)

    media = (df_pxe["personas_x_escano"] * df_pxe["magnitud_vigente"]).sum() / \
            df_pxe["magnitud_vigente"].sum()

    # Panel izquierdo: personas/escaño
    ax = axes[0]
    df_s = df_pxe.sort_values("personas_x_escano")
    colors = [C_HIGHLIGHT if v > media else C_OK
              for v in df_s["personas_x_escano"]]
    ax.barh(df_s["nombre"], df_s["personas_x_escano"], color=colors, height=0.7)
    ax.axvline(media, color="#333333", linewidth=1.4, linestyle="--",
               label=f"Media: {media:,.0f}")
    _ax_style(ax, f"Personas por escaño{suffix}",
              xlabel="Personas / escaño")
    ax.legend(fontsize=8)
    for i, (_, row) in enumerate(df_s.iterrows()):
        ax.text(row["personas_x_escano"] + media * 0.01, i,
                f"M={int(row['magnitud_vigente'])}",
                va="center", fontsize=6.5, color="#333333")

    # Panel derecho: peso relativo
    ax2 = axes[1]
    df_s2 = df_pxe.sort_values("peso_relativo")
    colors2 = [C_HIGHLIGHT if v > 1.0 else C_OK for v in df_s2["peso_relativo"]]
    ax2.barh(df_s2["nombre"], df_s2["peso_relativo"], color=colors2, height=0.7)
    ax2.axvline(1.0,  color="#333333", linewidth=1.4, linestyle="--",
                label="Media = 1.0")
    ax2.axvline(0.5,  color=C_WARN,   linewidth=1,   linestyle=":",
                alpha=0.8, label="0.5 (voto vale 2x)")
    ax2.axvline(2.0,  color=C_WARN,   linewidth=1,   linestyle=":",
                alpha=0.8, label="2.0 (voto vale 0.5x)")
    _ax_style(ax2, f"Peso relativo del voto{suffix}",
              xlabel="Personas/escaño ÷ media nacional")
    ax2.legend(fontsize=8)

    fig.suptitle(
        "H3 — Malapportionment: desigualdad del voto bajo Ley 20840",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(out_dir, "personas_por_escano.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


def plot_comparacion(df_comp: pd.DataFrame, out_dir: str, demo: bool) -> None:
    suffix = " (DEMO)" if demo else ""
    df_s = df_comp.sort_values("delta", ascending=False).reset_index(drop=True)

    fig, axes = plt.subplots(1, 2, figsize=(16, 10))
    fig.patch.set_facecolor(BG)

    # Panel izquierdo: magnitudes vigentes vs nuevas
    ax = axes[0]
    x  = np.arange(len(df_s))
    w  = 0.35
    ax.barh(x + w/2, df_s["magnitud_vigente"], w,
            color=C_BASE, label="Vigente (Ley 20840)", alpha=0.85)
    ax.barh(x - w/2, df_s["magnitud_nueva"], w,
            color=C_OK, label="Proporcional (Censo 2024)", alpha=0.85)
    ax.set_yticks(x)
    ax.set_yticklabels(df_s["nombre"], fontsize=7)
    _ax_style(ax, f"Magnitudes: vigente vs proporcional{suffix}",
              xlabel="Escaños")
    ax.legend(fontsize=8)

    # Panel derecho: delta de escaños
    ax2 = axes[1]
    colors = [C_OK if d > 0 else (C_HIGHLIGHT if d < 0 else C_WARN)
              for d in df_s["delta"]]
    ax2.barh(df_s["nombre"], df_s["delta"], color=colors, height=0.7)
    ax2.axvline(0, color="#333333", linewidth=1.2)
    _ax_style(ax2, f"Cambio de escaños{suffix}",
              xlabel="Δ escaños (Proporcional − Vigente)")
    handles = [
        mpatches.Patch(color=C_OK,       label="Gana escaños"),
        mpatches.Patch(color=C_HIGHLIGHT, label="Pierde escaños"),
        mpatches.Patch(color=C_WARN,      label="Sin cambio"),
    ]
    ax2.legend(handles=handles, fontsize=8)

    fig.suptitle(
        "H3 — Comparación de magnitudes: Ley 20840 vs proporcional Censo 2024",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(out_dir, "comparacion_magnitudes.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


def plot_umbrales(df_umb: pd.DataFrame, out_dir: str, demo: bool) -> None:
    suffix = " (DEMO)" if demo else ""
    df_s = df_umb.sort_values("T_U", ascending=False).reset_index(drop=True)

    CAT_COLOR = {"Alto": C_HIGHLIGHT, "Medio": C_WARN, "Bajo": C_OK}

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor(BG)
    colors = [CAT_COLOR[c] for c in df_s["categoria"]]
    ax.barh(df_s["nombre"], df_s["T_U"] * 100, color=colors, height=0.7)
    ax.axvline(16.7, color="#333333", linewidth=1, linestyle="--",
               alpha=0.8, label="M=5: 16.7%")
    ax.axvline(12.5, color="#555555", linewidth=1, linestyle=":",
               alpha=0.8, label="M=7: 12.5%")

    for i, row in df_s.iterrows():
        ax.text(row["T_U"] * 100 + 0.2, i,
                f"M={int(row['magnitud'])}",
                va="center", fontsize=7.5, color="#333333")

    _ax_style(ax,
              f"Umbral efectivo superior T_U = 1/(M+1){suffix}",
              xlabel="T_U (%)")
    handles = [mpatches.Patch(color=v, label=k) for k, v in CAT_COLOR.items()]
    ax.legend(handles=handles, fontsize=8)

    fig.suptitle(
        "H3 — Barrera de entrada al sistema electoral por circunscripción",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(out_dir, "umbrales_efectivos.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


def plot_electoral(df_elec: pd.DataFrame, out_dir: str, demo: bool) -> None:
    suffix = " (DEMO)" if demo else ""
    num_df = df_elec[df_elec["delta"].notna()].copy()

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(BG)
    x = np.arange(len(num_df))
    w = 0.35
    ax.bar(x - w/2, num_df["fijas"].astype(float), w,
           color=C_HIGHLIGHT, label="Magnitudes fijas (legales)", alpha=0.85)
    ax.bar(x + w/2, num_df["calculadas"].astype(float), w,
           color=C_OK, label="Magnitudes calculadas (Hamilton)", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(num_df["metrica"], rotation=25, ha="right", fontsize=8)
    _ax_style(ax, f"Comparación métricas electorales: fijas vs calculadas{suffix}")
    ax.legend(fontsize=9)

    fig.suptitle(
        "H3/H4 — Impacto de magnitudes fijas vs calculadas en proporcionalidad",
        fontsize=11, fontweight="bold",
    )
    plt.tight_layout()
    path = os.path.join(out_dir, "comparacion_electoral.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Figura: {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Directorio de salida
    base_datos = args.output_dir or os.path.join(args.base_dir, "datos")
    out_dir    = os.path.join(base_datos, "malapportionment")
    fig_dir    = os.path.join(out_dir, "figuras")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)

    print(f"\nchiledist — Malapportionment (H3)")
    print(f"  output: {out_dir}")

    # ── Cargar datos ──────────────────────────────────────────────────────────
    if args.demo:
        pop_por_distrito, assignment, votes_df = _demo_data()
        pacto_map = None
        # En --demo, unidad == distrito (asignación trivial), así que la
        # misma serie sirve como población por unidad para A4.
        pop_by_unit = pop_por_distrito
    else:
        # Intentar rutas por defecto si no se especifican
        def _default(provided, *candidates):
            if provided:
                return provided
            for c in candidates:
                p = os.path.join(args.base_dir, c)
                if os.path.exists(p):
                    print(f"  Auto-detectado: {p}")
                    return p
            return None

        census_path     = _default(args.census_path,
                                   "datos/poblacion_comunal_censo2024.csv")
        assignment_path = _default(args.assignment_path,
                                   "datos/asignacion_vigente.json")
        servel_path     = _default(args.servel_path,
                                   "datos/servel_2021_por_cut.csv")
        pacto_map       = _load_pacto_map(args.pacto_path)

        # Cargar asignación (obligatoria para A1-A2-A4)
        assignment = None
        if assignment_path:
            assignment = _load_assignment(assignment_path)
        if assignment is None:
            print(
                "\n  ⚠ Sin asignación vigente (--assignment-path).\n"
                "     El archivo debe ser JSON: {\"CUT_str\": n_circunscripcion, ...}\n"
                "     Puedes descargarlo de BCN / SERVEL o construirlo desde\n"
                "     la Ley 18.700 y sus modificaciones (Ley 20840).\n"
                "     Usa --demo para correr con datos sintéticos."
            )
            sys.exit(1)

        # Cargar población: agregada por distrito (A1-A3) y por unidad (A4 —
        # plan_electoral_metrics hace su propia agregación vía `assignment`
        # y necesita la población indexada por CUT, no por distrito).
        pop_por_distrito = None
        pop_by_unit = None
        if census_path:
            pop_por_distrito = _load_population(census_path, assignment)
            pop_by_unit = _load_population_by_unit(census_path)
        if pop_por_distrito is None:
            print(
                "\n  ⚠ Sin población comunal (--census-path).\n"
                "     Descarga el Censo 2024 comunal desde INE y pasa la ruta.\n"
                "     Usa --demo para correr con datos sintéticos."
            )
            sys.exit(1)

        # Cargar votos (opcional: solo A4)
        votes_df = _load_votes(servel_path) if servel_path else None
        if votes_df is None:
            print("  [A4] Sin datos SERVEL (--servel-path) — "
                  "análisis electoral omitido.")

    # ── Magnitudes vigentes ───────────────────────────────────────────────────
    districts_en_assignment = set(assignment.values())
    magnitudes = pd.Series(
        {k: int(v) for k, v in cd.MAGNITUDES_LEGALES_LEY20840.items()
         if k in districts_en_assignment}
    )

    # Si la asignación no cubre todos los 28 distritos, avisamos
    faltantes = set(cd.MAGNITUDES_LEGALES_LEY20840.keys()) - districts_en_assignment
    if faltantes:
        print(f"  ⚠ {len(faltantes)} distritos sin cobertura en la asignación: "
              f"{sorted(faltantes)[:5]}{'...' if len(faltantes) > 5 else ''}")

    # Alinear población con distritos con magnitud
    pop_por_distrito = pop_por_distrito.reindex(magnitudes.index, fill_value=0)

    # ── Análisis A1 ───────────────────────────────────────────────────────────
    df_pxe = analisis_pxe(pop_por_distrito, magnitudes)

    # ── Análisis A2 ───────────────────────────────────────────────────────────
    df_comp = analisis_comparacion(pop_por_distrito)

    # ── Análisis A3 ───────────────────────────────────────────────────────────
    df_umb = analisis_umbrales()

    # ── Análisis A4 (opcional) ────────────────────────────────────────────────
    df_elec = None
    if votes_df is not None:
        try:
            df_elec = analisis_electoral(assignment, votes_df,
                                         pop_by_unit, pacto_map)
        except Exception as e:
            import traceback
            print(f"  ⚠ A4 falló: {e}")
            traceback.print_exc()

    # ── Guardar CSVs ──────────────────────────────────────────────────────────
    df_pxe.to_csv(os.path.join(out_dir, "malapportionment_pxe.csv"), index=False)
    df_comp.to_csv(os.path.join(out_dir, "malapportionment_comparacion.csv"), index=False)
    df_umb.to_csv(os.path.join(out_dir, "malapportionment_umbrales.csv"), index=False)
    if df_elec is not None:
        df_elec.to_csv(os.path.join(out_dir, "malapportionment_electoral.csv"), index=False)

    print(f"\n  CSVs guardados en {out_dir}/")

    # ── Visualizaciones ───────────────────────────────────────────────────────
    if not args.skip_viz:
        plot_pxe(df_pxe, fig_dir, args.demo)
        plot_comparacion(df_comp, fig_dir, args.demo)
        plot_umbrales(df_umb, fig_dir, args.demo)
        if df_elec is not None:
            plot_electoral(df_elec, fig_dir, args.demo)

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESUMEN H3 — Malapportionment"
          + (" (DEMO)" if args.demo else ""))
    print(f"{'='*60}")
    print(df_pxe[["distrito", "nombre", "magnitud_vigente",
                  "personas_x_escano", "peso_relativo"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
