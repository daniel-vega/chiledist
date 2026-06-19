"""
viz.py
======
Visualización de capas APC, grafos de adyacencia y planes de
redistritaje para Chile. Estilo consistente con ALARM/redist.
"""

from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import networkx as nx
import scipy.sparse as sp


# ──────────────────────────────────────────────────────────────────────────────
# Paletas y estilos
# ──────────────────────────────────────────────────────────────────────────────

BG_COLOR  = "#F8F7F4"
EDGE_COLOR = "#888880"

TIPO_COLOR = {
    "URBANO": "#1D9E75",
    "RURAL":  "#D85A30",
    "MIXTO":  "#BA7517",
}

def _region_palette(regions: list) -> dict:
    colors = plt.cm.tab20.colors
    return {r: colors[i % len(colors)] for i, r in enumerate(sorted(regions))}

def _clean_region_label(name: str) -> str:
    for prefix in ["REGIÓN DE ", "REGIÓN DEL ", "Región de ", "Región del "]:
        name = name.replace(prefix, "")
    return name


# ──────────────────────────────────────────────────────────────────────────────
# 1. Visualización de grafo de adyacencia
# ──────────────────────────────────────────────────────────────────────────────

def plot_adjacency_graph(
    G: nx.Graph,
    adj: sp.csr_matrix,
    indice: pd.DataFrame,
    color_by: str = "tipo",
    title: str = "Red de adyacencia",
    islands_csv: Optional[str] = None,
    top_labels: int = 15,
    figsize: tuple = (24, 16),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Visualiza un grafo de adyacencia censal con layout geográfico.

    Parameters
    ----------
    color_by : str
        'tipo'   → colorear por TIPO_DISTRITO (Urbano/Rural/Mixto)
        'region' → colorear por N_REGION
    islands_csv : str, optional
        Ruta al CSV de conexiones artificiales de islas.
    top_labels : int
        Número de nodos más conectados a etiquetar.
    """
    import os

    pos_geo    = {i: (G.nodes[i]["x"], G.nodes[i]["y"]) for i in G.nodes()}
    degrees    = np.array(adj.sum(axis=1)).flatten()

    # Colores
    if color_by == "tipo":
        node_colors = [
            TIPO_COLOR.get(G.nodes[i].get("TIPO_DISTRITO", ""), "#888780")
            for i in G.nodes()
        ]
        node_sizes = [10 + d * 2 for d in degrees]
    else:
        regions     = sorted(set(G.nodes[i].get("N_REGION", "") for i in G.nodes()))
        pal         = _region_palette(regions)
        node_colors = [pal.get(G.nodes[i].get("N_REGION", ""), "#888780")
                       for i in G.nodes()]
        node_sizes  = [30 + d * 6 for d in degrees]

    # Islas opcionales
    ids_islas, edges_art = _load_islands(islands_csv, indice)
    id_col = indice.columns[0]
    isla_idx = {
        i for i, row in indice.iterrows()
        if row[id_col] in ids_islas
    }
    if edges_art:
        edges_nat = [(u, v) for u, v in G.edges()
                     if (u, v) not in edges_art and (v, u) not in edges_art]
    else:
        edges_nat = list(G.edges())

    # Figura
    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(BG_COLOR)

    ax1 = fig.add_axes([0.00, 0.00, 0.58, 1.00])
    ax2 = fig.add_axes([0.62, 0.52, 0.36, 0.42])
    ax3 = fig.add_axes([0.62, 0.06, 0.36, 0.38])

    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor(BG_COLOR)

    # Panel 1: grafo geográfico
    nx.draw_networkx_edges(G, pos_geo, edgelist=edges_nat, ax=ax1,
                           alpha=0.15, width=0.3, edge_color=EDGE_COLOR)
    if edges_art:
        nx.draw_networkx_edges(G, pos_geo, edgelist=edges_art, ax=ax1,
                               alpha=0.70, width=1.2, edge_color="#D85A30",
                               style="dashed")

    nodos_norm = [i for i in G.nodes() if i not in isla_idx]
    nx.draw_networkx_nodes(G, pos_geo, nodelist=nodos_norm, ax=ax1,
                           node_color=[node_colors[i] for i in nodos_norm],
                           node_size=[node_sizes[i] for i in nodos_norm],
                           alpha=0.80, linewidths=0.2, edgecolors="#555550")
    if isla_idx:
        nx.draw_networkx_nodes(G, pos_geo, nodelist=list(isla_idx), ax=ax1,
                               node_color=[node_colors[i] for i in isla_idx],
                               node_size=[node_sizes[i] + 20 for i in isla_idx],
                               alpha=0.95, linewidths=1.5, edgecolors="#D85A30")

    top_n = sorted(G.nodes(), key=lambda i: G.degree(i), reverse=True)[:top_labels]
    name_key = "N_DISTRITO" if "N_DISTRITO" in G.nodes[0] else "N_COMUNA"
    nx.draw_networkx_labels(
        G, pos_geo, labels={i: G.nodes[i].get(name_key, str(i)) for i in top_n},
        ax=ax1, font_size=5.5, font_color="#1a1a18",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.80)
    )

    ax1.set_title(title, fontsize=13, fontweight="bold", pad=12, color="#1a1a18")
    ax1.axis("off")

    # Leyendas panel 1
    if color_by == "tipo":
        handles = [mpatches.Patch(color=c, label=t)
                   for t, c in TIPO_COLOR.items()]
        leg1 = ax1.legend(handles=handles, loc="lower left", fontsize=8,
                          framealpha=0.88, edgecolor="none",
                          title="Tipo distrito")
    else:
        regions = sorted(set(G.nodes[i].get("N_REGION", "") for i in G.nodes()))
        pal     = _region_palette(regions)
        handles = [mpatches.Patch(color=pal[r],
                                  label=_clean_region_label(r))
                   for r in regions]
        leg1 = ax1.legend(handles=handles, loc="lower left", fontsize=6,
                          ncol=2, framealpha=0.88, edgecolor="none",
                          title="Región")
    ax1.add_artist(leg1)

    if ids_islas:
        h_isla = [
            mpatches.Patch(facecolor=BG_COLOR, edgecolor="#D85A30", lw=1.5,
                           label=f"Isla conectada ({len(ids_islas)})"),
            plt.Line2D([0],[0], color="#D85A30", lw=1.2, ls="--",
                       label="Conexión artificial"),
        ]
        ax1.legend(handles=h_isla, loc="upper right", fontsize=7,
                   framealpha=0.88, edgecolor="none")

    # Panel 2: histograma de grados
    ax2.hist(degrees, bins=range(int(degrees.min()), int(degrees.max())+2),
             color="#1D9E75", edgecolor="white", linewidth=0.5, align="left")
    ax2.axvline(degrees.mean(), color="#D85A30", linewidth=1.5,
                linestyle="--", label=f"Media: {degrees.mean():.1f}")
    ax2.set_xlabel("Grado (nº vecinos)", fontsize=10, color="#3d3d3a")
    ax2.set_ylabel("Frecuencia", fontsize=10, color="#3d3d3a")
    ax2.set_title("Distribución de grados", fontsize=11,
                  fontweight="bold", color="#1a1a18")
    ax2.legend(fontsize=9)
    ax2.spines[["top","right"]].set_visible(False)
    ax2.tick_params(colors="#3d3d3a")

    # Panel 3: grado promedio por grupo
    if color_by == "tipo":
        _panel_by_tipo(ax3, degrees, indice)
    else:
        _panel_by_region(ax3, degrees, indice)

    sufijo = " (con islas)" if ids_islas else ""
    fig.suptitle(
        f"{title}{sufijo}  "
        f"({G.number_of_nodes():,} nodos · {G.number_of_edges():,} aristas)",
        fontsize=14, fontweight="bold", y=1.005, color="#1a1a18"
    )
    # fig.add_axes() no es compatible con tight_layout — usar subplots_adjust
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01)

    if save_path:
        plt.savefig(save_path, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
        print(f"Guardado: {save_path}")

    return fig


def _panel_by_tipo(ax, degrees, indice):
    tipo_col = "TIPO_DISTRITO" if "TIPO_DISTRITO" in indice.columns else None
    if not tipo_col:
        ax.axis("off")
        return

    stats = []
    for tipo, color in TIPO_COLOR.items():
        mask = indice[tipo_col] == tipo
        if not mask.any():
            continue
        stats.append({"tipo": tipo, "media": degrees[indice.index[mask]].mean(),
                      "n": mask.sum(), "color": color})

    df = pd.DataFrame(stats).sort_values("media", ascending=True)
    bars = ax.barh(df["tipo"], df["media"], color=df["color"],
                   edgecolor="white", linewidth=0.5, height=0.5)
    ax.axvline(degrees.mean(), color="#888780", linewidth=1.0,
               linestyle="--", alpha=0.7,
               label=f"Media: {degrees.mean():.1f}")
    for bar, row in zip(bars, df.itertuples()):
        ax.text(row.media + 0.05, bar.get_y() + bar.get_height()/2,
                f"{row.media:.2f}  (n={row.n})",
                va="center", fontsize=9, color="#3d3d3a")

    ax.set_xlabel("Grado promedio", fontsize=10, color="#3d3d3a")
    ax.set_title("Grado promedio por tipo", fontsize=11,
                 fontweight="bold", color="#1a1a18")
    ax.legend(fontsize=8)
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(colors="#3d3d3a")


def _panel_by_region(ax, degrees, indice):
    reg_col = "N_REGION" if "N_REGION" in indice.columns else None
    if not reg_col:
        ax.axis("off")
        return

    regions = sorted(indice[reg_col].unique())
    pal     = _region_palette(regions)
    stats   = []
    for r in regions:
        mask = indice[reg_col] == r
        stats.append({"region": _clean_region_label(r),
                      "media": degrees[indice.index[mask]].mean(),
                      "color": pal[r]})

    df   = pd.DataFrame(stats).sort_values("media", ascending=True)
    bars = ax.barh(df["region"], df["media"], color=df["color"],
                   edgecolor="white", linewidth=0.5, height=0.7)
    ax.axvline(degrees.mean(), color="#D85A30", linewidth=1.0,
               linestyle="--", alpha=0.7,
               label=f"Media nacional: {degrees.mean():.1f}")
    for bar, val in zip(bars, df["media"]):
        ax.text(val+0.05, bar.get_y()+bar.get_height()/2,
                f"{val:.1f}", va="center", fontsize=7, color="#3d3d3a")

    ax.set_xlabel("Grado promedio", fontsize=10, color="#3d3d3a")
    ax.set_title("Grado promedio por región", fontsize=11,
                 fontweight="bold", color="#1a1a18")
    ax.legend(fontsize=8)
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=7, colors="#3d3d3a")
    ax.tick_params(axis="x", colors="#3d3d3a")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Visualización de capas geográficas
# ──────────────────────────────────────────────────────────────────────────────

def plot_layer(
    gdf: gpd.GeoDataFrame,
    color_col: Optional[str] = None,
    value_col: Optional[str] = None,
    title: str = "",
    cmap: str = "YlOrRd",
    figsize: tuple = (12, 18),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Visualiza una capa geográfica APC.

    Parameters
    ----------
    color_col : str, optional
        Columna categórica para colorear (ej. 'TIPO_DISTRITO', 'N_REGION').
    value_col : str, optional
        Columna numérica para mapa de calor (ej. 'viviendas', 'polsby_popper').
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    if value_col and value_col in gdf.columns:
        gdf.plot(column=value_col, ax=ax, cmap=cmap,
                 legend=True, edgecolor="#AAAAAA", linewidth=0.2,
                 legend_kwds={"label": value_col, "shrink": 0.6})

    elif color_col and color_col in gdf.columns:
        categories = sorted(gdf[color_col].unique())
        if color_col == "TIPO_DISTRITO":
            color_map = TIPO_COLOR
        else:
            pal       = _region_palette(categories)
            color_map = pal

        for cat in categories:
            subset = gdf[gdf[color_col] == cat]
            subset.plot(ax=ax, color=color_map.get(cat, "#888780"),
                        edgecolor="#AAAAAA", linewidth=0.1, label=cat)

        handles = [mpatches.Patch(color=color_map.get(c, "#888780"),
                                  label=_clean_region_label(str(c)))
                   for c in categories]
        ax.legend(handles=handles, loc="lower left", fontsize=7,
                  ncol=2, framealpha=0.88, edgecolor="none")

    else:
        gdf.plot(ax=ax, color="#1D9E75", edgecolor="#AAAAAA", linewidth=0.2)

    ax.set_title(title or f"Capa APC 2023 — {len(gdf):,} unidades",
                 fontsize=13, fontweight="bold", pad=12, color="#1a1a18")
    ax.axis("off")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
        print(f"Guardado: {save_path}")

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 3. Visualización de plan de redistritaje
# ──────────────────────────────────────────────────────────────────────────────

def plot_plan(
    gdf: gpd.GeoDataFrame,
    assignment: dict | pd.Series,
    id_col: str,
    pop_col: Optional[str] = None,
    title: str = "Plan de redistritaje",
    show_pop_balance: bool = True,
    figsize: tuple = (14, 18),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Visualiza un plan de redistritaje sobre el mapa.

    Parameters
    ----------
    assignment : dict | pd.Series
        {id_unidad: id_distrito}.
    show_pop_balance : bool
        Si True, agrega un panel con el balance poblacional.
    """
    if isinstance(assignment, pd.Series):
        assignment = assignment.to_dict()

    gdf = gdf.copy().to_crs("EPSG:32719")   # métrico para evitar error de aspect
    gdf["__distrito__"] = gdf[id_col].map(assignment)
    districts = sorted(gdf["__distrito__"].dropna().unique())

    pal = {d: plt.cm.Set3.colors[i % 12] for i, d in enumerate(districts)}

    ncols = 2 if show_pop_balance and pop_col else 1
    fig, axes = plt.subplots(1, ncols,
                             figsize=(figsize[0]*ncols//2, figsize[1]))
    fig.patch.set_facecolor(BG_COLOR)

    if ncols == 1:
        axes = [axes]

    ax_map = axes[0]
    ax_map.set_facecolor(BG_COLOR)

    for d in districts:
        subset = gdf[gdf["__distrito__"] == d]
        subset.plot(ax=ax_map, color=pal[d],
                    edgecolor="#AAAAAA", linewidth=0.3)

    # Disolver y dibujar bordes del distrito
    try:
        dissolved = gdf.dissolve("__distrito__")
        dissolved.boundary.plot(ax=ax_map, color="#333333", linewidth=0.8)
    except Exception:
        pass

    ax_map.set_title(title, fontsize=13, fontweight="bold",
                     pad=12, color="#1a1a18")
    ax_map.axis("off")

    # Panel de balance poblacional
    if show_pop_balance and pop_col and pop_col in gdf.columns and ncols > 1:
        ax_pop = axes[1]
        ax_pop.set_facecolor(BG_COLOR)

        pop_by_d = gdf.groupby("__distrito__")[pop_col].sum().sort_values()
        ideal    = pop_by_d.mean()

        colors_bar = [
            "#D85A30" if abs(p - ideal)/ideal > 0.05 else "#1D9E75"
            for p in pop_by_d.values
        ]
        bars = ax_pop.barh(
            [str(d) for d in pop_by_d.index],
            pop_by_d.values,
            color=colors_bar, edgecolor="white", linewidth=0.3
        )
        ideal_label = f"Ideal: {ideal:,.0f}" if np.isfinite(ideal) else "Ideal"
        ax_pop.axvline(ideal, color="#BA7517", linewidth=1.5,
                       linestyle="--", label=ideal_label)
        ax_pop.axvline(ideal * 1.05, color="#D85A30", linewidth=0.8,
                       linestyle=":", alpha=0.7, label="+5%")
        ax_pop.axvline(ideal * 0.95, color="#D85A30", linewidth=0.8,
                       linestyle=":", alpha=0.7, label="-5%")

        ax_pop.set_xlabel(pop_col, fontsize=10, color="#3d3d3a")
        ax_pop.set_title("Balance poblacional", fontsize=11,
                         fontweight="bold", color="#1a1a18")
        ax_pop.legend(fontsize=8)
        ax_pop.spines[["top","right"]].set_visible(False)
        ax_pop.tick_params(colors="#3d3d3a")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
        print(f"Guardado: {save_path}")

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 4. Visualización de métricas de compacidad
# ──────────────────────────────────────────────────────────────────────────────

def plot_compactness(
    gdf: gpd.GeoDataFrame,
    metrics_df: pd.DataFrame,
    id_col: str,
    metric: str = "polsby_popper",
    title: str = "",
    figsize: tuple = (14, 18),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Mapa de calor de una métrica de compacidad sobre las unidades.
    """
    gdf_plot = gdf.merge(metrics_df[[id_col, metric]], on=id_col, how="left")

    fig, axes = plt.subplots(1, 2, figsize=figsize)
    fig.patch.set_facecolor(BG_COLOR)

    # Mapa
    ax1 = axes[0]
    ax1.set_facecolor(BG_COLOR)
    gdf_plot.plot(column=metric, ax=ax1, cmap="RdYlGn",
                  vmin=0, vmax=1, edgecolor="#AAAAAA", linewidth=0.1,
                  legend=True,
                  legend_kwds={"label": metric, "shrink": 0.6})
    ax1.set_title(title or f"Compacidad: {metric}",
                  fontsize=12, fontweight="bold", color="#1a1a18")
    ax1.axis("off")

    # Histograma
    ax2 = axes[1]
    ax2.set_facecolor(BG_COLOR)
    vals = metrics_df[metric].dropna()
    ax2.hist(vals, bins=30, color="#1D9E75", edgecolor="white", linewidth=0.5)
    ax2.axvline(vals.mean(), color="#D85A30", linewidth=1.5,
                linestyle="--", label=f"Media: {vals.mean():.3f}")
    ax2.axvline(vals.median(), color="#BA7517", linewidth=1.5,
                linestyle=":", label=f"Mediana: {vals.median():.3f}")
    ax2.set_xlabel(metric, fontsize=10, color="#3d3d3a")
    ax2.set_ylabel("Frecuencia", fontsize=10, color="#3d3d3a")
    ax2.set_title(f"Distribución — {metric}", fontsize=11,
                  fontweight="bold", color="#1a1a18")
    ax2.legend(fontsize=9)
    ax2.spines[["top","right"]].set_visible(False)
    ax2.tick_params(colors="#3d3d3a")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
        print(f"Guardado: {save_path}")

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 5. Tabla de equivalencia USA-Chile
# ──────────────────────────────────────────────────────────────────────────────

def plot_equivalence_table(
    figsize: tuple = (14, 5),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Visualiza la tabla de equivalencia USA-Chile como figura."""
    from .equivalence import get_equivalence_table

    df = get_equivalence_table("compact")
    df.columns = ["Nivel", "USA", "Chile INE",
                  "Tamaño USA", "Tamaño Chile"]

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")

    row_colors = [
        ["#E6F1FB", "#E6F1FB", "#E1F5EE", "#E1F5EE", "#E1F5EE"]
        if i % 2 == 0
        else ["#F8F7F4"] * 5
        for i in range(len(df))
    ]

    tbl = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc="left",
        loc="center",
        cellColours=row_colors,
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 2.0)

    # Encabezados
    for j in range(len(df.columns)):
        tbl[0, j].set_facecolor("#1D9E75")
        tbl[0, j].set_text_props(color="white", fontweight="bold")

    ax.set_title("Equivalencia censal USA ↔ Chile INE",
                 fontsize=13, fontweight="bold", pad=16, color="#1a1a18")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
        print(f"Guardado: {save_path}")

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades internas
# ──────────────────────────────────────────────────────────────────────────────

def _load_islands(
    islands_csv: Optional[str],
    indice: pd.DataFrame,
) -> tuple[set, list]:
    """Carga el CSV de islas si existe."""
    import os
    if not islands_csv or not os.path.isfile(islands_csv):
        return set(), []

    df       = pd.read_csv(islands_csv)
    id_col   = df.columns[0]
    ids      = set(df[id_col].tolist())
    id_list  = indice[indice.columns[0]].tolist()
    id_index = {id_: i for i, id_ in enumerate(id_list)}

    # No podemos reconstruir edges_art sin el grafo completo aquí
    # Se devuelve vacío y se maneja en plot_adjacency_graph
    return ids, []
