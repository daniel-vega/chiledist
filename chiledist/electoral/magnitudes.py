"""
electoral.magnitudes
======================
Asignación de magnitudes de escaño (Hamilton acotado) y comparación entre
magnitudes vigentes y recalculadas con población actualizada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import TOTAL_ESCANOS_CAMARA, MIN_ESCANOS_DISTRITO, MAX_ESCANOS_DISTRITO


def assign_seat_magnitudes(
    pop_by_district: pd.Series,
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
) -> pd.Series:
    """
    Asigna magnitudes de escaño a circunscripciones electorales por población.

    Usa el método Hamilton (resto mayor) con cotas mínima y máxima por
    distrito, que es el método estándar en la Ley 18.700.

    Parameters
    ----------
    pop_by_district : pd.Series
        Población por circunscripción electoral (indexed by district id).
    total_seats : int
        Total de escaños a distribuir (default: 155 para Cámara de Diputados).
    min_seats, max_seats : int
        Cotas por distrito (default: 3 / 8 según Ley 18.700).

    Returns
    -------
    pd.Series (mismos índices que pop_by_district): escaños asignados (int).

    Raises
    ------
    ValueError
        Si el total de escaños no alcanza para asignar min_seats a cada
        distrito.
    """
    n = len(pop_by_district)
    if n == 0:
        return pd.Series(dtype=int)

    if total_seats < n * min_seats:
        raise ValueError(
            f"total_seats ({total_seats}) insuficiente para {n} distritos "
            f"con min_seats={min_seats} (requiere ≥ {n * min_seats})."
        )

    total_pop = pop_by_district.sum()
    if total_pop == 0:
        return pd.Series(min_seats, index=pop_by_district.index)

    # Cada distrito parte con mínimo garantizado
    seats = pd.Series(min_seats, index=pop_by_district.index, dtype=int)
    remaining = total_seats - n * min_seats
    capacity  = max_seats - min_seats  # escaños adicionales máximos

    if remaining == 0:
        return seats

    # Parte entera proporcional (con cota de capacidad)
    ideal     = pop_by_district / total_pop * remaining
    base_add  = ideal.apply(np.floor).astype(int).clip(upper=capacity)
    remainders = ideal - base_add

    seats    += base_add
    remaining -= int(base_add.sum())

    # Distribuir restantes por mayor resto, respetando max_seats
    if remaining > 0:
        puede_recibir = seats < max_seats
        orden = remainders[puede_recibir].sort_values(ascending=False)
        for idx in orden.index[:remaining]:
            seats[idx] += 1

    return seats


def comparar_magnitudes(
    pop_by_district: pd.Series,
    magnitudes_vigentes: "dict[int, int] | pd.Series",
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
) -> pd.DataFrame:
    """
    Compara las magnitudes vigentes con las que resultarían de reasignar
    escaños según la población actualizada (método Hamilton acotado).

    Útil para el análisis contrafactual de H3: ¿qué cambiaría si se
    actualizaran las magnitudes con el Censo 2024?

    Parameters
    ----------
    pop_by_district : pd.Series
        Población actualizada por circunscripción (Censo 2024 recomendado).
        El índice debe contener los mismos district_ids que magnitudes_vigentes.
    magnitudes_vigentes : dict | pd.Series
        Magnitudes actuales (ej. MAGNITUDES_LEGALES_LEY20840).
    total_seats, min_seats, max_seats : int
        Parámetros de assign_seat_magnitudes().

    Returns
    -------
    pd.DataFrame con columnas:
        distrito, magnitud_vigente, magnitud_nueva, delta,
        pop_vigente_pxe (personas/escaño con magnitud vigente),
        pop_nueva_pxe   (personas/escaño con magnitud nueva).
    """
    if isinstance(magnitudes_vigentes, dict):
        mag_vig = pd.Series(magnitudes_vigentes)
    else:
        mag_vig = magnitudes_vigentes.copy()

    mag_nueva = assign_seat_magnitudes(
        pop_by_district.reindex(mag_vig.index, fill_value=0),
        total_seats=total_seats,
        min_seats=min_seats,
        max_seats=max_seats,
    )

    pop_aligned = pop_by_district.reindex(mag_vig.index, fill_value=0)

    df = pd.DataFrame({
        "distrito":          mag_vig.index,
        "magnitud_vigente":  mag_vig.values,
        "magnitud_nueva":    mag_nueva.reindex(mag_vig.index, fill_value=min_seats).values,
    })
    df["delta"] = df["magnitud_nueva"] - df["magnitud_vigente"]

    df["pop"] = pop_aligned.values
    # Indexing directo sobre las columnas del df (sin .values) para evitar
    # alineación posicional frágil tras posibles reordenamientos.
    df["pop_vigente_pxe"] = (df["pop"] / df["magnitud_vigente"].replace(0, np.nan)).round(0).astype("Int64")
    df["pop_nueva_pxe"]   = (df["pop"] / df["magnitud_nueva"].replace(0, np.nan)).round(0).astype("Int64")

    return df.sort_values("delta", ascending=False).reset_index(drop=True)
