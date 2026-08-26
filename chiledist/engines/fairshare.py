"""
chiledist/fairshare.py
======================
Medidas de distancia entre asignaciones enteras de escaños
y el ideal fraccional (fair share / apportionment biproporcional).

Conceptos clave
---------------
*Fair share matrix* **Q** :
    Matriz (partido × distrito) donde Q[i,j] es el número *fraccional* de
    escaños que le corresponde al partido i en el distrito j bajo una
    representación simultáneamente proporcional a nivel nacional y distrital.

*Ideal fraccional* :
    La asignación de escaños que satisface exactamente:
    - Σ_j Q[i,j] = cuota Hamilton del partido i = (V_i / V) × S
    - Σ_i Q[i,j] = M_j (magnitud del distrito j)
    donde V_i = votos del partido i, V = votos totales, S = escaños totales.

*Asignación entera* **N** :
    La asignación observada (salida de D'Hondt), con n_{ij} ∈ ℤ≥0.
    Por la imposibilidad de divisar escaños, N ≠ Q en general.

*Distancia al fair share* :
    Medidas de cuánto difieren N y Q:
    L1 = Σ|n_{ij} − Q_{ij}|, L2 = ‖N − Q‖_F, max_dev = max|n_{ij} − Q_{ij}|.

Método biproporcional (Balinski–Ramírez)
-----------------------------------------
Q se calcula mediante Iterative Proportional Fitting (RAS / Sinkhorn)::

    1. Semilla A_{ij} = votos_{ij}  (matriz de votos brutos)
    2. Escalar filas → suma_j A[i,j] = cuota Hamilton del partido i
    3. Escalar columnas → suma_i A[i,j] = M_j
    4. Repetir hasta convergencia (max|Δ marginal| < tol)

La solución es la única matriz de la forma Q[i,j] = r_i · c_j · A[i,j]
que satisface ambos conjuntos de restricciones marginales.

Método distrital (simplificado)
---------------------------------
Q[i,j] = (v_{ij} / V_j) × M_j.  Solo satisface las restricciones de columna.
Difiere del método biproporcional cuando los partidos tienen distinta
concentración geográfica de votos.

Referencias
-----------
Balinski, M. L. & Ramírez González, V. (1999).
    Parametric Methods of Apportionment, Rounding and Production.
    *Mathematical Social Sciences*, 37(2), 107–122.

Balinski, M. L. & Young, H. P. (1982).
    *Fair Representation: Meeting the Ideal of One Man, One Vote*.
    Yale University Press.

Pukelsheim, F. (2014).
    *Proportional Representation: Apportionment Methods and Their Applications*.
    Springer.
"""

from __future__ import annotations

import warnings
from typing import Literal

import numpy as np
import pandas as pd


# ─── helpers privados ─────────────────────────────────────────────────────────

def _votes_to_matrix(
    votes_df: pd.DataFrame,
    district_col: str,
    partido_col: str,
    votos_col: str,
) -> pd.DataFrame:
    """Convierte votos en formato largo a matriz partido × distrito."""
    return (
        votes_df
        .pivot_table(
            index=partido_col,
            columns=district_col,
            values=votos_col,
            aggfunc="sum",
            fill_value=0.0,
        )
        .rename_axis(index=None, columns=None)
        .astype(float)
    )


def _ipf(
    seed: np.ndarray,
    row_targets: np.ndarray,
    col_targets: np.ndarray,
    max_iter: int,
    tol: float,
) -> tuple[np.ndarray, bool]:
    """
    Iterative Proportional Fitting (RAS / Sinkhorn).

    Encuentra la matriz Q[i,j] = r_i · c_j · seed[i,j] cuyos marginales
    (sumas de filas y columnas) igualan los objetivos dados.

    Parameters
    ----------
    seed : ndarray, shape (n_parties, n_districts)
        Matriz inicial no negativa con soporte compatible con los objetivos.
    row_targets : ndarray, length n_parties
        Suma objetivo de cada fila (cuotas Hamilton por partido).
    col_targets : ndarray, length n_districts
        Suma objetivo de cada columna (magnitudes).
    max_iter : int
        Máximo de iteraciones.
    tol : float
        Tolerancia de convergencia en norma máxima sobre los marginales.

    Returns
    -------
    (Q, converged) : tuple
        Q es la matriz ajustada; converged es True si alcanzó tol.
    """
    Q = seed.copy().astype(float)
    for _ in range(max_iter):
        # Escalar filas
        row_sums = Q.sum(axis=1)
        row_scale = np.where(row_sums > 0, row_targets / row_sums, 0.0)
        Q = Q * row_scale[:, np.newaxis]

        # Escalar columnas
        col_sums = Q.sum(axis=0)
        col_scale = np.where(col_sums > 0, col_targets / col_sums, 0.0)
        Q = Q * col_scale[np.newaxis, :]

        # Verificar convergencia en ambos marginales
        if (
            np.abs(Q.sum(axis=1) - row_targets).max() < tol
            and np.abs(Q.sum(axis=0) - col_targets).max() < tol
        ):
            return Q, True

    return Q, False


