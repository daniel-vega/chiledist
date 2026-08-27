"""
chiledist.validation
======================
Validación del motor D'Hondt del paquete contra el resultado oficial
TRICEL — compara escaños *calculados* (a partir de la votación SERVEL,
vía chiledist.engines.allocation.dhondt.dhondt_binivel) contra escaños
*proclamados* (chiledist.domain.data.tricel.import_proclamations()).

No es una de las 5 capas del paquete (domain/rules/engines/inference/
evaluation): es un consumidor terminal de todas ellas — no aporta datos
ni comportamiento a ninguna, solo compara la salida de un motor (capa 2)
contra una fuente externa de verdad (capa 0). Reutiliza dhondt_binivel()
sin reimplementar ninguna regla de asignación de escaños.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from typing import Optional

import pandas as pd

from ..domain.data.servel import normalize_commune_name
from ..engines.allocation.dhondt import dhondt_binivel

#: Etiqueta humana para el encabezado de ValidationReport.__str__ — no es
#: mecánicamente derivable de election_id ("CL-2025-DIP" -> "Diputados
#: 2025"), así que se mantiene como tabla explícita con fallback al
#: election_id crudo para IDs no registrados.
_ELECTION_LABELS = {
    "CL-2025-DIP": "Diputados 2025",
}


@dataclasses.dataclass
class ValidationReport:
    """Resultado de validar el motor D'Hondt contra proclamaciones TRICEL."""
    election_id: str
    districts_validated: int
    districts_total: int
    seats_validated: int
    seats_total: int
    list_allocations_validated: int
    list_allocations_total: int
    candidate_proclamations: int
    candidate_proclamations_total: int
    ties_requiring_legal_resolution: int
    source_hashes: dict
    status: str  # "EXACT_REPRODUCTION" | "PARTIAL" | "FAIL"
    discrepancies: list
    votes_tricel_fallback_count: int = 0
    # candidatos donde se usó votos SERVEL como fallback
    # (TRICEL no tenía esa columna en MESA A MESA)

    def __str__(self) -> str:
        label = _ELECTION_LABELS.get(self.election_id, self.election_id)
        lines = [
            f"Election: {label}",
            f"Districts validated: {self.districts_validated}/{self.districts_total}",
            f"Seats validated: {self.seats_validated}/{self.seats_total}",
            f"List allocations: {self.list_allocations_validated}/{self.list_allocations_total}",
            f"Candidate proclamations: {self.candidate_proclamations}/{self.candidate_proclamations_total}",
            f"Ties requiring legal resolution: {self.ties_requiring_legal_resolution}",
            "Source hashes:",
            f"  SERVEL: {self.source_hashes.get('SERVEL', '')}",
            f"  TRICEL: {self.source_hashes.get('TRICEL', '')}",
            f"Status: {self.status}",
        ]
        return "\n".join(lines)


def _top_k_candidate_ids(district_party_df: pd.DataFrame, k: int) -> list:
    """Los k candidatos más votados de un (distrito, partido) — desempate
    determinista por candidate_id ascendente."""
    if k <= 0:
        return []
    ranked = district_party_df.sort_values(
        ["votes", "candidate_id"], ascending=[False, True]
    )
    return ranked.head(k)["candidate_id"].tolist()


def _has_boundary_tie(district_party_df: pd.DataFrame, k: int) -> bool:
    """True si el último escaño asignado (posición k) empata en votos con
    el primer candidato no electo (posición k+1) — empate real que la ley
    chilena resuelve por sorteo (Ley 18.700), no algorítmicamente."""
    votes_sorted = sorted(district_party_df["votes"].tolist(), reverse=True)
    if k <= 0 or k >= len(votes_sorted):
        return False
    return votes_sorted[k - 1] == votes_sorted[k]


