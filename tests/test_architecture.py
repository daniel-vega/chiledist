"""
tests/test_architecture.py
=============================
Tests arquitectónicos de la refactorización a 5 capas (Etapa 3).

No prueban lógica de negocio (eso ya lo cubren los demás archivos de
tests/) — prueban que la arquitectura en sí se mantiene:

    1. La API pública plana (`import chiledist as cd`) no se rompió al
       reorganizar los archivos internos en domain/rules/engines/
       inference/evaluation.
    2. Las reglas de dependencia entre capas se respetan (domain/ y
       rules/ no importan "hacia arriba"), leyendo los imports de cada
       archivo con `ast` en vez de ejecutarlos.
    3. Un puñado de resultados numéricos conocidos no cambiaron durante
       el movimiento de código (Etapas 1 y 2 no debían alterar ningún
       resultado — esto es la prueba de esa afirmación).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartidos: ubicar el paquete sin ejecutarlo
# ─────────────────────────────────────────────────────────────────────────────

def _package_root() -> Path:
    """Directorio chiledist/chiledist/ — vía importlib, sin ejecutar el paquete."""
    spec = importlib.util.find_spec("chiledist")
    assert spec is not None and spec.origin is not None, (
        "No se pudo localizar el paquete chiledist con importlib.util.find_spec — "
        "¿está en PYTHONPATH?"
    )
    return Path(spec.origin).parent


PACKAGE_ROOT = _package_root()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Imports públicos vigentes (regresión de API)
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicAPI:
    """
    Congela la fachada plana `import chiledist as cd` tras el movimiento
    de archivos de las Etapas 1 y 2. Si alguno de estos símbolos deja de
    existir (por un import roto, un nombre mal escrito al reexportar
    desde la nueva ubicación, etc.), esta prueba lo detecta sin depender
    de que algún otro test ejercite justo esa función.
    """

    def test_symbolos_clave_explicitos(self):
        import chiledist as cd

        # Un símbolo representativo por capa, nombrados explícitamente
        # para que un fallo aquí diga inmediatamente qué capa se rompió.
        assert hasattr(cd, "dhondt")                       # engines.allocation
        assert hasattr(cd, "personas_por_escano")           # evaluation
        assert hasattr(cd, "run_recom_chain")                # engines.samplers
        assert hasattr(cd, "weighted_population_balance")   # evaluation
        assert hasattr(cd, "MAGNITUDES_LEGALES_LEY20840")   # rules
        assert hasattr(cd, "MAGNITUDES_CENSO2024_2026")     # rules
        assert hasattr(cd, "normalize_party_name")           # engines.allocation
        # domain e inference, para completar las 5 capas
        assert hasattr(cd, "ChileDistMap")                  # domain
        assert hasattr(cd, "compare_ensembles")              # inference

    def test_todos_los_simbolos_de_all(self):
        """Todo lo declarado en __all__ debe ser efectivamente accesible."""
        import chiledist as cd

        assert len(cd.__all__) > 0, "__all__ está vacío — ¿se rompió el facade?"
        faltantes = [s for s in cd.__all__ if not hasattr(cd, s)]
        assert not faltantes, (
            f"{len(faltantes)} símbolo(s) en __all__ pero no accesibles vía "
            f"cd.<nombre>: {faltantes}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Ausencia de ciclos críticos entre capas (AST estático, sin ejecutar)
# ─────────────────────────────────────────────────────────────────────────────

#: Orden de capas 0→4. domain/ solo puede depender de sí mismo (y de la
#: raíz del paquete para leaf modules como _version.py); rules/ puede
#: depender de domain/ y de sí mismo; etc.
_LAYER_ORDER = ["domain", "rules", "engines", "inference", "evaluation"]


def _module_dotted_name(py_file: Path) -> str:
    """Nombre de módulo punteado (chiledist.domain.scenario) desde su ruta."""
    rel = py_file.relative_to(PACKAGE_ROOT.parent)  # incluye 'chiledist/' al inicio
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _containing_package(py_file: Path) -> str:
    """Paquete que contiene a py_file, para resolver imports relativos."""
    dotted = _module_dotted_name(py_file)
    if py_file.name == "__init__.py":
        return dotted
    return dotted.rsplit(".", 1)[0] if "." in dotted else ""


def _resolve_import(py_file: Path, node: ast.AST) -> list[str]:
    """
    Dado un nodo ast.Import o ast.ImportFrom, retorna la(s) ruta(s)
    punteada(s) absoluta(s) importada(s) (solo el módulo, sin los nombres
    importados individualmente).
    """
    resolved: list[str] = []

    if isinstance(node, ast.Import):
        for alias in node.names:
            resolved.append(alias.name)

    elif isinstance(node, ast.ImportFrom):
        if node.level == 0:
            # Import absoluto: from chiledist.evaluation.scoring import X
            if node.module:
                resolved.append(node.module)
        else:
            # Import relativo: from ..evaluation.scoring import X
            pkg = _containing_package(py_file)
            pkg_parts = pkg.split(".") if pkg else []
            # level=1 → paquete contenedor; level=2 → un nivel arriba; etc.
            cut = len(pkg_parts) - (node.level - 1)
            base_parts = pkg_parts[: max(cut, 0)]
            if node.module:
                base_parts = base_parts + node.module.split(".")
            resolved.append(".".join(base_parts))

    return resolved


def _imports_of(py_file: Path) -> list[str]:
    """Todas las rutas de módulo importadas por py_file, leyendo el AST."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.extend(_resolve_import(py_file, node))
    return imports


