"""
tests/test_scenario_multinivel.py
====================================
Unit tests for multi-level hierarchical preservation (preservación
jerárquica multinivel):

    - Etapa 4: los 3 presets de escenario regionales agregados en
      chiledist/rules/scenario_rules.py:
          SCENARIO_COMUNAS_HARD_REGION_SOFT  (E2 — CUT hard, COD_REGION soft)
          SCENARIO_COMUNAS_HARD_REGION_HARD  (E3 — CUT hard, COD_REGION hard)
          SCENARIO_REGION_SOFT_ONLY          (E6 — solo COD_REGION soft)
      No requieren gerrychain ni datos reales — solo
      ScenarioConfig.validate()/resolved_preserve_mode().

    - Etapa 5: el preflight compuesto de scripts/redistritaje.py que,
      además del preflight existente sobre decision_unit, verifica
      factibilidad poblacional para cualquier columna con
      preserve_mode="hard" más gruesa que decision_unit (ej. COD_REGION).
      Corre scripts/redistritaje.py::analizar_region() de verdad, con
      carga de datos (cd.load_layer/aggregate_population/
      apply_rural_proxy_fallback) monkeypatcheada con GDFs sintéticos
      mínimos — sin shapefiles reales. El caso "factible" sí llega a
      correr una cadena ReCom real, pero deliberadamente trivial (4
      nodos, 2 distritos, con una única partición geométricamente válida
      que además respeta CUT y COD_REGION) para evitar el riesgo de
      warm-up infinito documentado para decision_unit más fino que una
      columna hard (ver SCIENTIFIC_HYPOTHESES.md §apc_strict) — verificado
      manualmente antes de escribir estos tests que termina en <5s, no
      cuelga.
"""

from __future__ import annotations

import importlib.util
import os
import warnings

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from chiledist.domain.scenario import ScenarioConfig
from chiledist.rules.scenario_rules import (
    SCENARIO_LEGAL,
    SCENARIO_APC_SOFT,
    SCENARIO_APC_FREE,
    SCENARIO_COMUNAS_HARD_REGION_SOFT,
    SCENARIO_COMUNAS_HARD_REGION_HARD,
    SCENARIO_REGION_SOFT_ONLY,
)


