"""
tests/test_servel_candidates.py
==================================
Tests para la refactorización de la capa de datos electorales SERVEL
(chiledist/domain/data/servel/) — Bloques 1, 2 y 3.

No requiere Excel reales de SERVEL ni shapefiles APC2023: los tests
construyen archivos .xlsx sintéticos en tmp_path con la misma forma
que datos/scripts_extra/escanos.py documenta para los Excel crudos
(región, distrito, comuna, pacto, subpacto, partido, cod_candidato,
nombre_candidato, votos_preliminares, electo_nominado — ver README.md
§ Datos externos).
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from chiledist.domain.data.servel import (
    COMMUNE_NAME_ALIASES,
    CandidateRecord,
    filter_administrative_rows,
    import_candidates,
    import_results,
    normalize_commune_name,
)
from chiledist.domain.data.servel.provenance import (
    PARSER_VERSION,
    ProvenanceRecord,
    compute_provenance,
)


# ──────────────────────────────────────────────────────────────────────────────
# BLOQUE 1 — normalize_commune_name
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizeCommuneName:

    def test_tildes_y_mayusculas(self):
        assert normalize_commune_name("Ñuñoa") == "NUNOA"
        assert normalize_commune_name("Peñalolén") == "PENALOLEN"

    def test_ya_normalizado_es_idempotente(self):
        assert normalize_commune_name("MARCHIHUE") == "MARCHIHUE"

    def test_strip_espacios(self):
        assert normalize_commune_name("  Santiago  ") == "SANTIAGO"

    def test_no_string_retorna_vacio(self):
        assert normalize_commune_name(None) == ""
        assert normalize_commune_name(float("nan")) == ""


# ──────────────────────────────────────────────────────────────────────────────
# BLOQUE 1 — COMMUNE_NAME_ALIASES
# ──────────────────────────────────────────────────────────────────────────────

class TestCommuneNameAliases:

    def test_tiene_las_5_entradas_documentadas(self):
        assert COMMUNE_NAME_ALIASES == {
            "MARCHIGUE":                   "MARCHIHUE",
            "TREHUACO":                    "TREGUACO",
            "PAIHUANO":                    "PAIGUANO",
            "LLAY-LLAY":                   "LLAILLAY",
            "CABO DE HORNOS(EX-NAVARINO)": "CABO DE HORNOS",
        }

    def test_valores_ya_estan_normalizados(self):
        """Los valores del alias deben calzar con normalize_commune_name()
        aplicado a sí mismos (mayúsculas, sin tildes)."""
        for canonical in COMMUNE_NAME_ALIASES.values():
            assert normalize_commune_name(canonical) == canonical


# ──────────────────────────────────────────────────────────────────────────────
# BLOQUE 1 — filter_administrative_rows
# ──────────────────────────────────────────────────────────────────────────────

class TestFilterAdministrativeRows:

    def _raw_df(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"cod_candidato": 1001, "partido": "PS", "votos_preliminares": 100},
            {"cod_candidato": 1002, "partido": "RN", "votos_preliminares": 200},
            # filas administrativas: sin cod_candidato
            {"cod_candidato": None, "partido": None, "votos_preliminares": 50},
            {"cod_candidato": float("nan"), "partido": None, "votos_preliminares": 30},
        ])

    def test_elimina_filas_sin_candidato(self):
        df_filtrado, n_removed = filter_administrative_rows(self._raw_df())
        assert n_removed == 2
        assert len(df_filtrado) == 2
        assert df_filtrado["cod_candidato"].notna().all()

    def test_nunca_asigna_ind(self):
        """La regla nunca debe reetiquetar filas administrativas como
        partido 'IND' (a diferencia de procesar_servel_cut.py)."""
        df_filtrado, _ = filter_administrative_rows(self._raw_df())
        assert "IND" not in df_filtrado["partido"].values
        assert not (df_filtrado["partido"] == "IND").any()

    def test_columna_faltante_lanza_keyerror(self):
        with pytest.raises(KeyError):
            filter_administrative_rows(pd.DataFrame({"x": [1, 2]}), candidate_col="cod_candidato")

    def test_no_elimina_filas_validas(self):
        df = pd.DataFrame({"cod_candidato": [1, 2, 3], "votos": [10, 20, 30]})
        df_filtrado, n_removed = filter_administrative_rows(df)
        assert n_removed == 0
        assert len(df_filtrado) == 3


# ──────────────────────────────────────────────────────────────────────────────
# BLOQUE 2 — import_candidates / import_results
# ──────────────────────────────────────────────────────────────────────────────

# CUT reales (verificados contra datos/scripts_extra/procesar_servel_cut.py::
# MAPA_COMUNA_CUT), ya con nombres normalizados como llave — igual que
# construir_mapa_comuna_cut() en escanos.py construye el mapa real desde
# cd.load_layer("comunal").
_FAKE_COMMUNE_CUT_MAP = {
    "SANTIAGO":         13101,
    "MARCHIHUE":        6204,
    "TREGUACO":         16207,
    "PAIGUANO":         4105,
    "LLAILLAY":         5703,
    "CABO DE HORNOS":   12201,
}


def _raw_servel_rows(*, distrito="Distrito 1", extra_admin_row=False):
    """
    Filas con la misma forma que un Excel PRELIMINARES_DIPUTADOS_DISTRITO_N.xlsx:
    region, distrito, comuna, pacto, subpacto, partido, cod_candidato,
    nombre_candidato, votos_preliminares, electo_nominado.
    """
    rows = [
        {
            "region": 13, "distrito": distrito, "comuna": "Santiago",
            "pacto": "Unidad por Chile", "subpacto": "A", "partido": "PS",
            "cod_candidato": 1001, "nombre_candidato": "Candidato Uno",
            "votos_preliminares": 1000, "electo_nominado": 1,
        },
        {
            "region": 13, "distrito": distrito, "comuna": "Santiago",
            "pacto": "Chile Grande y Unido", "subpacto": "B", "partido": "IND",
            "cod_candidato": 1002, "nombre_candidato": "Candidato Independiente",
            "votos_preliminares": 500, "electo_nominado": 0,
        },
    ]
    if extra_admin_row:
        rows.append({
            "region": 13, "distrito": distrito, "comuna": "Santiago",
            "pacto": None, "subpacto": None, "partido": None,
            "cod_candidato": None, "nombre_candidato": "Votos Nulos",
            "votos_preliminares": 314, "electo_nominado": None,
        })
    return rows


def _write_excel(tmp_path, filename, rows) -> None:
    pd.DataFrame(rows).to_excel(tmp_path / filename, index=False, engine="openpyxl")


class TestImportCandidates:

    def test_filas_administrativas_nunca_terminan_como_ind(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx",
            _raw_servel_rows(extra_admin_row=True),
        )
        df, provenance = import_candidates(
            tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
        )

        assert provenance["administrative_rows_removed"] == 1
        # La fila administrativa (314 votos, sin cod_candidato) no debe
        # aparecer como ningún candidato, y en particular no debe sumarse
        # al partido "ind" del candidato independiente real (que ya existe,
        # cod_candidato=1002, party_id derivado de "IND").
        assert len(df) == 2
        ind_row = df[df["candidate_id"] == 1002].iloc[0]
        assert ind_row["votes"] == 500  # no 500 + 314
        assert ind_row["independent_status"] is True or bool(ind_row["independent_status"])

    def test_cut_se_normaliza_marchigue_a_6204(self, tmp_path):
        rows = _raw_servel_rows()
        rows[0]["comuna"] = "MARCHIGUE"  # alias, no el nombre canónico
        _write_excel(tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", rows)

        df, provenance = import_candidates(
            tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
        )

        fila = df[df["candidate_id"] == 1001].iloc[0]
        assert fila["CUT"] == 6204
        assert "MARCHIGUE" in provenance["commune_aliases_applied"]

    @pytest.mark.parametrize("alias,canonico,cut_esperado", [
        ("MARCHIGUE",                   "MARCHIHUE",      6204),
        ("TREHUACO",                    "TREGUACO",       16207),
        ("PAIHUANO",                    "PAIGUANO",       4105),
        ("LLAY-LLAY",                   "LLAILLAY",       5703),
        ("CABO DE HORNOS(EX-NAVARINO)", "CABO DE HORNOS", 12201),
    ])
    def test_los_5_aliases_conocidos_se_resuelven(
        self, tmp_path, alias, canonico, cut_esperado,
    ):
        assert COMMUNE_NAME_ALIASES[normalize_commune_name(alias)] == canonico

        rows = _raw_servel_rows()
        rows[0]["comuna"] = alias
        _write_excel(tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", rows)

        df, provenance = import_candidates(
            tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
        )
        assert not provenance["unresolved_entities"]
        assert df[df["candidate_id"] == 1001].iloc[0]["CUT"] == cut_esperado

    def test_conservacion_de_votos_validos(self, tmp_path):
        rows = _raw_servel_rows(extra_admin_row=True)
        _write_excel(tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", rows)

        votos_candidatos_reales = sum(
            r["votos_preliminares"] for r in rows if r["cod_candidato"] is not None
        )

        df, provenance = import_candidates(
            tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
        )

        assert not provenance["unresolved_entities"], (
            "esta prueba requiere que todas las comunas resuelvan a CUT "
            "para que la conservación de votos sea 1:1"
        )
        assert df["votes"].sum() == votos_candidatos_reales

    def test_schema_canonico_columnas_exactas(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", _raw_servel_rows(),
        )
        df, _ = import_candidates(tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP)

        campos_esperados = [f.name for f in dataclasses.fields(CandidateRecord)]
        assert list(df.columns) == campos_esperados

    def test_comuna_sin_cut_queda_en_unresolved_entities(self, tmp_path):
        rows = _raw_servel_rows()
        rows[0]["comuna"] = "Comuna Inexistente"
        _write_excel(tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", rows)

        df, provenance = import_candidates(
            tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
        )
        assert "Comuna Inexistente" in provenance["unresolved_entities"]
        assert 1001 not in df["candidate_id"].values  # se descarta, no se inventa CUT

    def test_multiples_distritos_se_concatenan(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx",
            _raw_servel_rows(distrito="Distrito 1"),
        )
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_8.xlsx",
            _raw_servel_rows(distrito="Distrito 8"),
        )
        df, _ = import_candidates(tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP)
        assert set(df["district_id"].unique()) == {1, 8}
        assert len(df) == 4  # 2 candidatos x 2 distritos

    def test_office_invalido_lanza_error(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", _raw_servel_rows(),
        )
        with pytest.raises(ValueError):
            import_candidates(
                tmp_path, office="alcalde", commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
            )

    def test_sin_base_dir_ni_commune_cut_map_lanza_error(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", _raw_servel_rows(),
        )
        with pytest.raises(ValueError):
            import_candidates(tmp_path)


class TestImportResults:

    def test_schema_columnas_exactas(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", _raw_servel_rows(),
        )
        df, _ = import_results(tmp_path)
        assert list(df.columns) == ["election_id", "district_id", "list_id", "seats_won"]

    def test_cuenta_solo_electos(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", _raw_servel_rows(),
        )
        df, provenance = import_results(tmp_path)
        # Solo cod_candidato=1001 (PS / Unidad por Chile) tiene electo_nominado=1
        assert provenance["total_seats"] == 1
        assert df.loc[df["list_id"] == "Unidad por Chile", "seats_won"].iloc[0] == 1


# ──────────────────────────────────────────────────────────────────────────────
# BLOQUE 3 — provenance
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeProvenance:

    def test_sha256_no_vacio(self, tmp_path):
        archivo = tmp_path / "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx"
        pd.DataFrame(_raw_servel_rows()).to_excel(archivo, index=False, engine="openpyxl")

        record = compute_provenance(archivo, election_id="CL-2025-DIP")

        assert isinstance(record, ProvenanceRecord)
        assert record.sha256 != ""
        assert len(record.sha256) == 64  # hex digest de sha256
        assert all(c in "0123456789abcdef" for c in record.sha256)

    def test_campos_completos(self, tmp_path):
        archivo = tmp_path / "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx"
        pd.DataFrame(_raw_servel_rows()).to_excel(archivo, index=False, engine="openpyxl")

        record = compute_provenance(archivo, election_id="CL-2025-DIP", authority="SERVEL")

        assert record.authority == "SERVEL"
        assert record.original_filename == "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx"
        assert record.election_id == "CL-2025-DIP"
        assert record.parser_version == PARSER_VERSION
        assert record.retrieved_at  # ISO 8601, no vacío
        assert "T" in record.retrieved_at  # separador ISO 8601 fecha/hora

    def test_determinista_mismo_archivo_mismo_hash(self, tmp_path):
        archivo = tmp_path / "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx"
        pd.DataFrame(_raw_servel_rows()).to_excel(archivo, index=False, engine="openpyxl")

        r1 = compute_provenance(archivo, election_id="CL-2025-DIP")
        r2 = compute_provenance(archivo, election_id="CL-2025-DIP")
        assert r1.sha256 == r2.sha256
        assert r1.retrieved_at == r2.retrieved_at

    def test_archivo_inexistente_lanza_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compute_provenance(tmp_path / "no_existe.xlsx", election_id="CL-2025-DIP")


class TestImportCandidatesProvenanceIntegration:

    def test_source_provenance_tiene_sha256_por_archivo(self, tmp_path):
        _write_excel(
            tmp_path, "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx", _raw_servel_rows(),
        )
        _, provenance = import_candidates(
            tmp_path, commune_cut_map=_FAKE_COMMUNE_CUT_MAP,
        )

        assert "source_provenance" in provenance
        assert len(provenance["source_provenance"]) == 1
        record = provenance["source_provenance"][0]
        assert record["sha256"] != ""
        assert record["original_filename"] == "PRELIMINARES_DIPUTADOS_DISTRITO_1.xlsx"