def _apply_votes_source(
    candidates_servel: pd.DataFrame, votes_tricel: Optional[pd.DataFrame]
) -> "tuple[pd.DataFrame, int]":
    """
    Reemplaza la columna `votes` de candidates_servel por los totales de
    votes_tricel (import_votes(), hoja MESA A MESA) cuando se provee.

    Las 59 discrepancias candidato-a-candidato observadas al validar con
    votos SERVEL preliminares vienen de comparar fuentes distintas: el
    D'Hondt se calculaba con votación *preliminar* (noche de elección)
    mientras TRICEL proclamó con el escrutinio *final*. votes_tricel trae
    esos mismos totales finales por (distrito, candidato) — usarlos aquí
    hace que el cálculo y la proclamación vengan de la misma fuente.

    votes_tricel no trae candidate_id/party_id/list_id (solo
    candidate_name + totales), así que el cruce con candidates_servel se
    hace por (district_id, candidate_name normalizado) — ambas fuentes
    usan el nombre en mayúsculas sin tilde de SERVEL/TRICEL, normalizado
    aquí con normalize_commune_name() por consistencia con el cruce que
    ya hace domain.data.tricel.import_proclamations().

    Fallback: MESA A MESA no siempre trae una columna por cada candidato
    del roster completo (~24% de los candidatos reales quedan sin match
    — ver "Deuda técnica"). Antes, un candidato sin match quedaba en
    votes=0, lo que producía empates espurios (0 == 0) entre candidatos
    sin match del mismo partido y arruinaba el ranking intra-partido —
    ahora conserva sus votos SERVEL originales en vez de perderlos.

    Returns
    -------
    (df, n_fallback) — df con `votes` reemplazado donde hubo match
    TRICEL (sin cambios donde no lo hubo), y n_fallback = cuántos
    candidatos usaron el fallback a votos SERVEL.
    """
    if votes_tricel is None:
        return candidates_servel.copy(), 0

    servel = candidates_servel.copy()
    servel["_name_norm"] = servel["candidate_name"].apply(normalize_commune_name)

    votes = votes_tricel[["district_id", "candidate_name", "votes_final"]].copy()
    votes["_name_norm"] = votes["candidate_name"].apply(normalize_commune_name)
    votes = votes.drop(columns=["candidate_name"])

    merged = servel.merge(
        votes,
        on=["district_id", "_name_norm"],
        how="left",   # conserva todos los candidatos SERVEL
    )
    # Para candidatos sin match TRICEL, usar votos SERVEL
    merged["votes"] = merged["votes_final"].where(
        merged["votes_final"].notna(),
        other=merged["votes"],  # fallback a votos SERVEL
    ).astype(int)
    # Registrar cuántos usaron fallback
    n_fallback = int(merged["votes_final"].isna().sum())

    return merged.drop(columns=["_name_norm", "votes_final"]), n_fallback


