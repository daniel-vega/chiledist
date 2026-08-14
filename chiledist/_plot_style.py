"""
Paleta y helpers de estilo compartidos por los módulos de análisis que
generan figuras (malapportionment, pareto_sweep, electoral_ensemble,
scenario_comparison). Evita redefinir los mismos colores/helper en cada uno.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

BG = "#F8F7F4"
COLOR_MAIN = "#1D9E75"
COLOR_OBS = "#D85A30"
COLOR_PARETO = "#1A5C8A"
COLOR_KNEE = "#D85A30"


def styled_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.spines[["top", "right"]].set_visible(False)
