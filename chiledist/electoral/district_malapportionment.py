"""
electoral.district_malapportionment
======================================
Malapportionment a nivel de circunscripción individual: personas por
escaño, peso relativo del voto, umbral efectivo y margen del último
escaño. Complementa los índices agregados de :mod:`chiledist.malapportionment`
(un escalar por plan) con series por distrito.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def personas_por_escano(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> pd.Series:
    """
    Personas por escaño por circunscripción electoral.

    Métrica central de malapportionment: cuántas personas debe representar
    cada diputado según la distribución geográfica del plan.

    Parameters
    ----------
    pop_by_district : pd.Series
        Población por circunscripción (indexed by district_id).
    magnitudes : pd.Series
        Escaños asignados por circunscripción (indexed by district_id).

    Returns
    -------
    pd.Series (mismos índices) con personas / escaño por circunscripción.
    """
    common = pop_by_district.index.intersection(magnitudes.index)
    pop = pop_by_district.reindex(common)
    mag = magnitudes.reindex(common).replace(0, np.nan)
    return (pop / mag).rename("personas_por_escano")


def peso_relativo_del_voto(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> pd.Series:
    """
    Peso relativo del voto respecto a la media nacional.

    peso = (personas_por_escano_i) / media_nacional

    Interpretación:
        peso < 1.0 → ese voto vale MÁS que el promedio (subrepresentado en pop)
        peso > 1.0 → ese voto vale MENOS que el promedio (sobrerrepresentado en pop)
        peso = 0.5 → un voto en este distrito equivale a dos votos promedio

    Este es el estándar internacional de malapportionment (Samuels & Snyder 2001).

    Returns
    -------
    pd.Series (mismos índices).
    """
    common = pop_by_district.index.intersection(magnitudes.index)
    pop    = pop_by_district.reindex(common)
    mag    = magnitudes.reindex(common)

    # Media nacional correcta: total_pop / total_seats (no media aritmética de cocientes).
    # Las dos difieren cuando los distritos tienen tamaños distintos — que es siempre el caso.
    # Estándar: Samuels & Snyder (2001), Cox & Katz (2002).
    valid         = mag > 0
    total_pop     = pop[valid].sum()
    total_seats   = mag[valid].sum()

    if total_seats == 0 or total_pop == 0:
        pxe = personas_por_escano(pop_by_district, magnitudes)
        return pd.Series(np.nan, index=pxe.index, name="peso_relativo_del_voto")

    media_nacional = total_pop / total_seats
    pxe = personas_por_escano(pop_by_district, magnitudes)
    return (pxe / media_nacional).rename("peso_relativo_del_voto")


def umbral_efectivo(magnitud: int) -> float:
    """
    Umbral superior (T_U) de Taagepera para un distrito de M escaños.

    Fórmula: T_U = 1 / (M + 1)

    T_U es el umbral más exigente: un partido con menos del T_U% de votos
    prácticamente NO puede ganar un escaño bajo D'Hondt.  No confundir con:
        T_L = 1/(2M)           — umbral inferior (mínimo para ganar)
        T_e = √(T_L × T_U)    — umbral efectivo geométrico (Taagepera 1998)

    Esta función implementa T_U porque es la cota conservadora estándar para
    análisis de barreras de entrada. T_U sobreestima la barrera en ~20–30%
    respecto a T_e; si necesitas el umbral geométrico calcula √(T_U × T_U/2).

    Ejemplos:
        M=3 → 25.0%   (T_e ≈ 20.4%)
        M=5 → 16.7%   (T_e ≈ 12.9%)
        M=8 → 11.1%   (T_e ≈  8.3%)

    Returns
    -------
    float en (0, 1].
    """
    if magnitud <= 0:
        return 1.0
    return round(1.0 / (magnitud + 1), 4)


def margen_ultimo_escano(
    votes: "dict[str, int | float]",
    seats: int,
    threshold: float = 0.0,
) -> dict:
    """
    Margen del último escaño en una circunscripción electoral.

    Calcula la diferencia entre el cociente D'Hondt del último escaño
    asignado y el cociente más alto de los no ganadores.  Un margen
    pequeño indica que el resultado es altamente sensible a pequeños
    cambios en votos o geografía distrital.

    Parameters
    ----------
    votes : dict {lista_o_partido: n_votos}
    seats : int
    threshold : float
        Umbral mínimo de votos (0.0 = sin umbral).

    Returns
    -------
    dict con:
        ultimo_ganador   : nombre del partido/lista que ganó el último escaño
        primer_perdedor  : nombre del que no ganó por menor cociente
        cociente_ganador : cociente D'Hondt del último escaño (votos/n_escaños)
        cociente_perdedor: mejor cociente de los perdedores
        margen_cociente  : diferencia de cocientes (ganador − perdedor)
        margen_pct       : margen como % del cociente ganador
    """
    if seats <= 0 or not votes:
        return {}

    votes = {p: max(0, v) for p, v in votes.items()}
    total = sum(votes.values())
    if total == 0:
        return {}

    eligible = {p: v for p, v in votes.items() if v / total >= threshold}
    if not eligible:
        return {}

    # Simular D'Hondt paso a paso registrando cocientes
    seat_counts: dict[str, int] = {p: 0 for p in eligible}
    cocientes_asignados = []

    for _ in range(seats):
        cocientes_actuales = {
            p: eligible[p] / (seat_counts[p] + 1) for p in eligible
        }
        best = max(cocientes_actuales,
                   key=lambda p: (cocientes_actuales[p], eligible[p], p))
        cocientes_asignados.append((best, cocientes_actuales[best]))
        seat_counts[best] += 1

    ultimo_ganador, cociente_ganador = cocientes_asignados[-1]

    # Cociente que cada partido tendría en la siguiente asignación.
    # Para los perdedores (seat_counts sin cambio tras el último paso),
    # este cociente coincide con el que tenían EN el último paso.
    cocientes_siguientes = {
        p: eligible[p] / (seat_counts[p] + 1) for p in eligible
    }
    # Excluir explícitamente al ultimo_ganador: queremos el mejor cociente
    # entre quienes NO ganaron el último escaño.
    primer_perdedor = max(
        [p for p in eligible if p != ultimo_ganador],
        key=lambda p: cocientes_siguientes[p],
        default=None,
    )

    if primer_perdedor is None:
        return {
            "ultimo_ganador":    ultimo_ganador,
            "primer_perdedor":   None,
            "cociente_ganador":  round(cociente_ganador, 2),
            "cociente_perdedor": None,
            "margen_cociente":   None,
            "margen_pct":        None,
        }

    cociente_perdedor = cocientes_siguientes[primer_perdedor]
    margen = cociente_ganador - cociente_perdedor

    return {
        "ultimo_ganador":    ultimo_ganador,
        "primer_perdedor":   primer_perdedor,
        "cociente_ganador":  round(cociente_ganador, 2),
        "cociente_perdedor": round(cociente_perdedor, 2),
        "margen_cociente":   round(margen, 2),
        "margen_pct":        round(margen / cociente_ganador * 100, 2)
                             if cociente_ganador > 0 else None,
    }