def validate_election(
    candidates_servel: pd.DataFrame,
    proclamations_tricel: pd.DataFrame,
    assignment: dict,
    magnitudes: dict,
    pacto_map: dict,
    election_id: str = "CL-2025-DIP",
    source_hashes: Optional[dict] = None,
    votes_tricel: Optional[pd.DataFrame] = None,
) -> ValidationReport:
    """
    Valida el motor D'Hondt del paquete reproduciendo la elección oficial.

    Pipeline
    --------
    1. Para cada distrito con datos SERVEL, corre dhondt_binivel() sobre
       los votos agregados por partido para obtener escaños calculados
       por partido, y determina los candidatos ganadores dentro de cada
       partido por mayor votación individual (regla real, Ley 18.700 —
       no es un segundo D'Hondt intra-partido).
    2. Compara escaños calculados vs proclamados TRICEL agregados por
       (district_id, list_id).
    3. Compara el conjunto de candidate_id calculados vs proclamados.
    4. Reporta discrepancias candidato a candidato y de asignación por
       lista.
    5. Detecta empates: mismos votos entre el último candidato electo de
       un partido y el primer no electo (frontera de corte).

    Parameters
    ----------
    candidates_servel : pd.DataFrame
        Schema de chiledist.domain.data.servel.CandidateRecord (o
        compatible): requiere al menos district_id, party_id, list_id,
        candidate_id, candidate_name, votes.
    proclamations_tricel : pd.DataFrame
        Schema de chiledist.domain.data.tricel.ProclamationRecord:
        district_id, candidate_id, candidate_name, party_id, list_id,
        votes_final, officially_elected.
    assignment : dict
        {CUT: district_id} — define el universo completo de distritos
        (districts_total = distritos únicos), independiente de cuántos
        tengan datos SERVEL/TRICEL disponibles en esta corrida.
    magnitudes : dict
        {district_id: escaños legales} — ej. MAGNITUDES_LEGALES_LEY20840.
        seats_total = suma de todos los valores.
    pacto_map : dict
        {partido: pacto} — pasado directo a dhondt_binivel().
    election_id : str
    source_hashes : dict, opcional
        {"SERVEL": sha256, "TRICEL": sha256} — hashes de procedencia de
        las fuentes usadas (ver provenance de import_candidates()/
        import_proclamations()). No pedido explícitamente en el encargo
        original; se agregó porque ValidationReport.source_hashes no es
        derivable solo de los DataFrames de entrada (ver "Deuda técnica"
        en el reporte de esta etapa). Default: {}.
    votes_tricel : pd.DataFrame, opcional
        Schema de chiledist.domain.data.tricel.import_votes(): district_id,
        candidate_name, votes_final (+ votes_null/votes_blank/total_votes,
        no usados aquí). Si se provee, el D'Hondt se calcula con estos
        votos (escrutinio final TRICEL, mesa a mesa) en vez de los de
        candidates_servel (votación preliminar SERVEL) — evita comparar
        un cálculo hecho con una fuente contra una proclamación hecha con
        otra. El cruce con candidates_servel es por (district_id,
        candidate_name normalizado); ver _apply_votes_source(). Default:
        None (comportamiento anterior, usa candidates_servel.votes).

    Returns
    -------
    ValidationReport
    """
    districts_total = len(set(assignment.values()))
    seats_total = sum(magnitudes.values())

    servel, votes_tricel_fallback_count = _apply_votes_source(candidates_servel, votes_tricel)
    if "district_id" not in servel.columns:
        raise ValueError("candidates_servel requiere la columna district_id")

    covered_districts = sorted(
        d for d in servel["district_id"].unique() if d in magnitudes
    )

    districts_validated = 0
    seats_validated = 0
    list_allocations_validated = 0
    list_allocations_total = 0
    candidate_proclamations = 0
    ties_requiring_legal_resolution = 0
    discrepancies = []

    proclaimed_ids_total = set(
        zip(proclamations_tricel["district_id"], proclamations_tricel["candidate_id"])
    )

    for district_id in covered_districts:
        district_id = int(district_id)
        district_df = servel[servel["district_id"] == district_id]
        votos_por_partido = district_df.groupby("party_id")["votes"].sum().to_dict()
        seats = magnitudes[district_id]

        calculated_by_party = dhondt_binivel(votos_por_partido, pacto_map, seats)

        party_to_list = (
            district_df.drop_duplicates("party_id")
            .set_index("party_id")["list_id"].to_dict()
        )

        calculated_ids = set()
        calculated_seats_by_list = defaultdict(int)
        proclaimed_seats_by_party = (
            proclamations_tricel[proclamations_tricel["district_id"] == district_id]
            .groupby("party_id").size().to_dict()
        )

        district_ok = True

        for party, k in calculated_by_party.items():
            party_df = district_df[district_df["party_id"] == party]
            winners = _top_k_candidate_ids(party_df, k)
            calculated_ids.update(winners)
            calculated_seats_by_list[party_to_list.get(party, party)] += k
            seats_validated += min(k, proclaimed_seats_by_party.get(party, 0))
            if _has_boundary_tie(party_df, k):
                ties_requiring_legal_resolution += 1
                district_ok = False

        proclaimed_district = proclamations_tricel[
            proclamations_tricel["district_id"] == district_id
        ]
        proclaimed_ids = set(proclaimed_district["candidate_id"])
        proclaimed_seats_by_list = proclaimed_district.groupby("list_id").size().to_dict()

        all_lists = set(calculated_seats_by_list) | set(proclaimed_seats_by_list)
        for list_id in all_lists:
            list_allocations_total += 1
            calc_n = int(calculated_seats_by_list.get(list_id, 0))
            proc_n = int(proclaimed_seats_by_list.get(list_id, 0))
            if calc_n == proc_n:
                list_allocations_validated += 1
            else:
                district_ok = False
                discrepancies.append({
                    "type": "list_allocation_mismatch",
                    "district_id": district_id,
                    "list_id": list_id,
                    "calculated_seats": calc_n,
                    "proclaimed_seats": proc_n,
                })

        matched_ids = calculated_ids & proclaimed_ids
        candidate_proclamations += len(matched_ids)

        id_to_name = dict(zip(
            proclaimed_district["candidate_id"], proclaimed_district["candidate_name"]
        ))
        id_to_name.update(dict(zip(district_df["candidate_id"], district_df["candidate_name"])))

        for cid in sorted(proclaimed_ids - calculated_ids):
            cid = int(cid)
            district_ok = False
            discrepancies.append({
                "type": "candidate_mismatch",
                "district_id": district_id,
                "candidate_id": cid,
                "candidate_name": id_to_name.get(cid, ""),
                "expected": "elected (TRICEL)",
                "calculated": "not elected",
            })
        for cid in sorted(calculated_ids - proclaimed_ids):
            cid = int(cid)
            district_ok = False
            discrepancies.append({
                "type": "candidate_mismatch",
                "district_id": district_id,
                "candidate_id": cid,
                "candidate_name": id_to_name.get(cid, ""),
                "expected": "not elected",
                "calculated": "elected (D'Hondt)",
            })

        if district_ok:
            districts_validated += 1

    candidate_proclamations_total = len(proclaimed_ids_total)

    nothing_validated = (
        list_allocations_validated == 0
        and candidate_proclamations == 0
        and seats_validated == 0
    )
    if nothing_validated and (list_allocations_total or candidate_proclamations_total):
        status = "FAIL"
    elif (
        districts_validated == districts_total
        and not discrepancies
        and candidate_proclamations == candidate_proclamations_total
    ):
        status = "EXACT_REPRODUCTION"
    else:
        status = "PARTIAL"

    return ValidationReport(
        election_id=election_id,
        districts_validated=districts_validated,
        districts_total=districts_total,
        seats_validated=seats_validated,
        seats_total=seats_total,
        list_allocations_validated=list_allocations_validated,
        list_allocations_total=list_allocations_total,
        candidate_proclamations=candidate_proclamations,
        candidate_proclamations_total=candidate_proclamations_total,
        ties_requiring_legal_resolution=ties_requiring_legal_resolution,
        source_hashes=dict(source_hashes) if source_hashes else {},
        status=status,
        discrepancies=discrepancies,
        votes_tricel_fallback_count=votes_tricel_fallback_count,
    )


__all__ = ["ValidationReport", "validate_election"]
