"""
scripts/validar_tricel.py
============================
Validación candidato-a-candidato: compara los escaños D'Hondt binivel
calculados por chiledist contra las proclamaciones oficiales TRICEL 2025
(escrutinio final), a diferencia de scripts/validar_dhondt.py que valida
solo a nivel de conteo de escaños por (distrito, pacto) contra
escanos_oficiales_2025.csv (que a su vez viene de SERVEL, no de TRICEL).

Script manual — no forma parte de la suite de tests (requiere los Excel
crudos DISTRITO-XX.xlsx de TRICEL, que no se distribuyen en el repo, ver
.env.example).

Uso:
    python scripts/validar_tricel.py \\
        --data-dir /ruta/a/datos_fuentes \\
        --servel-candidates datos/servel_2025_candidatos.csv \\
        --pacto-map datos/pacto_map_2025.json \\
        --assignment datos/asignacion_vigente.json

--data-dir se usa para dos cosas: (1) exportado como CHILEDIST_DATA_DIR,
de donde chiledist.domain.data.tricel.import_proclamations() resuelve
TRICEL_2025/ y SERVEL_2025/ (para el cruce interno num_tricel ->
candidate_id); (2) pasado como base_dir a esa misma función para
resolver comuna -> CUT vía cd.load_layer("comunal", ...) (requiere
SHP_APC2023_R* dentro de data-dir).

candidates_servel se construye aparte, desde --servel-candidates (el CSV
ya procesado, no el Excel crudo) + --assignment, con el mismo patrón que
scripts/validar_dhondt.py --modo candidatos: district_id se deriva de
CUT vía assignment, y list_id/party_id ya vienen con cada candidato.

Estado (agosto 2026): 25/28 distritos (default --votes-source
servel_final, ver VALIDATION_REPORT.md). Los 3 distritos restantes
(D3, D5, D19) NO son un problema de cobertura de datos — la causa raíz
verificada es que chiledist.engines.allocation.dhondt.dhondt_binivel()
no aplica un tope de candidatos disponibles por partido en el reparto
intra-pacto (Nivel 2): un partido con un solo candidato inscrito puede
"ganar" más de un escaño en el cálculo aproximado, cuando en la
realidad ese escaño pasa al siguiente partido con un candidato
disponible. Ver VALIDATION_REPORT.md para la evidencia (7/7 pactos
reproducidos exactamente con un D'Hondt con tope de candidatos) — el
fix no está implementado aquí, es un cambio a la función D'Hondt
central usada en todo el pipeline, no específico de este script.
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

import chiledist as cd


def _cargar_candidates_servel(servel_candidates_path: str, assignment: dict) -> pd.DataFrame:
    df = pd.read_csv(servel_candidates_path)
    df["CUT"] = df["CUT"].map(cd.normalize_cut)
    df["district_id"] = df["CUT"].map(assignment)

    sin_distrito = df[df["district_id"].isna()]
    if not sin_distrito.empty:
        print(f"  ADVERTENCIA: {len(sin_distrito)} filas con CUT sin distrito "
              f"asignado -- excluidas.")
    df = df.dropna(subset=["district_id"]).copy()
    df["district_id"] = df["district_id"].astype(int)

    candidatos = pd.DataFrame({
        "district_id":    df["district_id"],
        "candidate_id":   df["cod_candidato"].astype(int),
        "candidate_name": df["nombre_candidato"].astype(str),
        "party_id":       df["partido"].map(cd.normalize_party_name),
        "list_id":        df["pacto"].astype(str),
        "votes":          pd.to_numeric(df["votos"], errors="coerce").fillna(0).astype(int),
    })

    # Agregar votos por candidato (una fila por candidato,
    # no una por CUT) -- servel_2025_candidatos.csv tiene
    # una fila por (candidate_id, CUT)
    candidatos = (
        candidatos.groupby(
            ["district_id", "candidate_id", "candidate_name",
             "party_id", "list_id"],
            as_index=False,
        )["votes"]
        .sum()
    )
    return candidatos


def _print_district_summary(discrepancies: list) -> None:
    """
    Resumen agrupado por distrito de discrepancias no validadas: total,
    tipos presentes, y candidatos en cada dirección del desacuerdo
    (calculados-pero-no-proclamados / proclamados-pero-no-calculados).
    """
    by_district = defaultdict(list)
    for d in discrepancies:
        by_district[d["district_id"]].append(d)

    print(f"Distritos no validados ({len(by_district)}):")
    for district_id in sorted(by_district):
        items = by_district[district_id]
        types_present = sorted({item["type"] for item in items})
        print(f"  D{district_id}: {len(items)} discrepancias ({' + '.join(types_present)})")

        falsos_positivos = [
            it for it in items
            if it["type"] == "candidate_mismatch" and it["calculated"] == "elected (D'Hondt)"
        ]
        falsos_negativos = [
            it for it in items
            if it["type"] == "candidate_mismatch" and it["expected"] == "elected (TRICEL)"
        ]
        if falsos_positivos:
            nombres = ", ".join(it["candidate_name"] for it in falsos_positivos)
            print(f"    Calculados electos pero no proclamados: {nombres}")
        if falsos_negativos:
            nombres = ", ".join(it["candidate_name"] for it in falsos_negativos)
            print(f"    Proclamados pero no calculados: {nombres}")


def _combined_hash(sha256_by_district: dict) -> str:
    """
    ProvenanceRecord/sha256_by_district traen un hash *por archivo* (uno
    por distrito) — ValidationReport.source_hashes espera un único hash
    por fuente. Se combina determinísticamente hasheando la lista
    ordenada de hashes por distrito, para que el resultado no dependa
    del orden de lectura.
    """
    if not sha256_by_district:
        return ""
    joined = "|".join(sha256_by_district[k] for k in sorted(sha256_by_district))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validación candidato-a-candidato: D'Hondt binivel "
                     "chiledist vs proclamaciones oficiales TRICEL 2025."
    )
    parser.add_argument("--data-dir", required=True,
                         help="Directorio raíz con SERVEL_2025/, TRICEL_2025/ "
                              "y SHP_APC2023_R* (ver .env.example).")
    parser.add_argument(
        "--base-dir",
        default="./SHP_APC2023",
        help="Carpeta SHP_APC2023 con shapefiles APC "
             "(default: ./SHP_APC2023)"
    )
    parser.add_argument("--servel-candidates", required=True,
                         help="CSV de candidatos SERVEL (CUT, cod_candidato, "
                              "nombre_candidato, partido, pacto, votos).")
    parser.add_argument("--pacto-map", required=True,
                         help="JSON {partido: pacto}.")
    parser.add_argument("--assignment", required=True,
                         help="JSON {CUT: n_distrito}.")
    parser.add_argument("--verbose", action="store_true",
                         help="Mostrar el detalle completo de cada discrepancia "
                              "(por default solo se muestra el resumen agrupado "
                              "por distrito).")
    parser.add_argument(
        "--votes-source", choices=["tricel", "servel_final"], default="servel_final",
        help="Fuente de votos para el parámetro votes_tricel de validate_election(). "
             "'servel_final' (default, agosto 2026): "
             "cd.domain.data.servel.import_final_scrutiny(), escrutinio final "
             "SERVEL republicado (ver VALIDATION_REPORT.md) — coincide ~100%% "
             "con los totales certificados por TRICEL en los 28 distritos "
             "(incluidos los 4 antes diagnosticados con baja cobertura) y no "
             "tiene el bug de fila-de-totales-duplicada de Distrito 8 que sí "
             "afecta a 'tricel'. Resultado empírico: 25/28 vs 24/28 con "
             "'tricel'. 'tricel': cd.import_votes(), mesa a mesa TRICEL — "
             "mantenido para comparación/depuración.",
    )
    args = parser.parse_args()

    os.environ["CHILEDIST_DATA_DIR"] = args.data_dir

    with open(args.assignment, encoding="utf-8") as f:
        assignment_raw = json.load(f)
    assignment = {cd.normalize_cut(k): int(v) for k, v in assignment_raw.items()}

    with open(args.pacto_map, encoding="utf-8") as f:
        pacto_map = json.load(f)

    print("=" * 70)
    print("  Validación TRICEL: D'Hondt binivel chiledist vs proclamaciones oficiales")
    print("=" * 70)

    print(f"  Cargando candidatos SERVEL desde {args.servel_candidates} ...")
    candidates_servel = _cargar_candidates_servel(args.servel_candidates, assignment)
    print(f"  {len(candidates_servel)} candidatos, "
          f"{candidates_servel['district_id'].nunique()} distritos.")

    print(f"  Importando proclamaciones TRICEL desde {args.data_dir}/TRICEL_2025 ...")
    proclamations, proc_provenance = cd.import_proclamations(
        source_dir=args.data_dir,
        base_dir=args.base_dir,
    )
    print(f"  {proc_provenance['districts_loaded']} distritos leídos, "
          f"{proc_provenance['candidates_matched']} candidatos cruzados con SERVEL, "
          f"{len(proc_provenance['candidates_unmatched'])} sin cruce.")
    if proc_provenance["candidates_unmatched"]:
        print(f"    Sin cruce: {proc_provenance['candidates_unmatched']}")

    if args.votes_source == "tricel":
        print(f"  Importando votación mesa a mesa TRICEL desde {args.data_dir}/TRICEL_2025 ...")
        votes_tricel, _votes_provenance = cd.import_votes(
            source_dir=args.data_dir,
        )
    else:
        from chiledist.domain.data.servel import import_final_scrutiny
        print(f"  Importando escrutinio final SERVEL (v2) desde {args.data_dir}/SERVEL_2025 ...")
        votes_tricel, _votes_provenance = import_final_scrutiny(
            source_path=f"{args.data_dir}/SERVEL_2025",
        )
        print(f"    workbook: {_votes_provenance['workbook']}")
    print(f"  {len(votes_tricel)} registros (distrito, candidato) de votación TRICEL.")

    magnitudes = {
        n: int(m) for n, m in cd.MAGNITUDES_LEGALES_LEY20840.items()
        if n in set(assignment.values())
    }

    with open(args.servel_candidates, "rb") as f:
        servel_hash = hashlib.sha256(f.read()).hexdigest()

    report = cd.validate_election(
        candidates_servel=candidates_servel,
        proclamations_tricel=proclamations,
        votes_tricel=votes_tricel,
        assignment=assignment,
        magnitudes=magnitudes,
        pacto_map=pacto_map,
        source_hashes={
            "SERVEL": servel_hash,
            "TRICEL": _combined_hash(proc_provenance["sha256_by_district"]),
        },
    )

    print()
    print(str(report))
    print()

    if report.status != "EXACT_REPRODUCTION" and report.discrepancies:
        _print_district_summary(report.discrepancies)
        print()

    if args.verbose and report.discrepancies:
        print(f"  {len(report.discrepancies)} discrepancia(s) (detalle completo):")
        for d in report.discrepancies[:50]:
            print(f"    {d}")
        if len(report.discrepancies) > 50:
            print(f"    ... y {len(report.discrepancies) - 50} más.")
        print()

    if report.status != "EXACT_REPRODUCTION":
        print("Para investigar discrepancias: usar --verbose para ver detalle completo")

    return 0 if report.status == "EXACT_REPRODUCTION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