def _align(
    a: pd.DataFrame,
    b: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Alinea dos matrices partido × distrito al índice/columnas unión.
    Celdas faltantes se rellenan con 0.
    """
    parties   = a.index.union(b.index)
    districts = a.columns.union(b.columns)
    return (
        a.reindex(index=parties, columns=districts, fill_value=0.0),
        b.reindex(index=parties, columns=districts, fill_value=0.0),
    )


# ─── API pública ──────────────────────────────────────────────────────────────

def fair_share_matrix(
    votes_df: pd.DataFrame,
    magnitudes: "pd.Series | dict",
    district_col: str = "district",
    partido_col: str = "partido",
    votos_col: str = "votos",
    method: Literal["biproportional", "district"] = "biproportional",
    max_iter: int = 2_000,
    tol: float = 1e-10,
) -> pd.DataFrame:
    """
    Calcula la matriz de *fair share* (asignación ideal fraccional).

    Parameters
    ----------
    votes_df : pd.DataFrame
        Votos en formato largo: debe contener al menos las columnas
        ``district_col``, ``partido_col``, ``votos_col``.
        Salida típica de :func:`chiledist.aggregate_votes`.
    magnitudes : pd.Series or dict
        Escaños por distrito.  Claves/índice deben coincidir con los
        valores presentes en ``votes_df[district_col]``.
    district_col, partido_col, votos_col : str
        Nombres de columnas en ``votes_df``.
    method : {'biproportional', 'district'}, default 'biproportional'
        ``'biproportional'`` :
            Satisface simultáneamente restricciones de fila (cuotas Hamilton
            nacionales por partido) y de columna (magnitudes distritales)
            mediante Iterative Proportional Fitting.
        ``'district'`` :
            Q[i,j] = (v_{ij} / V_j) × M_j.  Solo satisface restricciones
            de columna; en general no cumple las de fila.
    max_iter : int, default 2000
        Máximo de iteraciones IPF (solo ``'biproportional'``).
    tol : float, default 1e-10
        Tolerancia de convergencia IPF.

    Returns
    -------
    pd.DataFrame
        Matriz partido × distrito con valores ≥ 0.
        - Índice: nombre de partidos.
        - Columnas: IDs de distrito.
        - ``Q.sum(axis=0)`` ≈ magnitudes (error < tol).
        - ``Q.sum(axis=1)`` = cuotas Hamilton nacionales
          (solo garantizado en ``'biproportional'``).

    Raises
    ------
    ValueError
        Si ``votes_df`` carece de columnas requeridas, si algún distrito
        en ``votes_df`` no está en ``magnitudes``, o si hay votos negativos.

    Warns
    -----
    UserWarning
        Si IPF no converge en ``max_iter`` iteraciones.

    Notes
    -----
    La suma de columna j puede diferir de M_j en menos de ``tol`` por
    aritmética de punto flotante.

    Examples
    --------
    >>> import pandas as pd
    >>> import chiledist.fairshare as fs
    >>> votes = pd.DataFrame({
    ...     "district": [1, 1, 2, 2],
    ...     "partido":  ["A", "B", "A", "B"],
    ...     "votos":    [600, 400, 200, 800],
    ... })
    >>> mags = pd.Series({1: 5, 2: 5})
    >>> fs.fair_share_matrix(votes, mags)
         1    2
    A  3.0  1.0
    B  2.0  4.0
    """
    # ── validación ────────────────────────────────────────────────────────
    required = {district_col, partido_col, votos_col}
    missing_cols = required - set(votes_df.columns)
    if missing_cols:
        raise ValueError(
            f"votes_df no contiene las columnas: {sorted(missing_cols)}. "
            f"Columnas disponibles: {list(votes_df.columns)}."
        )
    if votes_df[votos_col].lt(0).any():
        raise ValueError("votes_df contiene votos negativos.")

    mag = pd.Series(magnitudes, dtype=float)
    if (mag <= 0).any():
        bad = mag[mag <= 0].to_dict()
        raise ValueError(f"magnitudes contiene valores ≤ 0: {bad}.")

    uncovered = set(votes_df[district_col].unique()) - set(mag.index)
    if uncovered:
        sample = sorted(uncovered)[:5]
        suffix = "…" if len(uncovered) > 5 else ""
        raise ValueError(
            f"magnitudes no cubre {len(uncovered)} distrito(s) en votes_df: "
            f"{sample}{suffix}."
        )

    # ── convertir a matriz ────────────────────────────────────────────────
    V = _votes_to_matrix(votes_df, district_col, partido_col, votos_col)
    # Mantener solo distritos cubiertos, en el orden de magnitudes
    districts = mag.index.intersection(V.columns)
    V = V[districts]
    mag_vals = mag[districts].to_numpy(dtype=float)

    if method == "district":
        col_sums = V.to_numpy().sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            fracs = np.where(col_sums > 0, V.to_numpy() / col_sums, 0.0)
        Q_vals = fracs * mag_vals[np.newaxis, :]

    elif method == "biproportional":
        total_v = V.to_numpy().sum()
        if total_v <= 0:
            raise ValueError("El total de votos en votes_df es cero.")
        total_s = float(mag_vals.sum())
        row_targets = V.to_numpy().sum(axis=1) / total_v * total_s

        Q_vals, converged = _ipf(
            seed=V.to_numpy(),
            row_targets=row_targets,
            col_targets=mag_vals,
            max_iter=max_iter,
            tol=tol,
        )
        if not converged:
            warnings.warn(
                f"IPF no convergió en {max_iter} iteraciones (tol={tol}). "
                "Considere aumentar max_iter.",
                UserWarning,
                stacklevel=2,
            )
    else:
        raise ValueError(
            f"method={method!r} no reconocido. Use 'biproportional' o 'district'."
        )

    return pd.DataFrame(Q_vals, index=V.index, columns=V.columns)


def results_to_matrix(
    results: pd.DataFrame,
    district_col: str = "district",
    partido_col: str = "partido",
    escanos_col: str = "escanos",
) -> pd.DataFrame:
    """
    Convierte la salida de ``run_electoral_plan`` a una matriz partido × distrito.

    Parameters
    ----------
    results : pd.DataFrame
        DataFrame con columnas [district_col, partido_col, escanos_col].
        Salida típica de :func:`chiledist.run_electoral_plan` o
        :func:`chiledist.run_electoral_plan_binivel`.
    district_col, partido_col, escanos_col : str
        Nombres de columna.

    Returns
    -------
    pd.DataFrame
        Matriz entera partido × distrito (celdas sin dato = 0).

    Examples
    --------
    >>> import chiledist as cd
    >>> import chiledist.fairshare as fs
    >>> results = cd.run_electoral_plan(votes_by_district, magnitudes)
    >>> N = fs.results_to_matrix(results)
    >>> Q = fs.fair_share_matrix(votes_by_district, magnitudes)
    >>> fs.fair_share_summary(N, Q)
    """
    missing = {district_col, partido_col, escanos_col} - set(results.columns)
    if missing:
        raise ValueError(
            f"results no contiene las columnas: {sorted(missing)}. "
            f"Columnas disponibles: {list(results.columns)}."
        )
    return (
        results
        .pivot_table(
            index=partido_col,
            columns=district_col,
            values=escanos_col,
            aggfunc="sum",
            fill_value=0,
        )
        .rename_axis(index=None, columns=None)
    )


def l1_distance_fair_share(
    integer_allocation: pd.DataFrame,
    fair_shares: pd.DataFrame,
    normalize: bool = False,
) -> float:
    """
    Distancia L1 entre asignación entera y fair share.

    .. math::

        L_1 = \\sum_{i,j} |n_{ij} - Q_{ij}|

    Interpretación: número total de "escaños fuera de lugar" al sumar las
    desviaciones absolutas de todas las celdas.  L1 = 0 si y solo si
    n_{ij} = Q_{ij} ∀ i,j (requiere que todas las cuotas sean enteras).

    Parameters
    ----------
    integer_allocation : pd.DataFrame
        Matriz partido × distrito con escaños enteros.  Salida de
        :func:`results_to_matrix`.
    fair_shares : pd.DataFrame
        Matriz partido × distrito fraccional.  Salida de
        :func:`fair_share_matrix`.
    normalize : bool, default False
        Si True, divide por el total de escaños ``Σ M_j``.
        La distancia normalizada ∈ [0, 2].

    Returns
    -------
    float

    Notes
    -----
    Las matrices se alinean a la unión de índices/columnas antes del cálculo.
    Celdas ausentes en alguna de las matrices se tratan como 0.

    Examples
    --------
    >>> import pandas as pd
    >>> import chiledist.fairshare as fs
    >>> N = pd.DataFrame({"D1": {"A": 3, "B": 2}, "D2": {"A": 1, "B": 4}})
    >>> Q = pd.DataFrame({"D1": {"A": 3.0, "B": 2.0}, "D2": {"A": 1.0, "B": 4.0}})
    >>> fs.l1_distance_fair_share(N, Q)
    0.0
    """
    n, q = _align(integer_allocation.astype(float), fair_shares.astype(float))
    l1 = float(np.abs(n.to_numpy() - q.to_numpy()).sum())
    if normalize:
        total = float(fair_shares.to_numpy().sum())
        if total > 0:
            l1 /= total
    return l1


def l2_distance_fair_share(
    integer_allocation: pd.DataFrame,
    fair_shares: pd.DataFrame,
    normalize: bool = False,
) -> float:
    """
    Distancia L2 (norma de Frobenius) entre asignación entera y fair share.

    .. math::

        L_2 = \\sqrt{\\sum_{i,j} (n_{ij} - Q_{ij})^2}

    Penaliza más que L1 las desviaciones grandes en celdas individuales.
    Si ``normalize=True``, devuelve el RMSE por celda.

    Parameters
    ----------
    integer_allocation : pd.DataFrame
    fair_shares : pd.DataFrame
    normalize : bool, default False
        Si True, devuelve RMSE = L2 / sqrt(n_celdas) en lugar de la norma.

    Returns
    -------
    float

    Examples
    --------
    >>> fs.l2_distance_fair_share(N, Q)          # Frobenius
    >>> fs.l2_distance_fair_share(N, Q, normalize=True)  # RMSE por celda
    """
    n, q = _align(integer_allocation.astype(float), fair_shares.astype(float))
    diff = n.to_numpy() - q.to_numpy()
    if normalize:
        return float(np.sqrt((diff ** 2).mean()))
    return float(np.sqrt((diff ** 2).sum()))


def max_cell_deviation(
    integer_allocation: pd.DataFrame,
    fair_shares: pd.DataFrame,
) -> dict:
    """
    Desviación absoluta máxima entre asignación entera y fair share.

    .. math::

        \\text{max\\_dev} = \\max_{i,j} |n_{ij} - Q_{ij}|

    Parameters
    ----------
    integer_allocation : pd.DataFrame
        Matriz partido × distrito con escaños enteros.
    fair_shares : pd.DataFrame
        Matriz partido × distrito fraccional.

    Returns
    -------
    dict con claves:
        max_dev : float
            Magnitud de la desviación máxima.
        partido : str
            Nombre del partido que alcanza la desviación máxima.
        distrito : int or str
            ID del distrito que alcanza la desviación máxima.
        n_obs : float
            Escaños observados en esa celda.
        q_ideal : float
            Fair share en esa celda.
        direction : str
            ``'sobre'`` si n > Q, ``'sub'`` si n < Q, ``'exacto'`` si n = Q.

    Notes
    -----
    Ante empate entre celdas, se devuelve la primera en orden lexicográfico
    (NumPy argmax devuelve el índice plano más bajo).

    Examples
    --------
    >>> fs.max_cell_deviation(N, Q)
    {'max_dev': 1.5, 'partido': 'UDI', 'distrito': 3, ...}
    """
    n, q = _align(integer_allocation.astype(float), fair_shares.astype(float))
    abs_diff = np.abs(n.to_numpy() - q.to_numpy())
    flat_idx = int(np.argmax(abs_diff))
    row_idx, col_idx = np.unravel_index(flat_idx, abs_diff.shape)

    n_obs   = float(n.to_numpy()[row_idx, col_idx])
    q_ideal = float(q.to_numpy()[row_idx, col_idx])
    dev     = float(abs_diff[row_idx, col_idx])
    direction = "exacto" if dev == 0.0 else ("sobre" if n_obs > q_ideal else "sub")

    return {
        "max_dev":   dev,
        "partido":   n.index[row_idx],
        "distrito":  n.columns[col_idx],
        "n_obs":     n_obs,
        "q_ideal":   q_ideal,
        "direction": direction,
    }


def fair_share_summary(
    integer_allocation: pd.DataFrame,
    fair_shares: pd.DataFrame,
    label: str = "",
) -> dict:
    """
    Resumen completo de distancias al ideal fraccional.

    Combina L1, L2, RMSE, max_dev y estadísticas de sobre/sub-asignación
    en un único diccionario listo para agregar a ``ensemble_stats``.

    Parameters
    ----------
    integer_allocation : pd.DataFrame
        Matriz partido × distrito con escaños enteros (salida de
        :func:`results_to_matrix`).
    fair_shares : pd.DataFrame
        Matriz partido × distrito con fair shares (salida de
        :func:`fair_share_matrix`).
    label : str, optional
        Etiqueta identificatoria del plan (ej. ``"legal"``, ``"apc_soft_p0.25"``).
        Se incluye bajo la clave ``"plan"`` en el resultado.

    Returns
    -------
    dict con claves:
        plan : str
            Valor de ``label``.
        l1 : float
            Distancia L1 absoluta = Σ|n_{ij} − Q_{ij}|.
        l1_norm : float
            L1 / Σ M_j ∈ [0, 2].  Fracción normalizada de escaños desplazados.
        l2 : float
            Distancia L2 (norma de Frobenius).
        rmse : float
            Desviación cuadrática media por celda = L2 / sqrt(n_celdas).
        max_dev : float
            Desviación absoluta máxima en una sola celda (partido × distrito).
        max_dev_partido : str
            Partido que alcanza ``max_dev``.
        max_dev_distrito : int or str
            Distrito que alcanza ``max_dev``.
        max_dev_direction : str
            ``'sobre'``, ``'sub'`` o ``'exacto'``.
        n_celdas : int
            Total de celdas partido × distrito.
        n_sobre : int
            Celdas con n_{ij} > Q_{ij} + 0.01 (sobre-asignadas).
        n_sub : int
            Celdas con n_{ij} < Q_{ij} − 0.01 (sub-asignadas).
        n_exacto : int
            Celdas con |n_{ij} − Q_{ij}| ≤ 0.01.
        share_sobre : float
            n_sobre / n_celdas.

    Notes
    -----
    El umbral 0.01 para clasificar celdas en sobre/sub/exacto absorbe errores
    de punto flotante menores a 0.01 escaños; cualquier desviación real causada
    por D'Hondt es ≥ 0.1 escaños.

    Examples
    --------
    >>> summary = fs.fair_share_summary(N, Q, label="legal_2026")
    >>> summary["l1_norm"]   # fracción normalizada de distorsión electoral
    0.12
    """
    n, q = _align(integer_allocation.astype(float), fair_shares.astype(float))
    diff      = n.to_numpy() - q.to_numpy()
    abs_diff  = np.abs(diff)

    total_seats = float(fair_shares.to_numpy().sum())
    n_cells     = diff.size

    l1   = float(abs_diff.sum())
    l2   = float(np.sqrt((diff ** 2).sum()))
    rmse = float(np.sqrt((diff ** 2).mean()))

    mcd = max_cell_deviation(integer_allocation, fair_shares)

    eps = 0.01
    n_sobre  = int((diff >  eps).sum())
    n_sub    = int((diff < -eps).sum())
    n_exacto = int((abs_diff <= eps).sum())

    return {
        "plan":              label,
        "l1":                round(l1, 6),
        "l1_norm":           round(l1 / total_seats, 6) if total_seats > 0 else float("nan"),
        "l2":                round(l2, 6),
        "rmse":              round(rmse, 6),
        "max_dev":           round(mcd["max_dev"], 6),
        "max_dev_partido":   mcd["partido"],
        "max_dev_distrito":  mcd["distrito"],
        "max_dev_direction": mcd["direction"],
        "n_celdas":          n_cells,
        "n_sobre":           n_sobre,
        "n_sub":             n_sub,
        "n_exacto":          n_exacto,
        "share_sobre":       round(n_sobre / n_cells, 4) if n_cells > 0 else float("nan"),
    }
