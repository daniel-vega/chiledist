"""
malapportionment
==================
Índices de malapportionment geográfico comparables internacionalmente.

Complementa las funciones de nivel distrital de ``electoral``
(:func:`personas_por_escano`, :func:`peso_relativo_del_voto`) con índices
**globales** (un escalar por plan) que permiten comparar sistemas electorales
entre países y entre escenarios de redistritaje.

Nota sobre ``peso_relativo_del_voto``
--------------------------------------
La función :func:`~chiledist.electoral.peso_relativo_del_voto` de
``electoral`` ya usa el denominador correcto::

    media_nacional = total_pop / total_seats    # ← correcto

Es la única forma de comparar pesos entre distritos de tamaño desigual.
La alternativa incorrecta sería usar la media aritmética de los cocientes
PxE_i, que sobrepondera a los distritos pequeños.  Estándar: Samuels &
Snyder (2001), Cox & Katz (2002).

Uso rápido
----------
    import chiledist as cd
    import chiledist.malapportionment as mala
    import pandas as pd

    pop_d   = pd.Series({1: 500_000, 2: 300_000, 3: 200_000})
    magnitudes = pd.Series({1: 3, 2: 3, 3: 2})   # suma ≠ proporcional

    print(mala.samuels_snyder_index(pop_d, magnitudes))
    summary = mala.malapportionment_summary(pop_d, magnitudes, label="mi_plan")

    # Comparación internacional
    table = mala.international_comparison({"mi_plan": summary})
    print(table[["samuels_snyder", "gini_pop_weighted", "max_min_ratio"]])
"""

from .indices import (
    samuels_snyder_index,
    loosemore_hanby_malapportionment,
    gini_personas_por_escano,
    max_min_representation_ratio,
    malapportionment_summary,
)
from .comparison import (
    compare_plans,
    international_comparison,
    BENCHMARK_MALAPPORTIONMENT,
)
from .plots import (
    plot_pxe_distribution,
    plot_malapportionment_ranking,
    plot_international_comparison,
)

__all__ = [
    "samuels_snyder_index",
    "loosemore_hanby_malapportionment",
    "gini_personas_por_escano",
    "max_min_representation_ratio",
    "malapportionment_summary",
    "compare_plans",
    "international_comparison",
    "plot_pxe_distribution",
    "plot_malapportionment_ranking",
    "plot_international_comparison",
    "BENCHMARK_MALAPPORTIONMENT",
]
