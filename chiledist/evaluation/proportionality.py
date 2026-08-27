"""
electoral.proportionality
============================
Índices de proporcionalidad entre cuotas de votos y de escaños a nivel
nacional (Gallagher, Loosemore-Hanby, Rae, ENP, seat bonus).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def gallagher_index(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> float:
    """
    Índice de desproporcionalidad de Gallagher (Least Squares Index).

    LSq = sqrt( Σ (v_i - s_i)² / 2 )

    Rango [0, 100]: 0 = perfectamente proporcional.
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return float(np.sqrt(((v - s) ** 2).sum() / 2))


def loosemore_hanby(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> float:
    """
    Índice de Loosemore-Hanby.

    LH = Σ |v_i - s_i| / 2

    Rango [0, 100]: 0 = perfectamente proporcional.
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return float((v - s).abs().sum() / 2)


def rae_index(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> float:
    """
    Índice de Rae (promedio de diferencias absolutas).

    Rae = Σ |v_i - s_i| / n_parties

    Rango [0, 100].
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return float((v - s).abs().mean())


def effective_number_of_parties(shares: pd.Series) -> float:
    """
    Número efectivo de partidos (Laakso-Taagepera).

    ENP = 1 / Σ p_i²

    Útil como ENP_votos (con vote_shares) y ENP_escaños (con seat_shares).
    """
    s = shares[shares > 0]
    if len(s) == 0:
        return float("nan")
    return float(1 / (s ** 2).sum())


def proportionality_summary(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> pd.DataFrame:
    """
    Tabla resumen con todos los índices de proporcionalidad.

    Parameters
    ----------
    vote_shares, seat_shares : pd.Series
        Cuotas nacionales en [0,1] por partido (salida de national_shares()).

    Returns
    -------
    pd.DataFrame con columnas: indice, valor, descripcion.
    """
    rows = [
        {
            "indice":      "gallagher",
            "valor":       round(gallagher_index(vote_shares, seat_shares), 4),
            "descripcion": "Índice Gallagher (LSq) — menor = más proporcional",
        },
        {
            "indice":      "loosemore_hanby",
            "valor":       round(loosemore_hanby(vote_shares, seat_shares), 4),
            "descripcion": "Índice Loosemore-Hanby — menor = más proporcional",
        },
        {
            "indice":      "rae",
            "valor":       round(rae_index(vote_shares, seat_shares), 4),
            "descripcion": "Índice Rae — menor = más proporcional",
        },
        {
            "indice":      "enp_votos",
            "valor":       round(effective_number_of_parties(vote_shares), 4),
            "descripcion": "N° efectivo de partidos (votos)",
        },
        {
            "indice":      "enp_escanos",
            "valor":       round(effective_number_of_parties(seat_shares), 4),
            "descripcion": "N° efectivo de partidos (escaños)",
        },
    ]
    return pd.DataFrame(rows)


def seat_bonus(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> pd.Series:
    """
    Prima de escaños: diferencia (escaños% − votos%) por partido o pacto.

    Positivo → sobrerepresentado (más escaños de los que corresponden
               por votos).
    Negativo → subrepresentado.

    Bajo proporcionalidad perfecta, todos los valores son 0.

    Parameters
    ----------
    vote_shares, seat_shares : pd.Series
        Cuotas en [0, 1] (salida de national_shares()).

    Returns
    -------
    pd.Series indexed by partido/pacto, valores en puntos porcentuales.
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return (s - v).rename("seat_bonus").round(4)
