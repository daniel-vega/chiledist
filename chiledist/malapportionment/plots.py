"""
malapportionment.plots
========================
Visualización de la distribución de personas/escaño y de comparaciones
internacionales de malapportionment.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from ..electoral import peso_relativo_del_voto
from .._plot_style import BG, COLOR_MAIN, COLOR_OBS, styled_ax
from .indices import _aligned


def plot_pxe_distribution(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
    label: str = "",
    reference_line: Optional[float] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Histograma de la distribución de personas por escaño.

    Parameters
    ----------
    pop_by_district, magnitudes : pd.Series
        Datos del plan.
    label : str
        Título del plan (se incluye en el título del gráfico).
    reference_line : float, optional
        Línea vertical adicional (ej. media nacional de otro plan).
    ax : plt.Axes, optional
        Eje existente.  Si ``None``, se crea una nueva figura.
    save_path : str, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    pxe      = (pop / mag).rename("pxe")
    mean_nat = float(pop.sum()) / float(mag.sum()) if mag.sum() > 0 else float("nan")

    created = ax is None
    if created:
        fig, ax = plt.subplots(figsize=(9, 5))
        fig.patch.set_facecolor(BG)
    else:
        fig = ax.get_figure()

    styled_ax(ax)
    ax.hist(pxe, bins=min(20, max(5, len(pxe))), color=COLOR_MAIN,
            alpha=0.75, edgecolor="white", linewidth=0.5)
    ax.axvline(mean_nat, color="#1A5C8A", linewidth=2, linestyle="--",
               label=f"Media nacional ({mean_nat:,.0f})")
    if reference_line is not None:
        ax.axvline(reference_line, color=COLOR_OBS, linewidth=1.5,
                   linestyle=":", label=f"Referencia ({reference_line:,.0f})")

    ax.set_xlabel("Personas por escaño", fontsize=10)
    ax.set_ylabel("Número de distritos", fontsize=10)
    ax.set_title(
        f"Distribución de personas/escaño{' — ' + label if label else ''}",
        fontsize=11, fontweight="bold",
    )
    ax.legend(fontsize=9)
    if save_path and created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG)
    return fig


def plot_malapportionment_ranking(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
    label: str = "",
    top_n: Optional[int] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Ranking de distritos por peso relativo del voto.

    Ordena los distritos de mayor (más subrepresentados) a menor
    peso relativo (más sobrerrepresentados) y los muestra como barras
    horizontales con la línea de equidad en 1.0.

    Parameters
    ----------
    top_n : int, optional
        Si se especifica, muestra solo los ``top_n`` distritos más extremos
        (los ``top_n//2`` más sobrerepresentados y los ``top_n//2`` más
        subrepresentados).

    Returns
    -------
    matplotlib.figure.Figure
    """
    pop, mag = _aligned(pop_by_district, magnitudes)
    prv      = peso_relativo_del_voto(pop, mag).sort_values(ascending=False)

    if top_n is not None and len(prv) > top_n:
        half = top_n // 2
        prv  = pd.concat([prv.head(half), prv.tail(half)])

    colors = [COLOR_OBS if v > 1.0 else COLOR_MAIN for v in prv.values]

    created = ax is None
    if created:
        figsize = (10, max(4, len(prv) * 0.35))
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(BG)
    else:
        fig = ax.get_figure()

    styled_ax(ax)
    y_pos = range(len(prv))
    ax.barh(list(y_pos), prv.values, color=colors, alpha=0.82, edgecolor="none")
    ax.axvline(1.0, color="#1A5C8A", linewidth=1.5, linestyle="--", zorder=3)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([str(i) for i in prv.index], fontsize=8)
    ax.set_xlabel("Peso relativo del voto (1.0 = equidad)", fontsize=10)
    ax.set_title(
        f"Ranking de distritos por representación{' — ' + label if label else ''}",
        fontsize=11, fontweight="bold",
    )
    under_lbl = mpatches.Patch(color=COLOR_OBS,  label="Subrepresentado (PxE > media)")
    over_lbl  = mpatches.Patch(color=COLOR_MAIN, label="Sobrerrepresentado (PxE < media)")
    ax.legend(handles=[under_lbl, over_lbl], fontsize=8, loc="lower right")
    plt.tight_layout()
    if save_path and created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG)
    return fig


def plot_international_comparison(
    comparison_df: pd.DataFrame,
    metric: str = "samuels_snyder",
    metric_label: Optional[str] = None,
    title: Optional[str] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Dot-plot de comparación internacional de malapportionment.

    Parameters
    ----------
    comparison_df : pd.DataFrame
        Salida de :func:`international_comparison`.
    metric : str
        Columna a graficar.  Default: ``"samuels_snyder"``.
    metric_label : str, optional
        Etiqueta del eje.  Default: el nombre de la columna.
    title : str, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    if metric not in comparison_df.columns:
        raise ValueError(f"Métrica '{metric}' no encontrada en comparison_df.")

    df = comparison_df[[metric, "type"]].dropna(subset=[metric]).sort_values(metric)
    if df.empty:
        raise ValueError("No hay datos válidos para graficar.")

    metric_label = metric_label or metric.replace("_", " ").title()

    colors = [
        "#1D9E75" if t == "custom" else "#1A5C8A"
        for t in df["type"]
    ]

    created = ax is None
    if created:
        figsize = (10, max(4, len(df) * 0.45))
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(BG)
    else:
        fig = ax.get_figure()

    styled_ax(ax)
    y_pos = range(len(df))
    ax.barh(list(y_pos), df[metric].values, color=colors, alpha=0.82,
            edgecolor="none", height=0.55)

    # Value labels
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row[metric] + df[metric].max() * 0.01, i,
                f"{row[metric]:.3f}", va="center", fontsize=8)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([str(i) for i in df.index], fontsize=9)
    ax.set_xlabel(metric_label, fontsize=10)
    ax.set_title(
        title or f"Comparación internacional — {metric_label}",
        fontsize=11, fontweight="bold",
    )

    bench = mpatches.Patch(color="#1A5C8A", label="Benchmark internacional")
    cstm  = mpatches.Patch(color="#1D9E75", label="Planes ChileDist")
    ax.legend(handles=[bench, cstm], fontsize=8, loc="lower right")
    plt.tight_layout()
    if save_path and created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG)
    return fig