def _layer_files(layer: str) -> list[Path]:
    layer_dir = PACKAGE_ROOT / layer
    if not layer_dir.is_dir():
        return []
    return sorted(layer_dir.rglob("*.py"))


class TestLayerBoundaries:
    """
    Regla de dependencia: cada capa solo puede importar de sí misma y de
    capas *anteriores* en el orden domain(0) < rules(1) < engines(2) <
    inference(3) < evaluation(4). Esta prueba solo verifica las dos
    fronteras más críticas — domain y rules, las capas más bajas, cuya
    contaminación hacia arriba fue precisamente el origen de los 3 ciclos
    de import resueltos en la Etapa 1 (ver ARCHITECTURE.md).

    No se verifica engines/inference/evaluation aquí: esas capas SÍ
    tienen una dependencia hacia adelante documentada y aceptada (ver
    ARCHITECTURE.md, sección "Inversión de dependencia documentada").
    """

    def _assert_no_forward_imports(self, layer: str, forbidden_layers: list[str]):
        violations: list[str] = []
        for py_file in _layer_files(layer):
            for imported in _imports_of(py_file):
                for forbidden in forbidden_layers:
                    if imported == f"chiledist.{forbidden}" or imported.startswith(
                        f"chiledist.{forbidden}."
                    ):
                        violations.append(
                            f"{py_file.relative_to(PACKAGE_ROOT)} importa "
                            f"'{imported}' (capa '{forbidden}' está por encima "
                            f"de '{layer}')"
                        )
        assert not violations, (
            f"{layer}/ no debe importar de {forbidden_layers}, pero se "
            f"encontraron {len(violations)} violación(es):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_domain_no_importa_de_capas_superiores(self):
        self._assert_no_forward_imports("domain", ["rules", "engines", "inference", "evaluation"])

    def test_rules_no_importa_de_capas_superiores(self):
        self._assert_no_forward_imports("rules", ["engines", "inference", "evaluation"])

    def test_domain_y_rules_tienen_archivos(self):
        """Guardia contra falso-positivo: si las capas están vacías, las
        pruebas de arriba pasarían trivialmente sin verificar nada."""
        assert len(_layer_files("domain")) >= 5
        assert len(_layer_files("rules")) >= 5


# ─────────────────────────────────────────────────────────────────────────────
# 3. Equivalencia numérica antes/después del movimiento de código
# ─────────────────────────────────────────────────────────────────────────────

class TestNumericEquivalence:
    """
    No re-derivan las fórmulas — comparan contra un resultado conocido
    (calculado a mano o documentado en SCIENTIFIC_HYPOTHESES.md) para
    detectar si mover código de archivo cambió algún comportamiento.
    """

    # -- a) D'Hondt binivel: caso de la documentación (SCIENTIFIC_HYPOTHESES.md
    #       § "Validación empírica — D'Hondt binivel vs SERVEL 2025" reporta
    #       96/96 combinaciones (distrito, pacto) contra datos reales de
    #       SERVEL 2025 no distribuidos con el repo. Ese archivo real no está
    #       disponible en tests/, así que este caso usa votos sintéticos con
    #       la forma de un distrito real (2 pactos, 4 partidos) y un
    #       resultado verificado a mano — el mismo caso documentado en el
    #       docstring de dhondt_binivel() y en test_electoral_binivel.py.
    def test_dhondt_binivel_caso_conocido(self):
        from chiledist.engines.allocation.dhondt import dhondt_binivel

        votos = {"PS": 30_000, "PPD": 20_000, "RN": 40_000, "UDI": 25_000}
        pactos = {
            "PS": "Apruebo", "PPD": "Apruebo",
            "RN": "Chile Vamos", "UDI": "Chile Vamos",
        }
        resultado = dhondt_binivel(votos, pactos, seats=3)

        # Verificado a mano:
        #   Nivel pactos (3 escaños): Apruebo=50000, Chile Vamos=65000
        #     → Chile Vamos, Apruebo, Chile Vamos = Apruebo:1, Chile Vamos:2
        #   Nivel partidos, Apruebo (1 escaño): PS=30000 > PPD=20000 → PS:1, PPD:0
        #   Nivel partidos, Chile Vamos (2 escaños): RN=40000, UDI=25000
        #     → RN, UDI = RN:1, UDI:1
        assert resultado == {"PS": 1, "PPD": 0, "RN": 1, "UDI": 1}
        assert sum(resultado.values()) == 3

    # -- b) assign_seat_magnitudes_dhondt: SCIENTIFIC_HYPOTHESES.md § "Validación
    #       assign_seat_magnitudes" reporta 26/28 coincidencias exactas contra
    #       MAGNITUDES_CENSO2024_2026 usando población real del Censo 2024 (no
    #       distribuida con el repo). Como proxy sintético usamos población
    #       proporcional a esas mismas magnitudes legales (más escaños legales
    #       ⇒ más población, la relación que D'Hondt básicamente invierte) y
    #       verificamos que el número de coincidencias no caiga bajo el piso
    #       real documentado — con población perfectamente proporcional se
    #       espera igual o mejor que 26/28, nunca peor.
    def test_assign_seat_magnitudes_dhondt_piso_26_de_28(self):
        import pandas as pd

        from chiledist.rules.electoral_rules import (
            MAGNITUDES_CENSO2024_2026,
            TOTAL_ESCANOS_CAMARA,
            MIN_ESCANOS_DISTRITO,
            MAX_ESCANOS_DISTRITO,
        )
        from chiledist.engines.allocation.magnitudes import assign_seat_magnitudes_dhondt

        magnitudes_legales = pd.Series(MAGNITUDES_CENSO2024_2026)
        poblacion_sintetica = magnitudes_legales * 200_000  # proxy proporcional

        calculado = assign_seat_magnitudes_dhondt(
            poblacion_sintetica,
            total_seats=TOTAL_ESCANOS_CAMARA,
            min_seats=MIN_ESCANOS_DISTRITO,
            max_seats=MAX_ESCANOS_DISTRITO,
        )

        coincidencias = int((calculado == magnitudes_legales).sum())
        assert coincidencias >= 26, (
            f"Solo {coincidencias}/28 coincidencias — el piso documentado en "
            "SCIENTIFIC_HYPOTHESES.md (validación contra población real) es "
            "26/28; con población sintética perfectamente proporcional no "
            "debería estar por debajo de ese piso."
        )
        assert int(calculado.sum()) == TOTAL_ESCANOS_CAMARA

    # -- c) polsby_popper: círculo perfecto → 1.0
    def test_polsby_popper_circulo(self):
        import geopandas as gpd
        from shapely.geometry import Point

        from chiledist.domain.equivalence import CRS_METRIC
        from chiledist.engines.metrics import polsby_popper

        circulo = Point(0, 0).buffer(1.0, resolution=128)
        gdf = gpd.GeoDataFrame({"geometry": [circulo]}, crs=CRS_METRIC)

        pp = polsby_popper(gdf).iloc[0]
        assert abs(pp - 1.0) < 1e-3

    # -- d) ReCom sintético: misma semilla → mismo assignment.
    #       run_recom_chain() es "la única fuente de verdad para el muestreo"
    #       (su propio docstring) — es la función de verdad de bajo nivel que
    #       scripts/redistritaje.py ejecuta en producción. run_recom() (la
    #       envoltura de conveniencia de alto nivel) tenía varios bugs
    #       latentes que la volvían no invocable — corregidos en la Etapa 3
    #       (BUGs 2 y 3, ver tests/test_recom.py). gerrychain usa
    #       random.random() del stdlib internamente para el muestreo de
    #       árboles de expansión, NO numpy — sembrar random.seed() (no
    #       np.random.seed) es lo que controla la reproducibilidad real de
    #       la cadena.
    def test_recom_reproducibilidad_por_semilla(self):
        gc = pytest.importorskip("gerrychain")
        import random

        import geopandas as gpd
        import numpy as np
        from shapely.geometry import box
        from gerrychain.proposals import recom as recom_proposal
        from gerrychain.accept import always_accept
        from functools import partial

        from chiledist.engines.samplers.recom import run_recom_chain

        def _build_chain():
            filas = [
                {"id": f"U{i}_{j}", "geometry": box(i, j, i + 1, j + 1), "pop": 10}
                for i in range(4)
                for j in range(4)
            ]
            gdf = gpd.GeoDataFrame(filas, crs="EPSG:32719").reset_index(drop=True)
            graph = gc.Graph.from_geodataframe(
                gdf, adjacency="queen", cols_to_add=["id", "pop"]
            )
            # Asignación inicial determinista y contigua para esta grilla:
            # agrupar por "columna" (mismo j) produce 4 franjas horizontales
            # contiguas — evita depender de contiguous_bfs (que en esta
            # versión de gerrychain no genera particiones, solo las valida).
            n_districts = 4
            assignment = {node: node % n_districts for node in graph.nodes()}
            updaters = {
                "population": gc.updaters.Tally("pop", alias="population"),
                "cut_edges": gc.updaters.cut_edges,
            }
            partition = gc.Partition(graph=graph, assignment=assignment, updaters=updaters)
            constraints = [
                gc.constraints.contiguous,
                gc.constraints.within_percent_of_ideal_population(partition, 0.6),
            ]
            proposal = partial(
                recom_proposal, pop_col="pop", pop_target=40, epsilon=0.6, node_repeats=2
            )
            chain = gc.MarkovChain(
                proposal=proposal,
                constraints=constraints,
                accept=always_accept,
                initial_state=partition,
                total_steps=5,
            )
            return chain, graph

        random.seed(123)
        chain1, graph1 = _build_chain()
        planes1, _, n1 = run_recom_chain(
            chain1, n_steps=5, id_col="id", ids_ordenados=list(range(16)),
            graph=graph1, ideal_pop=40,
        )

        random.seed(123)
        chain2, graph2 = _build_chain()
        planes2, _, n2 = run_recom_chain(
            chain2, n_steps=5, id_col="id", ids_ordenados=list(range(16)),
            graph=graph2, ideal_pop=40,
        )

        assert n1 == n2 == 5
        assert planes1 == planes2, (
            "Misma semilla (random.seed) debe producir la misma secuencia "
            "de planes — la cadena ReCom debe ser determinista dado un RNG "
            "sembrado igual."
        )