def _fineness_warnings(scenario) -> list[str]:
    """Warnings emitidos por validate() cuyo mensaje referencia el patrón
    apc_strict (ver ScenarioConfig.validate(), _UNIT_HIERARCHY) — aísla la
    advertencia de "fineness" de otras advertencias no relacionadas (ej.
    pop_col='viviendas')."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scenario.validate()
    return [str(w.message) for w in caught if "apc_strict" in str(w.message)]


# ── 1. Importables + atributos básicos ─────────────────────────────────────────

class TestScenarioAttributes:

    def test_comunas_hard_region_soft_attrs(self):
        sc = SCENARIO_COMUNAS_HARD_REGION_SOFT
        assert sc.name == "comunas_hard_region_soft"
        assert sc.tipo_reforma == "contrafactual_regional"
        assert sc.preserve_units == ["CUT", "COD_REGION"]
        assert sc.decision_unit == "CUT"

    def test_comunas_hard_region_hard_attrs(self):
        sc = SCENARIO_COMUNAS_HARD_REGION_HARD
        assert sc.name == "comunas_hard_region_hard"
        assert sc.tipo_reforma == "contrafactual_regional"
        assert sc.preserve_units == ["CUT", "COD_REGION"]
        assert sc.decision_unit == "CUT"

    def test_region_soft_only_attrs(self):
        sc = SCENARIO_REGION_SOFT_ONLY
        assert sc.name == "region_soft_only"
        assert sc.tipo_reforma == "contrafactual_regional"
        assert sc.preserve_units == ["COD_REGION"]
        assert sc.decision_unit == "CUT"


# ── 2. resolved_preserve_mode() por escenario ──────────────────────────────────

class TestResolvedPreserveModePerScenario:

    def test_comunas_hard_region_soft(self):
        assert SCENARIO_COMUNAS_HARD_REGION_SOFT.resolved_preserve_mode() == {
            "CUT": "hard", "COD_REGION": "soft",
        }
        # split_penalty ya es un dict explícito ({"CUT": 0.0, "COD_REGION":
        # 0.25}) -> resolved_split_penalty() lo devuelve tal cual (sin
        # filtrar por modo "soft", a diferencia del caso float uniforme) —
        # el 0.0 de CUT es explícito/documental, no tiene efecto porque CUT
        # es "hard" (nunca llega al mecanismo de aceptación soft).
        assert SCENARIO_COMUNAS_HARD_REGION_SOFT.resolved_split_penalty() == {
            "CUT": 0.0, "COD_REGION": 0.25,
        }

    def test_comunas_hard_region_hard(self):
        assert SCENARIO_COMUNAS_HARD_REGION_HARD.resolved_preserve_mode() == {
            "CUT": "hard", "COD_REGION": "hard",
        }
        # Ninguna columna es "soft" -> resolved_split_penalty vacío.
        assert SCENARIO_COMUNAS_HARD_REGION_HARD.resolved_split_penalty() == {}

    def test_region_soft_only(self):
        assert SCENARIO_REGION_SOFT_ONLY.resolved_preserve_mode() == {
            "COD_REGION": "soft",
        }
        assert SCENARIO_REGION_SOFT_ONLY.resolved_split_penalty() == {
            "COD_REGION": 0.25,
        }


# ── 3. Warning de fineness solo donde corresponde ──────────────────────────────

class TestFinenessWarningPerScenario:

    def test_comunas_hard_region_hard_emits_fineness_warning(self):
        """
        decision_unit='CUT' es más fino que 'COD_REGION' (ver
        _UNIT_HIERARCHY), y COD_REGION está en modo 'hard' -> mismo patrón
        que causó warm-up infinito con apc_strict.
        """
        assert len(_fineness_warnings(SCENARIO_COMUNAS_HARD_REGION_HARD)) > 0

    def test_comunas_hard_region_soft_does_not_warn(self):
        """
        CUT es 'hard' pero decision_unit == 'CUT' (no más fino que la
        propia columna preservada) -> caso trivial, sin riesgo. COD_REGION
        es 'soft', no 'hard' -> tampoco dispara el check (que solo mira
        columnas hard).
        """
        assert _fineness_warnings(SCENARIO_COMUNAS_HARD_REGION_SOFT) == []

    def test_region_soft_only_does_not_warn(self):
        """Ninguna columna es 'hard' -> el check de fineness (que solo
        aplica a columnas hard) no tiene nada que evaluar."""
        assert _fineness_warnings(SCENARIO_REGION_SOFT_ONLY) == []


# ── 4. Regresión: escenarios existentes sin cambios ────────────────────────────

class TestExistingScenariosUnaffected:
    """
    Agregar los 3 presets nuevos (y el nuevo tipo_reforma
    'contrafactual_regional' en domain/scenario.py) no debe introducir
    ningún warning nuevo en los escenarios existentes.
    """

    def test_scenario_legal_no_new_warnings(self):
        assert _fineness_warnings(SCENARIO_LEGAL) == []

    def test_scenario_apc_soft_no_new_warnings(self):
        assert _fineness_warnings(SCENARIO_APC_SOFT) == []

    def test_scenario_apc_free_no_new_warnings(self):
        assert _fineness_warnings(SCENARIO_APC_FREE) == []


# ── Etapa 5: preflight compuesto para columnas hard más gruesas ───────────────

def _import_redistritaje():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(root, "scripts", "redistritaje.py")
    spec = importlib.util.spec_from_file_location(
        "redistritaje_preflight_regional", script_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def redistritaje():
    return _import_redistritaje()


# 4 unidades de decisión (CUT), una por comuna, 2 comunas por región:
#   C1, C2 -> COD_REGION=R1
#   C3, C4 -> COD_REGION=R2
_REGION_BY_CUT = {"C1": "R1", "C2": "R1", "C3": "R2", "C4": "R2"}


def _make_synthetic_distritos(pops: dict) -> gpd.GeoDataFrame:
    cuts = list(pops.keys())
    return gpd.GeoDataFrame(
        {
            "ID_DIST":       cuts,
            "CUT":           cuts,
            "COD_DISTRITO":  [1] * len(cuts),
            "COD_REGION":    [_REGION_BY_CUT[c] for c in cuts],
            "COD_PROVINCIA": [_REGION_BY_CUT[c] + "P" for c in cuts],
            "N_REGION":      [_REGION_BY_CUT[c] for c in cuts],
            "N_PROVINCIA":   [_REGION_BY_CUT[c] + "P" for c in cuts],
            # cajas disjuntas en línea: Queen las hace mutuamente adyacentes
            # en orden, dando exactamente 3 aristas para 4 nodos (C1-C2-C3-C4).
            "geometry": [box(i, 0, i + 1, 1) for i in range(len(cuts))],
        },
        crs="EPSG:4326",
    )


def _patch_data_loading(redistritaje, monkeypatch, pops: dict) -> None:
    """
    Monkeypatchea cd.load_layer/aggregate_population/apply_rural_proxy_fallback
    (referenciados como cd.<fn> dentro de scripts/redistritaje.py) para que
    analizar_region() corra sobre un GDF sintético de 4 unidades en vez de
    shapefiles reales — sin tocar ninguna otra lógica de la función real.
    """
    distritos = _make_synthetic_distritos(pops)

    def fake_load_layer(layer, base_dir=None, regions=None, **kwargs):
        if layer == "distrital":
            return distritos.copy()
        # manzana_urbana/manzana_aldea/puntos_rural: su contenido es
        # irrelevante porque aggregate_population()/
        # apply_rural_proxy_fallback() están mockeadas más abajo y nunca
        # inspeccionan estos GDF.
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")

    def fake_aggregate_population(manzanas, level, source="urbana"):
        if source == "urbana":
            return pd.DataFrame({
                "CUT":          list(pops.keys()),
                "COD_DISTRITO": [1] * len(pops),
                "viviendas":    list(pops.values()),
            })
        # manzana_aldea: sin población adicional (frame vacío con las
        # mismas columnas, para que el merge urb+ald en analizar_region()
        # funcione igual que con datos reales).
        return pd.DataFrame({"CUT": [], "COD_DISTRITO": [], "viviendas": []})

    monkeypatch.setattr(redistritaje.cd, "load_layer", fake_load_layer)
    monkeypatch.setattr(redistritaje.cd, "aggregate_population", fake_aggregate_population)
    monkeypatch.setattr(redistritaje.cd, "apply_rural_proxy_fallback",
                         lambda gdf, puntos: gdf)


def _region_hard_scenario(name: str) -> ScenarioConfig:
    return ScenarioConfig(
        name=name,
        decision_unit="CUT",
        preserve_units=["CUT", "COD_REGION"],
        preserve_mode={"CUT": "hard", "COD_REGION": "hard"},
        pop_tolerance=0.10,
    )


class TestCompoundFeasibilityPreflight:

    def test_region_exceeds_ideal_returns_infeasible(
        self, redistritaje, monkeypatch, tmp_path,
    ):
        """
        R1 = C1(100) + C2(100) = 200; ideal (n_distritos=2, total=300) = 150;
        200 > 150*1.10=165 -> COD_REGION es inviable, aunque cada CUT
        individual (100) esté muy por debajo del límite (165) y por lo
        tanto el preflight EXISTENTE (a nivel decision_unit) pase.
        """
        pops = {"C1": 100, "C2": 100, "C3": 50, "C4": 50}
        _patch_data_loading(redistritaje, monkeypatch, pops)

        result = redistritaje.analizar_region(
            region_code=13,
            base_dir=".",
            output_base=str(tmp_path),
            n_distritos=2,
            pop_tol=0.10,
            n_steps=1,
            seed=42,
            skip_viz=True,
            scenario=_region_hard_scenario("test_region_infeasible"),
        )

        assert result["status"] == "infeasible_population"
        assert result["reason"] == "preserve_hard_COD_REGION_exceeds_bound"
        assert result["col"] == "COD_REGION"
        assert result["blocking_unit"] == "R1"

    def test_all_regions_within_bound_does_not_return_early(
        self, redistritaje, monkeypatch, tmp_path,
    ):
        """
        R1 = C1(75)+C2(75) = 150; R2 = C3(75)+C4(75) = 150; ideal
        (n_distritos=2, total=300) = 150 -> ambas regiones exactamente en
        el ideal, muy por debajo de 150*1.10=165. El preflight compuesto
        no debe retornar infeasible_population/preserve_hard_* — solo se
        verifica esto (no que la corrida completa "gane" en algún sentido
        de calidad de plan), por eso se usa --n-steps 1 con geometría que
        no arriesga el problema de warm-up infinito documentado para
        decision_unit más fino que una columna hard (ver docstring del
        módulo).
        """
        pops = {"C1": 75, "C2": 75, "C3": 75, "C4": 75}
        _patch_data_loading(redistritaje, monkeypatch, pops)

        result = redistritaje.analizar_region(
            region_code=13,
            base_dir=".",
            output_base=str(tmp_path),
            n_distritos=2,
            pop_tol=0.10,
            n_steps=1,
            seed=42,
            skip_viz=True,
            scenario=_region_hard_scenario("test_region_feasible"),
        )

        assert result["status"] != "infeasible_population"
        assert not str(result.get("reason", "")).startswith("preserve_hard_")


# ── Etapa 6, Parte 1: cobertura pendiente del prompt original (Etapa 4) ────────

class TestImportableFromTopLevelPackage:
    """
    Test 6 del prompt original de Etapa 4: "Los 3 son importables:
    cd.SCENARIO_COMUNAS_HARD_REGION_SOFT etc." — verificado manualmente
    en su momento (REPL), nunca capturado como test automático. Los tests
    de arriba (TestScenarioAttributes, etc.) importan directamente desde
    chiledist.rules.scenario_rules, no desde la fachada plana
    `import chiledist as cd` — este test cubre específicamente ESA vía de
    acceso, la que de hecho pidió el prompt original.
    """

    def test_los_3_escenarios_accesibles_via_cd(self):
        import chiledist as cd

        assert cd.SCENARIO_COMUNAS_HARD_REGION_SOFT is SCENARIO_COMUNAS_HARD_REGION_SOFT
        assert cd.SCENARIO_COMUNAS_HARD_REGION_HARD is SCENARIO_COMUNAS_HARD_REGION_HARD
        assert cd.SCENARIO_REGION_SOFT_ONLY is SCENARIO_REGION_SOFT_ONLY

    def test_los_3_estan_en_all(self):
        import chiledist as cd

        for nombre in (
            "SCENARIO_COMUNAS_HARD_REGION_SOFT",
            "SCENARIO_COMUNAS_HARD_REGION_HARD",
            "SCENARIO_REGION_SOFT_ONLY",
        ):
            assert nombre in cd.__all__, f"{nombre} no está en chiledist.__all__"


class TestScenariosRegistryCliAccess:
    """
    Test adicional pedido en Etapa 6: las 3 claves cortas agregadas al
    dict SCENARIOS (chiledist/rules/scenario_rules.py) para que
    --scenario <key> las resuelva en scripts/redistritaje.py /
    scripts/run_chains.py (ambos leen SCENARIOS[args.scenario] o
    choices=list(SCENARIOS.keys()) — ver Etapa "acceso CLI").
    """

    def test_las_3_claves_nuevas_estan_en_scenarios_dict(self):
        from chiledist.rules.scenario_rules import SCENARIOS

        assert SCENARIOS["comunas_hard_region_soft"] is SCENARIO_COMUNAS_HARD_REGION_SOFT
        assert SCENARIOS["comunas_hard_region_hard"] is SCENARIO_COMUNAS_HARD_REGION_HARD
        assert SCENARIOS["region_soft_only"] is SCENARIO_REGION_SOFT_ONLY

    @pytest.mark.parametrize("key", [
        "comunas_hard_region_soft", "comunas_hard_region_hard", "region_soft_only",
    ])
    def test_redistritaje_cli_acepta_la_clave_nueva(self, redistritaje, monkeypatch, key):
        """
        redistritaje.py::parse_args() usa choices=list(SCENARIOS.keys())
        en --scenario (no hay build_parser() separado en este script, a
        diferencia de run_chains.py/smc_pipeline.py) — invoca el parser
        real vía sys.argv, no solo relee el dict, para confirmar que
        argparse en sí acepta la clave (choices= rechazaría con
        SystemExit si no estuviera ahí).
        """
        monkeypatch.setattr("sys.argv", ["redistritaje.py", "--scenario", key])
        args = redistritaje.parse_args()
        assert args.scenario == key
