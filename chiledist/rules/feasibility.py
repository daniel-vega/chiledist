"""
feasibility.py
===============
Chequeo determinista de factibilidad poblacional, previo a la búsqueda
de partición inicial (recursive_tree_part) y a la escalera de
tolerancias de scripts/redistritaje.py.

Una unidad de decisión (CUT o ID_DIST, según el escenario) es
indivisible para el algoritmo: no puede fragmentarse entre distritos.
Si la población de una sola unidad excede el ideal por distrito en más
de lo que permite pop_tolerance, todo plan que la contenga (la única
opción posible) viola la tolerancia — sin importar cuántas semillas o
intentos de inicialización se prueben. Este módulo detecta esa
situación de forma barata y determinista, antes de invertir tiempo en
recursive_tree_part o en la cadena ReCom.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Optional

# Código estable y machine-readable para el único motivo de inviabilidad que
# este preflight puede demostrar. Un status "infeasible_population" aguas
# abajo (scripts/redistritaje.py, manifests, resúmenes) debe reportar este
# reason — a diferencia de "sin_particion", que es un fallo de búsqueda del
# algoritmo de inicialización y NO implica que el espacio de planes sea
# matemáticamente vacío.
REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND = "indivisible_unit_exceeds_population_bound"


@dataclasses.dataclass(frozen=True)
class PopulationFeasibilityResult:
    """Resultado del chequeo de factibilidad poblacional."""

    feasible: bool
    reason: Optional[str]
    total_population: float
    n_districts: int
    ideal_population: float
    largest_indivisible_unit: float
    largest_indivisible_unit_id: Any
    minimum_required_tolerance: float
    requested_tolerance: float

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)

    def diagnostic_message(self) -> str:
        if self.feasible:
            return (
                "Factible: la unidad indivisible más poblada "
                f"({self.largest_indivisible_unit_id!r}) requiere una "
                f"tolerancia mínima de ±{self.minimum_required_tolerance*100:.2f}%, "
                f"dentro de la tolerancia solicitada "
                f"(±{self.requested_tolerance*100:.2f}%)."
            )
        return (
            "Escenario estructuralmente inviable por población: la unidad "
            f"indivisible {self.largest_indivisible_unit_id!r} tiene "
            f"{self.largest_indivisible_unit:,.0f} hab./viv. frente a un "
            f"ideal de {self.ideal_population:,.1f} por distrito "
            f"({self.n_districts} distritos, población total "
            f"{self.total_population:,.0f}). Esto exige una tolerancia "
            f"mínima de ±{self.minimum_required_tolerance*100:.2f}%, mayor "
            f"que la tolerancia solicitada de ±{self.requested_tolerance*100:.2f}%. "
            "Ninguna cantidad de semillas ni intentos de inicialización "
            "(recursive_tree_part) puede resolver esto: la unidad no puede "
            "partirse, así que su desviación poblacional es inevitable "
            "para cualquier plan."
        )


def check_population_feasibility(
    unit_populations: Mapping[Any, float],
    n_districts: int,
    pop_tolerance: float,
) -> PopulationFeasibilityResult:
    """
    Determina si la tolerancia poblacional solicitada es matemáticamente
    alcanzable dada la población de las unidades de decisión indivisibles.

        ideal_pop = total_pop / n_districts
        min_required_tolerance = max(0, pop_i / ideal_pop - 1) sobre todas
                                  las unidades i
        feasible = min_required_tolerance <= pop_tolerance

    Parameters
    ----------
    unit_populations : Mapping[Any, float]
        {id_unidad: población} de cada unidad de decisión indivisible
        (ej. CUT en modo "legal", ID_DIST en modos APC).
    n_districts : int
        Número de distritos objetivo.
    pop_tolerance : float
        Tolerancia poblacional solicitada (ej. 0.05 = ±5%).

    Returns
    -------
    PopulationFeasibilityResult
    """
    if n_districts < 1:
        raise ValueError("n_districts debe ser >= 1.")
    if not unit_populations:
        raise ValueError("unit_populations no puede estar vacío.")

    total_population = float(sum(unit_populations.values()))
    if total_population <= 0:
        raise ValueError("La población total debe ser > 0.")

    ideal_population = total_population / n_districts

    largest_unit_id, largest_unit_pop = max(
        unit_populations.items(), key=lambda kv: kv[1]
    )
    largest_unit_pop = float(largest_unit_pop)

    minimum_required_tolerance = max(
        0.0, largest_unit_pop / ideal_population - 1.0
    )
    feasible = minimum_required_tolerance <= pop_tolerance

    return PopulationFeasibilityResult(
        feasible=feasible,
        reason=None if feasible else REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND,
        total_population=total_population,
        n_districts=n_districts,
        ideal_population=ideal_population,
        largest_indivisible_unit=largest_unit_pop,
        largest_indivisible_unit_id=largest_unit_id,
        minimum_required_tolerance=minimum_required_tolerance,
        requested_tolerance=pop_tolerance,
    )
