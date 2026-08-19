"""
scripts/validar_dhondt.py
===========================
Validación H4: compara los escaños D'Hondt binivel calculados por
chiledist contra el resultado oficial SERVEL 2025, usando la asignación
distrital vigente (Ley 20.840).

Corre sin argumentos, asumiendo datos/ desde la raíz del proyecto:
    datos/servel_2025_por_cut.csv      votos por CUT y partido
    datos/pacto_map_2025.json          partido -> pacto
    datos/asignacion_vigente.json      CUT -> n_distrito (1-28)
    datos/escanos_oficiales_2025.csv   distrito,pacto,escanos oficiales
                                        (distrito = "DISTRITO 1", ..., "DISTRITO 28")

Dos modos:
    --modo por_cut (default): agrega votos por CUT+partido y deriva el
        pacto de cada partido vía pacto_map_2025.json. Trata a los
        independientes ("IND"/"INDEPENDIENTES") como una única bolsa
        agregada -- no refleja que cada independiente compite por su
        cuenta en el sistema real.
    --modo candidatos: agrega votos por candidato real desde
        datos/servel_2025_candidatos.csv (CUT, cod_candidato,
        nombre_candidato, partido, pacto, votos), usando el pacto que
        ya trae cada candidato desde el propio dato SERVEL -- no
        necesita pacto_map_2025.json.

Uso:
    python scripts/validar_dhondt.py
    python scripts/validar_dhondt.py --modo candidatos --votos-path /ruta/a/servel_2025_candidatos.csv
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

import chiledist as cd

DATOS_DIR = os.path.join(ROOT, "datos")

# La salida oficial de SERVEL etiqueta al pacto ganador de candidatos
# independientes como "CANDIDATURA INDEPENDIENTE" (ver DISTRITO 28), mientras
# que pacto_map_2025.json mapea IND/Independientes a "Independientes Fuera de
# Pacto" -- mismo concepto, nombre distinto. Sin este alias, la comparación
# reportaría un mismatch de etiqueta, no un mismatch real de escaños.
ALIAS_PACTO = {
    "candidatura independiente": "independientes fuera de pacto",
}


def _norm_pacto(nombre: str) -> str:
    n = cd.normalize_party_name(nombre)
    return ALIAS_PACTO.get(n, n)


def cargar_datos(votos_path: str):
    with open(os.path.join(DATOS_DIR, "asignacion_vigente.json"), encoding="utf-8") as f:
        assignment_raw = json.load(f)
    assignment = {cd.normalize_cut(k): int(v) for k, v in assignment_raw.items()}

    votes_df = pd.read_csv(votos_path)
    votes_df["CUT"] = votes_df["CUT"].map(cd.normalize_cut)

    with open(os.path.join(DATOS_DIR, "pacto_map_2025.json"), encoding="utf-8") as f:
        pacto_map = json.load(f)

    oficial = pd.read_csv(os.path.join(DATOS_DIR, "escanos_oficiales_2025.csv"))

    return assignment, votes_df, pacto_map, oficial


def correr_dhondt_chiledist(assignment, votes_df, pacto_map):
    # Mismo patrón que scripts/electoral_analysis.py (bloque B4): normalizar
    # ambos lados con normalize_party_name y usar el propio nombre de partido
    # como pacto de respaldo cuando no está en pacto_map (ej. partidos chicos
    # sin coalición registrada en el mapa).
    pacto_map_norm = {cd.normalize_party_name(k): v for k, v in pacto_map.items()}

    votos_dist = cd.aggregate_votes(votes_df, assignment, unit_col="CUT")
    votos_dist["pacto"] = (
        votos_dist["partido"].map(cd.normalize_party_name).map(pacto_map_norm)
        .fillna(votos_dist["partido"])
    )

    magnitudes = pd.Series({
        n: int(m) for n, m in cd.MAGNITUDES_LEGALES_LEY20840.items()
        if n in set(assignment.values())
    })

    resultado = cd.run_electoral_plan_binivel(votos_dist, magnitudes)
    return resultado, magnitudes


def correr_dhondt_candidatos(assignment: dict, votes_df: pd.DataFrame):
    """
    Modo --modo candidatos: votes_df viene de servel_2025_candidatos.csv
    (CUT, cod_candidato, nombre_candidato, partido, pacto, votos) -- sin
    columna "distrito", hay que derivarla de CUT vía assignment, igual
    que en modo por_cut. A diferencia de por_cut, el pacto ya viene
    correcto por candidato desde el propio dato SERVEL (no requiere
    pacto_map_2025.json), así que cada independiente conserva su propio
    pacto real en vez de caer en la bolsa agregada "IND".
    """
    votes_df = votes_df.copy()
    votes_df["district"] = votes_df["CUT"].map(assignment)

    sin_distrito = votes_df[votes_df["district"].isna()]
    if not sin_distrito.empty:
        print(
            f"  ADVERTENCIA: {len(sin_distrito)} filas con CUT sin distrito "
            f"asignado en asignacion_vigente.json -- excluidas."
        )
    votes_df = votes_df.dropna(subset=["district"]).copy()
    votes_df["district"] = votes_df["district"].astype(int)

    # PASO 2: agregar votos por (distrito, partido, pacto) -- suma los CUT
    # parciales de cada candidato y los candidatos del mismo partido en el
    # mismo distrito.
    votos_dist = (
        votes_df
        .groupby(["district", "partido", "pacto"], as_index=False)["votos"]
        .sum()
    )

    magnitudes = pd.Series({
        n: int(m) for n, m in cd.MAGNITUDES_LEGALES_LEY20840.items()
        if n in set(assignment.values())
    })

    resultado = cd.run_electoral_plan_binivel(votos_dist, magnitudes, partido_col="partido")
    return resultado, magnitudes


def comparar(res: pd.DataFrame, oficial: pd.DataFrame) -> pd.DataFrame:
    chiledist_pacto = (
        res.groupby(["district", "pacto"], as_index=False)["escanos"].sum()
    )
    # Solo pactos con escaños>0 son comparables: el oficial no lista pactos
    # que no ganaron ningún escaño, así que incluir los ceros de chiledist
    # produciría cientos de "mismatches" espurios (pacto ausente en oficial
    # porque no ganó nada, no porque chiledist se equivocara).
    chiledist_pacto = chiledist_pacto[chiledist_pacto["escanos"] > 0].copy()
    chiledist_pacto["distrito"] = chiledist_pacto["district"].map(lambda n: f"DISTRITO {n}")
    chiledist_pacto["pacto_norm"] = chiledist_pacto["pacto"].map(_norm_pacto)

    oficial = oficial.copy()
    oficial["pacto_norm"] = oficial["pacto"].map(_norm_pacto)

    merged = oficial.merge(
        chiledist_pacto, on=["distrito", "pacto_norm"], how="outer",
        suffixes=("_oficial", "_chiledist"),
    )
    merged["escanos_oficial"] = merged["escanos_oficial"].fillna(0).astype(int)
    merged["escanos_chiledist"] = merged["escanos_chiledist"].fillna(0).astype(int)
    merged["pacto"] = merged["pacto_oficial"].fillna(merged["pacto_chiledist"])
    merged["diff"] = merged["escanos_chiledist"] - merged["escanos_oficial"]

    tabla = merged[["distrito", "pacto", "escanos_oficial", "escanos_chiledist", "diff"]].copy()
    tabla["_n_distrito"] = tabla["distrito"].str.replace("DISTRITO ", "", regex=False).astype(int)
    tabla = (
        tabla
        .sort_values(["_n_distrito", "escanos_oficial"], ascending=[True, False])
        .drop(columns="_n_distrito")
        .reset_index(drop=True)
    )
    return tabla


def validar_invariantes(res: pd.DataFrame, magnitudes: pd.Series) -> list[str]:
    problemas = []

    escanos_por_distrito = res.groupby("district")["escanos"].sum()
    for n_distrito, magnitud in magnitudes.items():
        calculado = int(escanos_por_distrito.get(n_distrito, 0))
        if calculado != magnitud:
            problemas.append(
                f"DISTRITO {n_distrito}: suma escaños chiledist = {calculado}, "
                f"magnitud legal (MAGNITUDES_LEGALES_LEY20840) = {magnitud}"
            )

    total = int(res["escanos"].sum())
    if total != 155:
        problemas.append(f"Suma escaños total chiledist = {total}, esperado 155")

    votos_pacto = res.groupby(["district", "pacto"])["votos"].sum()
    escanos_pacto = res.groupby(["district", "pacto"])["escanos_pacto"].first()
    sin_votos_con_escanos = [
        (d, p, int(escanos_pacto[(d, p)]))
        for (d, p), v in votos_pacto.items()
        if v <= 0 and escanos_pacto[(d, p)] > 0
    ]
    if sin_votos_con_escanos:
        problemas.append(
            f"{len(sin_votos_con_escanos)} pactos con 0 votos y escaños>0: "
            f"{sin_votos_con_escanos}"
        )

    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validación H4: D'Hondt binivel chiledist vs SERVEL oficial 2025."
    )
    parser.add_argument(
        "--modo", choices=["por_cut", "candidatos"], default="por_cut",
        help="'por_cut' (default): agrega por CUT+partido, pacto vía "
             "pacto_map_2025.json. 'candidatos': agrega por candidato real "
             "desde servel_2025_candidatos.csv, con el pacto que ya trae "
             "cada candidato desde SERVEL.",
    )
    parser.add_argument(
        "--votos-path", default=None,
        help="Ruta al CSV de votos. Default: datos/servel_2025_por_cut.csv "
             "(modo por_cut) o datos/servel_2025_candidatos.csv (modo candidatos).",
    )
    args = parser.parse_args()

    votos_path = args.votos_path or os.path.join(
        DATOS_DIR,
        "servel_2025_por_cut.csv" if args.modo == "por_cut" else "servel_2025_candidatos.csv",
    )

    print("=" * 70)
    print("  Validación H4: D'Hondt binivel chiledist vs SERVEL oficial 2025")
    print(f"  Modo: {args.modo} -- votos: {votos_path}")
    print("=" * 70)

    assignment, votes_df, pacto_map, oficial = cargar_datos(votos_path)
    print(f"  CUTs asignados: {len(assignment)} -- "
          f"distritos: {len(set(assignment.values()))}")

    if args.modo == "por_cut":
        res, magnitudes = correr_dhondt_chiledist(assignment, votes_df, pacto_map)
    else:
        res, magnitudes = correr_dhondt_candidatos(assignment, votes_df)

    tabla = comparar(res, oficial)

    print(f"\n  Tabla completa ({len(tabla)} filas distrito x pacto):")
    print(tabla.to_string(index=False))

    n_total = len(tabla)
    n_coincidencias = int((tabla["diff"] == 0).sum())
    distritos_con_diff = sorted(
        tabla.loc[tabla["diff"] != 0, "distrito"].unique(),
        key=lambda s: int(s.replace("DISTRITO ", "")),
    )

    print(f"\n  Resumen: {n_coincidencias}/{n_total} filas (distrito, pacto) coinciden.")
    print(f"  Distritos con alguna diferencia: {len(distritos_con_diff)} -> {distritos_con_diff}")

    total_oficial = int(oficial["escanos"].sum())
    total_chiledist = int(res["escanos"].sum())
    print(f"  Total escaños: chiledist={total_chiledist} vs oficial={total_oficial}")

    problemas = validar_invariantes(res, magnitudes)
    print("\n  Invariantes matemáticos:")
    if problemas:
        for p in problemas:
            print(f"    ✗ {p}")
    else:
        print("    ✓ Σ escaños por distrito == magnitud legal, Σ total == 155, "
              "ningún pacto con 0 votos recibe escaños.")

    ok = bool((tabla["diff"] == 0).all()) and not problemas

    print("\n" + "=" * 70)
    if ok:
        print("  VEREDICTO: PASS")
    else:
        print("  VEREDICTO: FAIL")
        if (tabla["diff"] != 0).any():
            print(f"    - {n_total - n_coincidencias} filas (distrito, pacto) no coinciden "
                  f"(ver tabla arriba).")
        if problemas:
            print(f"    - {len(problemas)} invariantes matemáticos violados (ver detalle arriba).")
    print("=" * 70)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
