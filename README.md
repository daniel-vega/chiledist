# chiledist

Librería Python para redistritaje electoral y análisis distrital de Chile usando datos cartográficos oficiales del INE (APC 2023 y Censo 2024). Implementa redistritaje ReCom, comparación de escenarios, asignación de escaños por D'Hondt, diagnósticos de convergencia y exportación para el paquete `redist` (R/ALARM Harvard).

---

## Cambios recientes

**Refactorización B1 (agosto 2026):** la librería se reorganizó de módulos sueltos y paquetes ad-hoc (`electoral/`, `scenario_comparison/`, `malapportionment/`, `pareto_sweep/`, `electoral_ensemble/`, `metrics.py`, `split_metrics.py`, `config.py`, etc.) a una **arquitectura de 5 capas**: `domain` → `rules` → `engines` → `inference`/`evaluation`, más `validation` como pipeline transversal. Ver [Estructura del proyecto](#estructura-del-proyecto) y `ARCHITECTURE.md` para el detalle completo.

A diferencia de la reorganización anterior (single-file → paquete), **esta NO es compatible hacia atrás a nivel de submódulo**: `from chiledist.electoral import dhondt`, `chiledist.scenario_comparison`, `chiledist.malapportionment`, etc. ya no existen — no hay shim de compatibilidad. Lo que sí se mantiene sin cambios es la API pública de nivel superior: `import chiledist as cd; cd.dhondt(...)` sigue funcionando igual, porque `chiledist/__init__.py` reexporta las funciones públicas de las 5 capas.

También se agregó la **capa de datos SERVEL/TRICEL** (`chiledist.domain.data.tricel`, `chiledist.domain.data.servel`) y el pipeline de **validación electoral** (`chiledist.validation.validate_election()`) — ver secciones "Datos externos" y "Validación electoral" más abajo.

---

## Contexto

### ¿Qué es el APC 2023?

La **Actualización Precensal 2023 (APC 2023)** es el operativo cartográfico del INE realizado entre marzo y septiembre de 2023 como preparación para el Censo 2024. Levantó el total de edificaciones del país al más bajo nivel geográfico posible.

Los datos están disponibles como shapefiles organizados en **16 carpetas regionales** (`SHP_APC2023_R01` a `SHP_APC2023_R16`), cada una con 8 capas:

| Capa | Tipo | Descripción |
|------|------|-------------|
| `Comunal.shp` | Polígono | 345 comunas del país |
| `Distrital.shp` | Polígono | ~2.768 distritos censales |
| `Limite_Urbano_Censal.shp` | Polígono | Separación urbano/rural |
| `Aldea.shp` | Polígono | Centros rurales concentrados |
| `Manzana_Urbana.shp` | Polígono | ~200k manzanas urbanas |
| `Manzana_Aldea.shp` | Polígono | Manzanas en aldeas rurales |
| `Eje_Vial.shp` | Línea | Red vial y caminera |
| `Puntos_Edificacion_Rural.shp` | Punto | Edificaciones rurales |

### Jerarquía censal Chile ↔ USA

| Nivel | USA Census | Chile INE | Campo ID | Shapefile |
|-------|-----------|-----------|----------|-----------|
| 1 | State | Región | `COD_REGION` | — |
| 2 | County | Provincia | `COD_PROVINCIA` | — |
| 3 | Municipality | **Comuna** | `CUT` | `Comunal.shp` |
| 4 | **Census Tract** | **Distrito APC** | `ID_DIST` | `Distrital.shp` |
| 5 | Block Group | Zona Censal | `COD_ZONA` | — |
| 6 | Census Block | **Manzana** | `MANZENT` | `Manzana_Urbana.shp` |

El **Distrito APC** (`ID_DIST`) es la unidad recomendada para redistritaje. Se forma como `{CUT_5dígitos}_{COD_DISTRITO_3dígitos}`, por ejemplo `13101_021`.

### Marco normativo y modos de análisis

Chile opera bajo la **Ley 20.840 (2015)**: 28 distritos electorales con composición geográfica fija y magnitudes en rango [3, 8] escaños. Este mapa no cambia salvo reforma legislativa — no se redistribuye en cada elección.

Chiledist no replica el mapa vigente: lo usa como referencia y genera **planes alternativos** para análisis comparado. La diferencia entre los modos es qué restricciones respetan:

| Modo | Unidad mínima | Restricción comunal | Naturaleza |
|------|--------------|---------------------|------------|
| `legal` | CUT (comuna) | **Dura** — ningún distrito puede partir comunas (Ley 18.700) | Contrafactual con restricción legal |
| `apc_soft` | ID\_DIST (APC) | **Blanda** — partir comunas tiene costo pero no es ilegal | Contrafactual híbrido |
| `apc_free` | ID\_DIST (APC) | **Ninguna** — comunas divisibles libremente | Contrafactual puro; mide el costo de la restricción |

Solo el modo `legal` respeta la restricción de la Ley 18.700. Los modos APC son instrumentos de análisis científico — no son propuestas legislativas.

---

## Instalación

### Requisitos

- Python >= 3.11

### Entorno virtual (recomendado)

```bash
# Crear e instalar todo automáticamente
bash setup_env.sh

# O con nombre personalizado
bash setup_env.sh mi_entorno

# Activar
source env/bin/activate       # Linux/macOS
env\Scripts\activate          # Windows
```

### Instalación manual

`chiledist` es un paquete instalable vía `pip install -e .` (`pyproject.toml` en la raíz del repo declara todas las dependencias — es la única fuente de verdad; `setup_env.sh` lo usa internamente, no reimplementa la lista de paquetes).

```bash
# Instalación básica (dependencias de chiledist.__init__ y los flujos ReCom/análisis)
pip install -e .

# Con dependencias de test (pytest, pytest-randomly)
pip install -e ".[dev]"
```

No hay extra `[smc]` con paquetes Python adicionales — el puente a R (`chiledist.engines.samplers.smc`, `scripts/smc_pipeline.py`) es generación de script R + subprocess, no una librería Python. Requiere R con el paquete `redist` instalado aparte (fuera de pip) — ver "Bridge R / redist" más abajo. `pip install -e ".[smc]"` funciona igual (es un extra vacío) pero no reemplaza instalar R.

`requirements.txt` sigue disponible como lista plana equivalente para entornos que prefieran `pip install -r requirements.txt` en vez de una instalación editable del paquete.

### Verificar instalación

```bash
python -c "import chiledist as cd; cd.print_equivalence()"
```

---

## Estructura del proyecto

> **Post-refactorización B1 (agosto 2026):** la librería se reorganizó de módulos
> sueltos/paquetes ad-hoc a una **arquitectura de 5 capas** (`domain` → `rules` →
> `engines` → `inference`/`evaluation`, más `validation` como pipeline transversal).
> Los imports antiguos (`chiledist.electoral`, `chiledist.scenario_comparison`,
> `chiledist.malapportionment`, `chiledist.metrics`, etc.) **ya no existen** — no
> hay shim de compatibilidad. La API pública vía `import chiledist as cd` (funciones
> reexportadas en `chiledist/__init__.py`) no cambió. Ver **`ARCHITECTURE.md`** para
> el detalle completo de cada capa, sus fronteras y la justificación del diseño.

```
chiledist/
├── chiledist/                      # Librería principal
│   ├── __init__.py                 # API pública (reexporta las 5 capas)
│   ├── _version.py
│   ├── _plot_style.py              # Paleta y estilo compartido por los plots.py de cada capa
│   ├── viz.py                      # Visualización de capas, grafos y planes
│   ├── domain/                     # capa 0: entidades, loaders, grafos
│   │   ├── scenario.py             # ScenarioConfig + escenarios predefinidos + YAML (antes config.py)
│   │   ├── hierarchy.py            # Contracción APC → CUT, validación de jerarquía
│   │   ├── graph.py                # Grafos de adyacencia y matrices sparse
│   │   ├── loader.py               # Carga de capas APC y build_national
│   │   ├── persistence.py          # PlanEnsemble, manifiestos de corrida reproducibles
│   │   ├── ensemble_store.py       # build_scenario_overview, assess_comparison_completeness
│   │   ├── equivalence.py          # Tabla USA ↔ Chile, CRS, get_optimal_crs
│   │   ├── map.py                  # ChileDistMap — contenedor de datos cargados por corrida
│   │   ├── utils.py                # normalize_party_name y otros helpers de normalización
│   │   └── data/                   # census2024.py + servel/ (SERVEL) + tricel/ (TRICEL, ver "Datos externos")
│   ├── rules/                      # capa 1: restricciones legales, magnitudes
│   │   ├── constraints.py          # Restricciones gerrychain + penalización splits
│   │   ├── electoral_rules.py      # MAGNITUDES_LEGALES_LEY20840, MAGNITUDES_CENSO2024_2026
│   │   ├── feasibility.py          # check_population_feasibility — preflight de factibilidad
│   │   ├── scenario_rules.py       # Reglas de escenario (legal/apc_soft/apc_free)
│   │   └── split_rules.py          # is_split() y otras reglas de partición
│   ├── engines/                    # capa 2: D'Hondt, ReCom, métricas
│   │   ├── metrics.py              # Compacidad, balance poblacional Y métricas de comunas partidas (antes metrics.py + split_metrics.py)
│   │   ├── fairshare.py            # Fair share biproporcional (IPF) y distancia al ideal
│   │   ├── redistricting.py
│   │   ├── diagnostics.py
│   │   ├── allocation/             # dhondt.py (D'Hondt uni/binivel), magnitudes.py, plan_metrics.py
│   │   └── samplers/               # recom.py, smc.py, accept.py, updaters.py, diagnostics.py
│   ├── inference/                  # capa 3: ensembles, Pareto, sensibilidad
│   │   ├── comparison.py           # compare_ensembles, scenario_delta, pareto_frontier_nd
│   │   ├── sensitivity.py          # position_plan_vigente, compare_sensitivity, ranking_concordance (H5)
│   │   ├── plots.py                # plot_tradeoff_frontier, boxplots, radar
│   │   ├── pareto_sweep/           # sweep_split_penalty, build_tradeoff_frontier, knee point (H2)
│   │   └── electoral_ensemble/     # run_electoral_ensemble, ensemble_gallagher, etc.
│   ├── evaluation/                 # capa 4: proporcionalidad, malapportionment
│   │   ├── proportionality.py      # gallagher_index, loosemore_hanby, rae_index, seat_bonus
│   │   ├── district_malapportionment.py  # personas_por_escano, peso_relativo_del_voto, weighted_population_balance
│   │   ├── scoring.py              # ScoringConfig, METRICAS_STD, PESOS_DEFAULT
│   │   ├── framing.py              # reforma_context
│   │   └── malapportionment/       # indices.py, comparison.py (international_comparison), plots.py
│   └── validation/                 # pipeline de validación electoral (TRICEL 2025)
│       └── __init__.py             # validate_election(), ValidationReport
│
├── scripts/                        # Scripts de análisis operativos
│   ├── setup.py                    # Inicialización del proyecto
│   ├── redistritaje.py             # Redistritaje ReCom parametrizable por escenario
│   ├── compare_scenarios.py        # Comparación formal de 3 escenarios
│   ├── pareto_sweep.py             # H2: barrido split_penalty → frontera Pareto
│   ├── malapportionment.py         # H3: malapportionment con magnitudes legales
│   ├── electoral_analysis.py       # H4: D'Hondt binivel sobre ensemble
│   ├── run_chains.py               # H5: N cadenas ReCom + diagnósticos de convergencia
│   ├── smc_pipeline.py             # H5: bridge Python → R/redist → Python
│   ├── autocorrelacion.py          # Autocorrelación espacial
│   ├── export_imc_bundle.py        # Exportación bundle IMC Plan Lab
│   ├── validar_dhondt.py           # Validación D'Hondt binivel vs SERVEL 2025 (96/96)
│   ├── validar_tricel.py           # Validación electoral completa vs TRICEL 2025 (24/28)
│   ├── validar_datos_externos.py   # Validación de datos externos antes de análisis
│   └── recalcular_reock.py         # Recalcula métrica Reock tras corrección shapely 2.x
│
├── datos/                      # Salidas (generado automáticamente) + insumos manuales
│   ├── asignacion_vigente.json # Insumo manual: mapa distrital vigente (Ley 20.840), ver
│   │                           # "Datos externos" más abajo — NO se genera automáticamente
│   ├── pacto_map_2025.json     # Insumo manual: mapa partido → pacto electoral (D'Hondt
│   │                           # binivel), ver "Datos externos" — NO se genera automáticamente
│   ├── nacional/
│   │   ├── matrices/           # .npz, .csv, R export
│   │   ├── figuras/
│   │   ├── redistritaje_apc/       # Redistritaje nacional a nivel APC (~2.768 nodos)
│   │   ├── redistritaje_comunal/   # Redistritaje nacional a nivel comunal (345 nodos)
│   │   ├── autocorrelacion/        # Autocorrelación nacional APC
│   │   └── autocorrelacion_comunal/ # Autocorrelación nacional comunal
│   └── R{N}_{NOMBRE}/              # Una carpeta por región (ej. R13_METROPOLITANA)
│       ├── redistritaje/       # Redistritaje por región (--regiones N)
│       └── autocorrelacion/
│
├── imc_bundle_{level}_{scope}/ # Bundle IMC Plan Lab
│   ├── units.geojson
│   ├── adjacency.json
│   ├── metadata.json
│   └── README.md
│
├── requirements.txt
├── setup_env.sh
└── README.md
```

---

## Flujo de trabajo

```
1. setup.py              →  matrices nacionales, figuras, exportación R
         ↓
2. redistritaje.py        →  ensembles ReCom por escenario (legal / apc_free / apc_soft)
                              con población desde APC, Censo 2024 o padrón SERVEL
         ↓
3. compare_scenarios.py   →  H1: comparación formal: tabla, tradeoff plots, boxplots
         ↓
4. pareto_sweep.py        →  H2: barrido split_penalty → frontera Pareto
   malapportionment.py    →  H3: malapportionment con magnitudes Ley 20840
   electoral_analysis.py  →  H4: D'Hondt binivel sobre ensemble
   run_chains.py          →  H5: N cadenas ReCom + mixing_diagnostics + sensibilidad
   smc_pipeline.py        →  H5: bridge Python → R/redist → comparación SMC vs ReCom
         ↓
5. autocorrelacion.py     →  Moran, LISA, G* (por región, nacional APC o comunal)
         ↓
6. export_imc_bundle.py   →  bundle GeoJSON/JSON para Plan Lab
```

---

## Datos externos

### `datos/asignacion_vigente.json` — mapa distrital vigente (Ley 20.840)

A diferencia de todo lo demás en `datos/`, este archivo **no lo genera ningún
script de chiledist** — es un insumo curado manualmente a partir de fuentes
oficiales, que documentamos aquí para que sea reproducible.

**Qué es.** El mapa de distritos electorales de la Cámara de Diputados
actualmente vigente (28 distritos, Ley 18.700 modificada por Ley 20.840),
expresado como la asignación comuna → distrito que consumen
`scripts/malapportionment.py` (H3) y `scripts/electoral_analysis.py` (H4)
vía su argumento `--assignment-path`. Es el contrafactual de referencia
("¿cuánto malapportionment tiene el mapa que ya existe?", "¿cómo se
distribuyen los escaños D'Hondt bajo la geografía distrital real?") frente
a los mapas sintéticos que produce `redistritaje.py`.

**Esquema.**

```json
{
  "01101": 2,
  "01107": 2,
  "...": "...",
  "16305": 19
}
```

- Clave: código CUT de la comuna, **string de 5 dígitos** con cero a la
  izquierda si corresponde (ej. `1101` → `"01101"`).
- Valor: número de distrito electoral, **entero entre 1 y 28**.
- 346 entradas — una por comuna vigente.
- Codificación UTF-8.

> **No hace falta decidir si el CUT "debe" tener 4 o 5 dígitos en cada
> fuente de datos.** Distintas fuentes lo representan de forma distinta —
> `chiledist.domain.data.census2024.load_census2024()` devuelve CUT como `int`
> (sin cero inicial), mientras que este archivo usa strings de 5 dígitos.
> Usa `chiledist.normalize_cut(valor)` (`chiledist/domain/hierarchy.py`) en
> ambos lados de cualquier cruce/lookup por CUT entre fuentes distintas —
> acepta int, str con o sin cero inicial, o float, y siempre devuelve el
> string canónico de 5 dígitos. `scripts/malapportionment.py` y
> `scripts/electoral_analysis.py` ya la usan en sus loaders de
> población/asignación/votos (`_load_population`, `_load_assignment`,
> `_load_votes`) — antes de esto, un cruce ingenuo (`str(cut)` sin relleno)
> descartaba en silencio toda comuna de regiones 1–9 (las que necesitan el
> cero a la izquierda): ~206 de 346 comunas y cerca de la mitad de la
> población nacional desaparecían del cálculo de malapportionment sin
> ningún error ni warning. Ver `tests/test_cut_normalization.py`.
>
> **Bug relacionado, ya corregido, y distinto del anterior:**
> `scripts/malapportionment.py::analisis_electoral()` (A4) recibía
> población agregada por **distrito** (salida de `_load_population()`,
> usada correctamente por A1-A3) en el parámetro que
> `cd.plan_electoral_metrics()` espera indexado por **unidad/CUT**, porque
> esa función hace su propia agregación a distrito internamente vía
> `assignment`. El resultado: `pxe_max`, `pxe_min`, `ratio_max_min_pxe` y
> `peso_relativo_max/min` de A4 salían en 0/NaN en modo real (no en
> `--demo`, donde unidad y distrito coinciden por construcción). Se agregó
> `_load_population_by_unit()` (población por CUT, sin agregar) y se usa
> ahora para A4. Ver `tests/test_analisis_electoral_pop_by_unit.py`.

**Fuentes primarias.**

| Fuente | Provee | Enlace |
|--------|--------|--------|
| Códigos Únicos Territoriales (CUT) — SUBDERE / IDE Chile | `nombre_comuna ↔ código CUT` | [IDE Chile — Codificación DPA](https://www.ide.cl/index.php/informacion-territorial/codificacion-division-politico-administrativa-dpa) · [datos.gob.cl — DPA SUBDERE](https://datos.gob.cl/dataset/division-politico-administrativa-de-chile-subdere) |
| Ley N° 18.700 (texto refundido, DFL N° 2 de 2017), Art. 179 | `nombre_comuna ↔ distrito electoral (1-28)` | [BCN — Ley Chile, idNorma 1107567](https://www.bcn.cl/leychile/navegar?idNorma=1107567) |

El Art. 179 fija la conformación por comunas de los 28 distritos según la
Ley 20.840 (2015), con la actualización de la Ley 21.033 (2017) para la
Región de Ñuble. Art. 179 bis habilita una revisión de magnitudes cada 10
años en base al último censo — al cierre de este documento no hay una
actualización vigente que la reemplace.

**Procedimiento de construcción.**

1. **Tabla CUT.** Descargar el CSV/XLSX de División Político-Administrativa
   (DPA) desde el portal de datos abiertos o IDE Chile. Quedarse con
   `codigo_comuna`/`cut_comuna` (normalizado a string de 5 dígitos) y
   `nombre_comuna`. Resultado esperado: 346 filas.
2. **Mapeo comuna → distrito.** Leer el Art. 179 de la Ley 18.700 en la BCN
   y extraer, para cada uno de los 28 distritos, la lista de comunas que lo
   componen (ej. Distrito 1: Arica, Camarones, Putre, General Lagos).
3. **Cruce e indexación.** Normalizar nombres de comuna antes del *join*
   (sin tildes, capitalización homogénea) — hay variantes ortográficas
   conocidas que rompen un cruce ingenuo: `Aisén` vs `Aysén`, `Coyhaique`
   vs `Coihaique`, `Trehuaco` vs `Treguaco`, `La Calera` vs `Calera`. Cruzar
   por nombre normalizado contra la lista comunal de cada distrito y
   validar que las 346 comunas queden con un distrito entero en `[1, 28]`.
4. **Serialización.** Volcar el dict `{cut_5_digitos: distrito}` a JSON
   UTF-8 como `datos/asignacion_vigente.json`.

**Validación rápida** (repetir tras cualquier regeneración manual):

```python
import json
with open("datos/asignacion_vigente.json", encoding="utf-8") as f:
    asignacion = json.load(f)

assert len(asignacion) == 346, "deben quedar las 346 comunas vigentes"
assert all(len(k) == 5 and k.isdigit() for k in asignacion), "CUT debe ser string de 5 dígitos"
assert all(isinstance(v, int) and 1 <= v <= 28 for v in asignacion.values()), "distrito debe ser int en [1, 28]"
assert set(asignacion.values()) == set(range(1, 29)), "los 28 distritos deben estar representados"
```

**Quién lo consume.**

```bash
python scripts/malapportionment.py \
    --census-path     datos/poblacion_comunal_censo2024.csv \
    --assignment-path datos/asignacion_vigente.json

python scripts/electoral_analysis.py \
    --servel-path     datos/servel_2021_por_cut.csv \
    --assignment-path datos/asignacion_vigente.json \
    --census-path     datos/poblacion_comunal_censo2024.csv
```

`_load_assignment()` en ambos scripts normaliza claves a `str` y valores a
`int` al cargar, así que tolera un JSON con claves numéricas o valores en
string — pero el esquema canónico de este archivo es el de arriba (claves
string de 5 dígitos, valores int).

**Referencias legales.** Ley N° 20.840 (2015); DFL N° 2 de 2017 (texto
refundido de la Ley N° 18.700 Orgánica Constitucional sobre Votaciones
Populares y Escrutinios); Ley N° 21.033 (2017, ajuste Región de Ñuble) —
todas en BCN. Sistema Único de Codificación DPA — SUBDERE, Decreto Exento
N° 817.

---

### `datos/pacto_map_2025.json` — mapa partido → pacto electoral

Igual que `asignacion_vigente.json`, este archivo **no lo genera ningún script de chiledist** — es un insumo curado manualmente a partir de resoluciones oficiales SERVEL, documentado aquí para que sea reproducible.

**Qué es.** El mapa partido político → pacto electoral (coalición) de la elección de referencia (2025), que habilita el D'Hondt **binivel** real del sistema chileno: primero se asignan escaños entre pactos sobre sus votos totales de lista, luego dentro de cada pacto se asignan a los partidos/candidatos según orden de mayor votación. Sin este mapa, `cd.dhondt_binivel()` no puede agrupar los votos por partido en listas de pacto, y `scripts/malapportionment.py` (A4) / `scripts/electoral_analysis.py` (B1-B4) caen al D'Hondt uninivel (avisan por consola y omiten los bloques binivel).

**Esquema.**

```json
{
  "UDI": "Chile Grande y Unido",
  "Unión Demócrata Independiente": "Chile Grande y Unido",
  "PS": "Unidad por Chile",
  "Partido Socialista de Chile": "Unidad por Chile",
  "REP": "Cambio por Chile",
  "Partido Republicano de Chile": "Cambio por Chile",
  "IND": "Independientes Fuera de Pacto"
}
```

- Clave: nombre de partido — **tanto la sigla oficial como el nombre completo** aparecen como entradas separadas apuntando al mismo pacto, para tolerar cualquiera de los dos formatos que traigan los datos SERVEL de origen.
- Valor: nombre del pacto/coalición. Un partido que compite en lista propia sin pacto usa su propio nombre como valor; una candidatura sin cupo partidario usa `"Independientes Fuera de Pacto"`.
- 61 entradas en el archivo actual (partidos × 2 formas de nombre, aproximadamente).
- Codificación UTF-8.

**Fuentes primarias.**

| Fuente | Provee | Enlace |
|--------|--------|--------|
| SERVEL — Resultados electorales | Nombre de lista/pacto, partido/sigla y tipo de candidatura por registro | [servel.cl/resultados-elecciones](https://www.servel.cl/resultados-elecciones/) · [elecciones.servel.cl](https://elecciones.servel.cl/) |
| SERVEL — Resoluciones de formalización de pactos y declaración de candidaturas | Asociación oficial partido → pacto (Ley 18.700) | [servel.cl/category/elecciones-2025](https://www.servel.cl/category/elecciones-2025/) |

**Procedimiento de construcción.**

1. **Descarga.** Descargar del portal de resultados SERVEL la base de la elección de referencia (Diputados/Senadores) a nivel de candidatos o mesas, y quedarse con las columnas de lista/pacto, partido/sigla y tipo de candidatura (`Pacto`, `Partido`, `Independiente fuera de pacto`).
2. **Limpieza y normalización.** Extraer los valores únicos de partido. Disociar candidaturas independientes declaradas en cupo de partido (`IND - UDI` → partido declarante `UDI`). Crear entradas tanto para la sigla oficial como para el nombre completo del partido, para que el mapa funcione sin importar el formato de la fuente.
3. **Asignación partido → pacto.** Según las resoluciones de formalización SERVEL: si el partido pertenece a un pacto inscrito, el valor es el nombre del pacto; si compite en lista propia sin pacto, el valor es el propio nombre del partido; candidaturas sin cupo partidario van a `"Independientes Fuera de Pacto"`.
4. **Serialización.** Volcar el dict `{partido: pacto}` a JSON UTF-8 como `datos/pacto_map_2025.json`, validando la sintaxis antes de guardar.

**Validación rápida** (repetir tras cualquier regeneración manual):

```python
import json
with open("datos/pacto_map_2025.json", encoding="utf-8") as f:
    pacto_map = json.load(f)

assert len(pacto_map) > 0
assert all(isinstance(k, str) and isinstance(v, str) for k, v in pacto_map.items())
```

**Quién lo consume.**

```bash
python scripts/malapportionment.py \
    --census-path     datos/poblacion_comunal_censo2024.csv \
    --assignment-path datos/asignacion_vigente.json \
    --servel-path     datos/servel_2025_por_cut.csv \
    --pacto-path      datos/pacto_map_2025.json

python scripts/electoral_analysis.py \
    --servel-path     datos/servel_2025_por_cut.csv \
    --assignment-path datos/asignacion_vigente.json \
    --census-path     datos/poblacion_comunal_censo2024.csv \
    --pacto-path      datos/pacto_map_2025.json
```

`_load_pacto_map()` en ambos scripts retorna `None` si `--pacto-path` no se pasa o si la carga falla (avisando por consola), en cuyo caso los análisis siguen corriendo pero solo con D'Hondt uninivel — no es un error fatal, es un degradado explícito.

**Referencias.** Servicio Electoral de Chile (SERVEL): resoluciones sobre formalización de pactos y declaraciones de candidaturas para las Elecciones Generales (Ley N° 18.700 Orgánica Constitucional sobre Votaciones Populares y Escrutinios); base de datos de resultados electorales y registro de partidos políticos constituidos.

---

### `TRICEL_2025/` — proclamaciones oficiales del Tribunal Calificador de Elecciones

A diferencia de los archivos anteriores, este no es un único archivo curado sino un **directorio de 28 archivos** descargados directamente de la fuente oficial, uno por distrito.

**Qué es.** Las proclamaciones oficiales de Diputados 2025 del Tribunal Calificador de Elecciones (TRICEL) — la fuente de verdad contra la que se valida que `chiledist.engines.allocation.dhondt.dhondt_binivel()` reproduce el resultado real. Se usa para validación (`scripts/validar_tricel.py`), no como insumo de los análisis H1-H9.

- **Fuente**: [tribunalcalificador.cl/resultados_de_elecciones](https://tribunalcalificador.cl/resultados_de_elecciones/)
- **Archivos**: `Distrito-01.xlsx` a `Distrito-28.xlsx` (28 archivos; nótese el guion y capitalización título — no `DISTRITO-XX.xlsx`), cada uno con las hojas ELECTOS (proclamaciones) y MESA A MESA (votación).
- **Convención de directorio**: `$CHILEDIST_DATA_DIR/TRICEL_2025/` — la variable de entorno `CHILEDIST_DATA_DIR` se exporta automáticamente al pasar `--data-dir` a `scripts/validar_tricel.py` (ver `.env.example`).
- **Loaders**:
  ```python
  from chiledist.domain.data.tricel import import_proclamations, import_votes

  proclamaciones = import_proclamations(data_dir)  # hoja ELECTOS: candidato → escaño proclamado
  votos          = import_votes(data_dir)          # hoja MESA A MESA: votación por candidato/mesa
  ```
- **Estado de la validación**: 24/28 distritos coinciden exactamente contra el D'Hondt binivel calculado por chiledist (`PARTIAL`, no `EXACT_REPRODUCTION` — los 4 distritos restantes se explican por cobertura incompleta del SERVEL preliminar, no por un bug del cálculo). Ver "Validación electoral" más abajo y `VALIDATION_REPORT.md` para el detalle completo, incluidas las causas distrito por distrito.

---

### Datos externos — resumen y scripts de generación

chiledist requiere 6 archivos de datos externos. Cuatro se generan con los scripts en `datos/scripts_extra/`; los dos `.json` (`asignacion_vigente.json`, `pacto_map_2025.json`, documentados en detalle arriba en esta misma sección) son de construcción manual. Ninguno de estos scripts se distribuye como parte instalable de la librería — son utilitarios de una sola vez para transformar fuentes externas (Censo 2024, SERVEL, Ley 20.840) al formato que consume chiledist.

#### `datos/poblacion_comunal_censo2024.csv`

- **Script**: `datos/scripts_extra/run.py`
- **Entrada**: `personas_censo2024.csv` (microdatos Censo 2024 INE, separador `;`, columna `comuna` = CUT numérico) — no se distribuye, descargar de [ine.gob.cl](https://www.ine.gob.cl) (Censo 2024, base de personas)
- **Salida**: `CUT, personas`
- **Lógica**: `groupby("comuna").size()` — conteo de personas por CUT

#### `datos/servel_2025_por_cut.csv`

- **Script**: `datos/scripts_extra/procesar_servel_cut.py`
- **Entrada**: los 28 `PRELIMINARES_DIPUTADOS_DISTRITO_N.xlsx` (sección "Resultados Electorales" → Elecciones Parlamentarias 2025, SERVEL). Cada archivo tiene una fila por mesa con columnas `region, distrito, comuna, pacto, subpacto, partido, cod_candidato, nombre_candidato, votos_preliminares, electo_nominado`.
- **Salida**: `CUT, partido, votos`
- **Lógica**: agrega `votos_preliminares` por (CUT, partido), usando un diccionario `MAPA_COMUNA_CUT` hardcodeado en el script para el mapeo nombre de comuna → CUT
- **Limitación conocida**: las filas administrativas de cada mesa sin partido (`Votos Nulos`, `Votos en Blanco`, `Total Sufragios Validamente Emitidos`, `Total Suma Calculada` — `partido` viene `NaN` en el Excel) se agrupan como `"IND"` vía `.fillna("IND")`, inflando artificialmente el cociente D'Hondt de independientes (verificado: para Distrito 1, IND=313.938 = exactamente la suma de esas 4 filas administrativas, no votos de candidatos independientes reales). **Usar `servel_2025_candidatos.csv` para análisis electorales** — este archivo sirve solo para exploración y autocorrelación espacial.
- El bloque `__main__` del script también procesa `PRELIMINARES_SENADORES_CIRCUNSCRIPCI*.xlsx`: si esos 7 archivos no están en el directorio de trabajo, el script falla con `FileNotFoundError` antes de terminar — hay que tenerlos presentes, o comentar esa segunda llamada.

#### `datos/servel_2025_candidatos.csv`

- **Script**: `datos/scripts_extra/escanos.py`
- **Entrada**: los 28 `PRELIMINARES_DIPUTADOS_DISTRITO_N.xlsx` + `cd.load_layer("comunal")` para el mapeo nombre de comuna → CUT
- **Salida**: `CUT, cod_candidato, nombre_candidato, partido, pacto, votos`
- **Lógica**: votos por candidato individual por CUT (no agregado por partido) — cada candidato independiente es su propia entidad, reproduciendo el sistema real chileno en vez de la bolsa "IND" de `servel_2025_por_cut.csv`
- **Cobertura**: 13.410 filas, 1.096 candidatos, 345/345 CUT (excluye Antártica, CUT 12202, sin polígono en APC2023)
- **Uso**: `scripts/validar_dhondt.py --modo candidatos`

#### `datos/escanos_oficiales_2025.csv`

- **Script**: `datos/scripts_extra/escanos.py` (mismo script que el anterior — genera ambos archivos)
- **Entrada**: los 28 `PRELIMINARES_DIPUTADOS_DISTRITO_N.xlsx`
- **Salida**: `distrito, pacto, escanos`
- **Lógica**: candidatos con `electo_nominado==1`, agrupados por (distrito, pacto)
- **Validado**: Σ==155, magnitudes por distrito correctas (`MAGNITUDES_LEGALES_LEY20840`)
- **Uso**: referencia oficial para `scripts/validar_dhondt.py`

#### Aliases de nombres de comunas

`escanos.py` normaliza las siguientes variantes ortográficas entre el Excel de SERVEL y la cartografía APC2023:

| Excel SERVEL | APC2023 | CUT |
|---|---|---|
| MARCHIGUE | MARCHIHUE | 6204 |
| TREHUACO | TREGUACO | 16207 |
| PAIHUANO | PAIGUANO | 4105 |
| LLAY-LLAY | LLAILLAY | 5703 |
| CABO DE HORNOS(EX-NAVARINO) | CABO DE HORNOS | 12201 |

#### `datos/asignacion_vigente.json` y `datos/pacto_map_2025.json`

Sin script de generación automática — construcción manual, documentada en detalle más arriba en esta misma sección (`## Datos externos`). Resumen:

- **`asignacion_vigente.json`**: desde el texto de la Ley 20.840 ([bcn.cl/2f773](https://bcn.cl/2f773)). `{"CUT_str": n_distrito_int}`, 346 comunas → 28 circunscripciones (1-28). Ver `chiledist.domain.data.REGIONES_APC` para el mapeo de regiones.
- **`pacto_map_2025.json`**: desde resultados SERVEL 2025. `{"nombre_partido": "nombre_pacto"}`, en formato título con tildes (`"Evolución Política"`) — `chiledist.normalize_party_name()` normaliza automáticamente al hacer lookups, así que el mismatch de formato con SERVEL (MAYÚSCULAS sin tildes) no afecta los resultados.

#### Ejecución de los scripts

Desde el directorio que contiene los Excel de SERVEL:

```bash
# Población Censo 2024
python datos/scripts_extra/run.py
cp poblacion_comunas_censo2024.csv datos/poblacion_comunal_censo2024.csv

# Votos por candidato + escaños oficiales (genera ambos archivos)
python datos/scripts_extra/escanos.py
cp escanos_oficiales_2025.csv datos/escanos_oficiales_2025.csv
cp servel_2025_candidatos.csv datos/servel_2025_candidatos.csv

# Votos por CUT y partido (formato alternativo, solo exploración)
python datos/scripts_extra/procesar_servel_cut.py
cp servel_2025_diputados_por_cut.csv datos/servel_2025_por_cut.csv
```

Los Excel de SERVEL (`PRELIMINARES_DIPUTADOS_DISTRITO_N.xlsx`) y el CSV de microdatos del Censo 2024 no se distribuyen con la librería y deben obtenerse directamente de las fuentes.

⚠ Los datos electorales son `votos_preliminares` (conteo nocturno), no el escrutinio general final. En cocientes D'Hondt ajustados esto puede producir diferencias de 1 escaño respecto al resultado oficial — documentado en `SCIENTIFIC_HYPOTHESES.md` § H4.

---

## Validación electoral

`chiledist.validation` no es una de las 5 capas del paquete — es un consumidor terminal que compara la salida del motor D'Hondt (capa `engines`) contra la fuente oficial de verdad (TRICEL, capa `domain`), sin reimplementar ninguna regla de asignación de escaños.

```python
from chiledist.validation import validate_election, ValidationReport
from chiledist.domain.data.tricel import import_proclamations, import_votes

proclamaciones = import_proclamations(data_dir)
votos_tricel   = import_votes(data_dir)

report: ValidationReport = validate_election(
    candidates_servel=candidates_servel,      # datos/servel_2025_candidatos.csv
    proclamations_tricel=proclamaciones,
    assignment=asignacion_vigente,            # datos/asignacion_vigente.json
    magnitudes=MAGNITUDES_LEGALES_LEY20840,
    pacto_map=pacto_map,                      # datos/pacto_map_2025.json
    votes_tricel=votos_tricel,
)
print(report)  # Districts validated: 24/28, Status: PARTIAL
```

**Pipeline** (ver docstring de `validate_election()` para el detalle completo): corre `dhondt_binivel()` sobre los votos SERVEL agregados por partido y distrito, determina los candidatos ganadores dentro de cada partido por mayor votación individual (regla real, Ley 18.700 — no un segundo D'Hondt intra-partido), compara escaños calculados vs. proclamados TRICEL por (distrito, pacto) y por candidato, y reporta discrepancias y empates que requieren resolución legal.

**Estado actual: `PARTIAL` — 24/28 distritos validados** exactamente contra las proclamaciones oficiales TRICEL 2025 (141/155 escaños, 181/185 asignaciones de lista). Los 4 distritos restantes (D3, D5, D8, D19) muestran únicamente discrepancias "proclamado pero no calculado" — no hay ningún falso positivo — y se explican por cobertura incompleta del SERVEL preliminar (38.8%-86% del escrutinio final certificado por TRICEL, según distrito), no por un error del motor D'Hondt. Ver `VALIDATION_REPORT.md` para el historial completo de la validación, las causas distrito por distrito y el camino hacia `EXACT_REPRODUCTION`.

```bash
python scripts/validar_tricel.py \
    --data-dir "$CHILEDIST_DATA_DIR" \
    --servel-candidates datos/servel_2025_candidatos.csv \
    --pacto-map datos/pacto_map_2025.json \
    --assignment datos/asignacion_vigente.json
```

---

## Scripts de análisis

### 1. setup.py — Inicialización

Genera los datos base necesarios para todos los análisis posteriores.

```bash
# Inicialización completa
python scripts/setup.py --base-dir ./SHP_APC2023

# Sin figuras (más rápido)
python scripts/setup.py --base-dir ./SHP_APC2023 --skip-viz

# Sin manzanas (no agrega población)
python scripts/setup.py --base-dir ./SHP_APC2023 --skip-manzanas
```

**Salidas en `datos/nacional/`:**

```
matrices/
    matriz_distrital_matriz.npz     # Matriz sparse 2.768×2.768
    matriz_distrital_indice.csv     # Mapeo fila ↔ ID_DIST
    matriz_distrital_islas.csv      # Conexiones artificiales de islas (distrital)
    matriz_comunal_matriz.npz       # Matriz sparse 345×345
    matriz_comunal_indice.csv
    matriz_comunal_islas.csv        # Conexiones artificiales de islas (comunal)
    poblacion_distritos.csv
    compacidad_distritos.csv
    resumen_regional.csv
    chiledist_redist.rds            # Datos exportados para R/redist (RDS, no un script)
figuras/
    equivalencia_usa_chile.png
    grafo_adyacencia_distrital.png
    grafo_adyacencia_comunal.png
    compacidad_distrital.png
    mapa_distritos_tipo.png
```

---

### 2. redistritaje.py — Redistritaje ReCom

Genera ensembles de redistritaje usando ReCom. Soporta **tres escenarios** electorales y **cuatro fuentes de población**.

#### Escenarios disponibles

| `--scenario` | Unidad mínima | Preservación comunas | Naturaleza | Descripción |
|--------------|---------------|----------------------|------------|-------------|
| `legal` | `CUT` (comuna) | Dura | Contrafactual legal | Explora redistritajes que respetan la Ley 18.700 |
| `apc_free` | `ID_DIST` (APC) | Ninguna | **Contrafactual científico** | Mide el costo de la restricción comunal |
| `apc_soft` | `ID_DIST` (APC) | Blanda (penalización) | **Contrafactual científico** | APC con penalización configurable por splits |

También se pueden cargar escenarios personalizados desde YAML con `--scenario-file`.

#### Modos de región

| `--regiones` | Descripción |
|--------------|-------------|
| `13` | Región específica |
| `5,8,13` | Lista de regiones (separadas por coma) |
| `todas` | Las 16 regiones en secuencia |
| `nacional` | APC nacional directo (~2.768 nodos, lento) |
| `nacional_comunal` | 345 comunas — contrafactual con restricción comunal |

```bash
# Modo legal (comunas indivisibles, Ley 18.700)
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 --scenario legal

# APC libre
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 --scenario apc_free

# APC con penalización de splits
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 --scenario apc_soft

# Escenario personalizado desde YAML
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 \
    --scenario-file scenarios/mi_escenario.yml

# Con población real del Censo 2024 (Base manzana — join exacto por distrito)
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 \
    --scenario legal \
    --pop-source manzana \
    --census-path datos/Base_manzana_entidad_CPV24.csv

# Con tabla comunal del Censo 2024 (distribución proporcional)
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 \
    --pop-source censo2024 --census-path datos/censo2024_comunas.csv

# Con padrón electoral SERVEL
python scripts/redistritaje.py --base-dir ./SHP_APC2023 --regiones 13 \
    --pop-source padron --padron-path datos/padron_2024.csv
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--regiones` | `13` | Región(es) a analizar |
| `--scenario` | — | Escenario predefinido: `legal`, `apc_free`, `apc_soft` |
| `--scenario-file` | — | Ruta a YAML de escenario personalizado |
| `--decision-unit` | — | Override: `CUT` o `ID_DIST` |
| `--preserve-mode` | — | Override: `hard`, `soft`, `none` |
| `--preserve-units` | — | Columnas a preservar, separadas por coma (override manual, ej. `CUT`) |
| `--split-penalty` | `0.25` | Peso de penalización en modo `soft` |
| `--pop-source` | `viviendas` | Fuente de población: `viviendas`, `manzana`, `censo2024`, `padron` |
| `--census-path` | — | CSV del Censo 2024 (para `manzana` o `censo2024`) |
| `--padron-path` | — | CSV del padrón SERVEL (para `padron`) |
| `--n-distritos` | _(del escenario)_ | Número de particiones territoriales a generar; default = `n_districts` del escenario (`ScenarioConfig.n_districts`, típicamente 8). **No** es la magnitud electoral (escaños por distrito, Ley 20.840 — ver `MAGNITUDES_LEGALES_LEY20840`), que es un concepto separado y no relacionado. |
| `--pop-tol` | _(del escenario)_ | Tolerancia poblacional; default = `pop_tolerance` del escenario (0.05). Usar `0.15` para regiones pequeñas. |
| `--n-steps` | `10000` | Pasos de la cadena ReCom |
| `--seed` | `42` | Semilla aleatoria |
| `--skip-viz` | — | Omitir figuras |

**Salidas en `datos/{REGION}/redistritaje/{SCENARIO}/`:**

```
ensemble_stats.csv             # Distribución completa del ensemble — resultado principal
plan_referencia_detalle.csv    # Detalle por distrito del plan de referencia (visualización)
comunas_partidas.csv           # Comunas partidas en el plan de referencia (modos APC)
metricas_cadena.csv            # Métricas paso a paso de la cadena
ref_vs_extremo.png             # Plan de referencia vs plan de menor score
cadena_markov.png
ensemble_distribucion.png
ref_balance.png
compacidad.png
```

#### Estados posibles en el resumen final

| `status` | `reason` | Significado |
|----------|----------|-------------|
| `ok` | — | Análisis completado correctamente |
| `sin_poblacion` | — | La región no tiene datos de viviendas |
| `sin_gerrychain` | — | `gerrychain` no está instalado; el redistritaje se omite |
| `infeasible_population` | `indivisible_unit_exceeds_population_bound` | **Prueba matemática de inviabilidad**, calculada por el preflight de factibilidad poblacional *antes* de intentar `recursive_tree_part`: alguna unidad de decisión indivisible (una CUT en modo legal, un ID_DIST en modos APC) por sí sola excede `pop_tolerance` respecto del ideal por distrito. Ningún número de semillas, intentos ni tolerancias de inicialización puede resolverlo — hay que cambiar `n_distritos`, `pop_tolerance` o la unidad de decisión (`decision_unit`). |
| `sin_particion` | `initialization_search_exhausted` | El preflight de factibilidad poblacional **no** demostró inviabilidad, pero `recursive_tree_part` agotó su escalera de tolerancias `[0.25, 0.35, 0.45, 0.60, 0.80]` y sus semillas sin producir una partición inicial. Esto es un fallo del algoritmo de búsqueda/inicialización (topología del grafo, spanning trees desbalanceados, etc.) — **no** es una prueba de que el espacio de planes sea matemáticamente vacío. |
| `sin_planes` | — | La cadena fue interrumpida antes de generar planes |
| `sin_planes_validos` | — | La cadena corrió pero ningún plan cumple la tolerancia |
| `error` | — | Error inesperado (ver traceback) |

`infeasible_population` y `sin_particion` se distinguen deliberadamente: el primero es una demostración cerrada (recalculable con `chiledist.check_population_feasibility`), el segundo es evidencia de que la búsqueda falló sin cerrar la pregunta. El resumen CSV (`redistritaje_resumen_*.csv`) incluye la columna `reason` para poder filtrar ambos casos por separado aguas abajo.

#### Comportamiento para regiones problemáticas

Varias regiones tienen características geográficas que dificultan el redistritaje:

- **Regiones pequeñas** (R01, R11, R15): pocos distritos APC. El script ajusta automáticamente `n_distritos = min(pedido, n_dist_apc // 4)`.
- **Regiones insulares** (R10 Los Lagos, R11 Aysén, R12 Magallanes): muchas islas y componentes desconectados. El script conecta automáticamente las islas en el grafo gerrychain por distancia de centroides.
- **`Failed to find a balanced cut`**: warning de gerrychain cuando el spanning tree es demasiado pequeño. El script habilita `pair_reselection=True` automáticamente si está disponible en la versión instalada, y aumenta `node_repeats` para regiones pequeñas.

Si una región retorna `sin_particion` (búsqueda agotada, no inviabilidad demostrada), una solución habitual es pedir menos grupos, lo que reduce cuánto debe balancearse cada partición candidata:

```bash
python scripts/redistritaje.py --base-dir ./SHP_APC2023 \
    --regiones 15 --n-distritos 3   # Arica: 4 comunas → 3 grupos
python scripts/redistritaje.py --base-dir ./SHP_APC2023 \
    --regiones 11 --n-distritos 4   # Aysén: 10 comunas → 4 grupos
```

---

### 3. compare_scenarios.py — Comparación de escenarios

Corre los tres escenarios predefinidos sobre la misma región y produce una comparación formal con tabla de métricas, rankings y visualizaciones.

```bash
# Comparar los tres escenarios en la Región Metropolitana
python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 13

# Varias regiones
python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 5,13

# Solo comparar resultados ya existentes (sin re-ejecutar redistritaje)
python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 13 --skip-run

# Escenarios personalizados desde YAML
python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 13 \
    --scenario-files scenarios/A.yml,scenarios/B.yml

# Con parámetros
python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 13 \
    --n-distritos 8 --n-steps 5000 --seed 42
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--regiones` | `13` | Región(es): número, lista o `todas` |
| `--scenarios` | `legal,apc_free,apc_soft` | Escenarios a comparar |
| `--scenario-files` | — | Rutas YAML separadas por coma (override `--scenarios`) |
| `--n-distritos` | _(del escenario)_ | Número de particiones territoriales a generar (NO la magnitud electoral Ley 20.840). Default: cada escenario conserva su propio `n_districts`; si se pasa explícito, se aplica a todos los escenarios comparados. |
| `--n-steps` | `10000` | Pasos de la cadena ReCom |
| `--skip-run` | — | Solo comparar resultados existentes, no re-ejecutar |
| `--skip-viz` | — | Omitir figuras |

**Salidas en `datos/{REGION}/comparacion/`:**

```
comparacion_escenarios.csv          # Tabla de métricas + deltas + ranking (solo escenarios con ensemble válido)
escenarios_overview.csv             # Una fila por escenario esperado, incluidos los sin ensemble válido
                                     # (status, reason, included_in_scoring — ver más abajo)
comparacion_status.json             # comparison_status (COMPLETE/INCOMPLETE), expected_scenarios,
                                     # valid_ensembles, missing_baseline, ranking_scope
comunas_partidas_frecuencia.csv     # Frecuencia de comunas partidas por escenario
tradeoff_balance_splits.png         # Gráfico balance vs comunas partidas
tradeoff_compacidad_splits.png      # Gráfico compacidad vs comunas partidas
boxplots_comparativos.png           # Distribuciones de métricas por escenario
```

Un escenario sin ensemble válido (`infeasible_population`, `sin_particion`, etc.) sigue visible en `escenarios_overview.csv` con su `status`/`reason` reales — nunca se le asigna score artificial ni entra al ranking de `comparacion_escenarios.csv`. Si falta un escenario esperado (típicamente el baseline `legal_comunas`), `comparacion_status.json` marca `comparison_status: "INCOMPLETE"` y `ranking_scope: "partial"`: el ranking entre los escenarios restantes puede calcularse, pero no debe leerse como una comparación H1 completa. `compare_and_export()` (en `scripts/compare_scenarios.py`) devuelve `{"ranking", "overview", "completeness"}` con esta misma información.

---

### 4. autocorrelacion.py — Autocorrelación espacial

Calcula I de Moran global, LISA, Getis-Ord G* y correlograma espacial.
Soporta los mismos **tres modos** que redistritaje.

#### Modos disponibles

| Modo `--regiones` | Opción | Unidad | Salida |
|-------------------|--------|--------|--------|
| `13` | B | APC región | `datos/R13_*/autocorrelacion/` |
| `todas` | B | APC por región | una carpeta por región |
| `nacional` | A | APC nacional ~2.768 nodos | `datos/nacional/autocorrelacion/` |
| `nacional_comunal` | C | Comunas ~345 nodos | `datos/nacional/autocorrelacion_comunal/` |

```bash
# Región específica
python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones 13

# Varias regiones (análisis separado por cada una)
python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones 5,8,13

# Todas las regiones por separado
python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones todas

# Chile completo a nivel APC (Opción A)
python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones nacional

# Chile completo a nivel comunal (Opción C)
python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones nacional_comunal

# Variables y parámetros personalizados
python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones nacional \
    --variables viviendas,densidad_viv_km2,polsby_popper \
    --max-order 7 --permutaciones 999
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--regiones` | `13` | Región(es): número, lista, `todas`, `nacional`, `nacional_comunal` |
| `--variables` | `viviendas,densidad_viv_km2,polsby_popper` | Variables a analizar |
| `--max-order` | `7` | Orden máximo del correlograma |
| `--permutaciones` | `999` | Permutaciones para inferencia |
| `--skip-viz` | — | Omitir figuras |

**Salidas por ejecución:**

```
moran_scatter.png           # Diagramas de dispersión de Moran por variable
lisa_mapas.png              # Mapas LISA (HH/LL/LH/HL) con leyenda
getisord_mapas.png          # Hotspots/coldspots G* + zoom automático
correlograma.png            # Decaimiento I de Moran por orden de vecindad
resultados.csv              # Índices LISA y G* por unidad
moran_global.csv            # Resumen I de Moran global por variable
```

**Requiere:** `pip install esda`

---

### 5. export_imc_bundle.py — Bundle IMC Plan Lab

Exporta un bundle geoespacial compatible con herramientas de redistritaje interactivo.

```bash
# Bundle distrital nacional
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level distrital

# Bundle comunal nacional
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level comunal

# Solo una región
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \
    --level distrital --regiones 13

# Varias regiones
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \
    --level distrital --regiones 5,8,13

# Sin compacidad (más rápido)
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \
    --level comunal --no-compacidad

# Directorio de salida personalizado
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \
    --level distrital --output-dir ./bundles

# Sin población ni README, sin conectar islas
python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \
    --level distrital --no-poblacion --no-readme --no-connect-islands
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--level` | `distrital` | `comunal` o `distrital` |
| `--regiones` | _(nacional)_ | Número, lista (`5,8,13`) o vacío/`nacional`/`todas` para el país completo |
| `--output-dir` | `.` | Directorio donde se crea la carpeta del bundle |
| `--no-compacidad` | — | Omitir cálculo de métricas de compacidad (más rápido) |
| `--no-poblacion` | — | Omitir agregación de población desde manzanas |
| `--no-readme` | — | Omitir generación de `README.md` del bundle |
| `--connect-islands` / `--no-connect-islands` | `--connect-islands` | Conectar islas sin vecinos al vecino más cercano |

**Salidas en `imc_bundle_{level}_{scope}/`:**

```
units.geojson       # Geometrías + atributos en EPSG:4326
adjacency.json      # Lista de pares adyacentes (imc-adjacency-v1)
metadata.json       # Metadatos del bundle (imc-planlab-bundle-v1)
README.md           # Documentación del bundle
```

**Campos en `units.geojson`:**

```json
{
  "unit_id":          "13101_021",
  "level":            "distrital",
  "name":             "BARRIO INDUSTRIAL",
  "region_id":        "13",
  "region_name":      "REGIÓN METROPOLITANA DE SANTIAGO",
  "ID_DIST":          "13101_021",
  "CUT":              "13101",
  "N_COMUNA":         "SANTIAGO",
  "viviendas":        1250,
  "population":       1250,
  "polsby_popper":    0.612,
  "compactness_mean": 0.587
}
```

**Formato `adjacency.json`:**

```json
{
  "format":        "imc-adjacency-v1",
  "directed":      false,
  "unit_id_field": "unit_id",
  "edges": [["13101_021", "13101_022"], ["13101_021", "13102_005"]]
}
```

El script valida antes de exportar: `unit_id` sin nulos ni duplicados, geometrías en EPSG:4326, edges sin self-loops ni duplicados, todos los IDs en edges presentes en units.

---

### 6. pareto_sweep.py — H2: Frontera de Pareto

Barre valores de `split_penalty` para la frontera Pareto entre balance poblacional y fragmentación comunal.

```bash
# Barrido estándar para la RM con 6 valores de penalty
python scripts/pareto_sweep.py --base-dir ./SHP_APC2023 --regiones 13

# Rango y resolución personalizados
python scripts/pareto_sweep.py --base-dir ./SHP_APC2023 --regiones 13 \
    --penalties 0.0,0.1,0.2,0.5,1.0,2.0

# Con población real del Censo 2024 (en vez del default --pop-source viviendas)
python scripts/pareto_sweep.py --base-dir ./SHP_APC2023 --output-dir ./datos --regiones 13 \
    --penalties 0.0,0.25,0.5,1.0,2.5,5.0,10.0,25.0 \
    --pop-source censo2024 --census-path datos/poblacion_comunal_censo2024.csv \
    --pop-tol 0.10 --n-steps 10000 --seed 42

# Solo calcular (sin re-ejecutar redistritaje; lee ensemble_stats.csv ya existentes)
python scripts/pareto_sweep.py --base-dir ./SHP_APC2023 --regiones 13 --skip-run

# Sin figuras
python scripts/pareto_sweep.py --base-dir ./SHP_APC2023 --regiones 13 --skip-viz
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--regiones` | `13` | Región(es) a analizar, separadas por coma, o `todas` |
| `--region` | — | _(Obsoleto, usar `--regiones`)_ Alias de compatibilidad para un único código de región |
| `--penalties` | `0.0,0.1,0.25,0.5,1.0,2.0` | Valores de `split_penalty` (coma-separados) |
| `--n-distritos` | _(del escenario)_ | Número de particiones territoriales a generar (NO la magnitud electoral Ley 20.840). Default: cada anclaje/variante del barrido conserva su propio `n_districts`; no se homogeneiza salvo override explícito. |
| `--pop-tol` | `0.15` | Tolerancia poblacional aplicada a todas las configuraciones del barrido |
| `--n-steps` | `5000` | Pasos de la cadena por escenario |
| `--seed` | `42` | Semilla aleatoria |
| `--pop-source` | `viviendas` | Fuente de población: `viviendas`, `manzana`, `censo2024`, `padron`. **`padron` no es utilizable aquí**: requiere `--padron-path`, que este script no expone (a diferencia de `redistritaje.py`) — usarlo aborta con error. |
| `--census-path` | — | CSV del Censo 2024 (para `censo2024`; también usado por `manzana`, ver limitación de `padron` arriba) |
| `--no-anchors` | — | Omite los anclajes `legal`/`apc_strict`/`apc_free`, deja solo el barrido continuo de `apc_soft` |
| `--skip-run` | — | Solo leer CSVs existentes (no re-ejecuta `analizar_region()`; falla por configuración si falta su `ensemble_stats.csv`) |
| `--skip-viz` | — | Omitir figuras |

> `--output-dir` (default: `<base-dir>/datos`) determina dónde se leen/escriben los ensembles y el barrido — si se usa un `--base-dir` distinto de `.` (p. ej. `./SHP_APC2023`), pasar `--output-dir ./datos` explícitamente para que la salida quede junto al resto de `datos/`, en vez de anidada bajo `--base-dir`.

**Salidas en `<output-dir>/{REGION}/pareto_sweep/`:**

```
pareto_sweep_results.csv   # tabla completa: todas las configuraciones + is_pareto
pareto_frontier.csv        # solo las configuraciones Pareto-óptimas
pareto_tradeoff.png        # scatter + frontera Pareto + anclajes
pareto_pop_afectada.png    # balance vs pop_afectada_pct, si está disponible (≥2 puntos válidos)
```

> Para variantes `apc_soft`, el campo `point_type="reference_plan"` indica que la métrica corresponde al plan seleccionado por el score (no la mediana del ensemble), ya que variaciones de `split_penalty` solo afectan la selección del plan de referencia, no la distribución de la cadena.

---

### 7. malapportionment.py — H3: Malapportionment

Cuatro análisis sobre el mapa distrital **vigente** (28 circunscripciones, Ley 20.840): A1 personas por escaño y peso relativo del voto, A2 magnitudes vigentes vs. proporcionales al Censo 2024, A3 umbral efectivo por circunscripción, A4 métricas electorales fijas vs. calculadas (requiere SERVEL). No opera sobre los escenarios/ensembles de `redistritaje.py` — usa el mapa real, no simulaciones.

```bash
# Datos reales (ver "Datos externos" más arriba para asignacion_vigente.json)
python scripts/malapportionment.py \
    --census-path     datos/poblacion_comunal_censo2024.csv \
    --assignment-path datos/asignacion_vigente.json \
    --servel-path     datos/servel_2021_por_cut.csv

# Solo A1–A3 (sin métricas electorales)
python scripts/malapportionment.py \
    --census-path     datos/poblacion_comunal_censo2024.csv \
    --assignment-path datos/asignacion_vigente.json

# Demo con datos sintéticos (no requiere archivos externos)
python scripts/malapportionment.py --demo
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--census-path` | — | CSV Censo 2024: columnas `CUT`, `personas` |
| `--assignment-path` | — | JSON `{CUT_str: n_circunscripcion}` — asignación vigente (ver `datos/asignacion_vigente.json`) |
| `--servel-path` | — | CSV SERVEL 2021: columnas `CUT`, `partido`, `votos` [A4] |
| `--pacto-path` | — | JSON `{partido: pacto}` para D'Hondt binivel en A4 (opcional) |
| `--output-dir` | `datos/malapportionment` | Directorio de salida |
| `--base-dir` | `.` | Raíz del proyecto |
| `--demo` | — | Datos sintéticos para los cuatro análisis, sin archivos externos |
| `--skip-viz` | — | Omitir figuras |

Si falta algún archivo, el análisis correspondiente se omite con aviso (no aborta los demás).

**Salidas en `<output-dir>/malapportionment/`:**

```
malapportionment_pxe.csv          # A1: personas/escaño y peso relativo por circunscripción
malapportionment_comparacion.csv  # A2: magnitudes vigentes vs. proporcionales a Censo 2024
malapportionment_umbrales.csv     # A3: umbral efectivo por distrito
malapportionment_electoral.csv    # A4: métricas electorales, magnitudes fijas vs. calculadas
figuras/personas_por_escano.png
figuras/peso_relativo.png
figuras/comparacion_magnitudes.png
figuras/umbrales_efectivos.png
```

---

### 8. electoral_analysis.py — H4: Análisis D'Hondt binivel

¿Cómo cambia la proporcionalidad bajo el sistema chileno real (D'Hondt binivel: pactos compiten entre sí, partidos dentro de cada pacto) respecto al modelo uninivel? Cuatro bloques: B1 comparación uni/binivel en un distrito de ejemplo, B2 matriz 4-combinaciones (magnitudes fijas/calculadas × uni/binivel) sobre el mapa vigente completo, B3 distribución de Gallagher sobre un ensemble de planes (requiere `assignments.parquet` de `redistritaje.py`), B4 seat bonus por partido, detalle uni vs. binivel.

```bash
# Todos los datos reales, incluido el ensemble de un run de redistritaje.py (B3)
python scripts/electoral_analysis.py \
    --servel-path     datos/servel_2021_por_cut.csv \
    --assignment-path datos/asignacion_vigente.json \
    --census-path     datos/poblacion_comunal_censo2024.csv \
    --pacto-path      datos/pacto_map_2025.json \
    --run-dir         datos/R13_METROPOLITANA/redistritaje/legal_comunas

# Solo B1-B2 (sin ensemble, no requiere --run-dir)
python scripts/electoral_analysis.py \
    --servel-path datos/servel_2021_por_cut.csv \
    --assignment-path datos/asignacion_vigente.json \
    --census-path datos/poblacion_comunal_censo2024.csv \
    --pacto-path datos/pacto_map_2025.json

# Demo completo con datos sintéticos
python scripts/electoral_analysis.py --demo
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--servel-path` | — | CSV SERVEL 2021: columnas `CUT`, `partido`, `votos` |
| `--assignment-path` | — | JSON `{CUT_str: n_circunscripcion}` — mapa vigente (ver `datos/asignacion_vigente.json`) |
| `--census-path` | — | CSV Censo 2024: columnas `CUT`, `personas` (para población) |
| `--pacto-path` | — | JSON `{partido: pacto}`, para D'Hondt binivel |
| `--run-dir` | — | `run_dir` de `redistritaje.py` con `assignments.parquet` [solo B3] |
| `--n-ensemble` | `200` | Tamaño de muestra del ensemble para B3 |
| `--output-dir` | `datos/electoral_analysis` | Directorio de salida |
| `--base-dir` | `.` | Raíz del proyecto |
| `--demo` | — | Datos sintéticos para los cuatro bloques |
| `--skip-viz` | — | Omitir figuras |

**Salidas en `<output-dir>/electoral_analysis/`:**

```
electoral_b1_distrito.csv     # B1: uninivel vs binivel, distrito de ejemplo
electoral_b2_matrix.csv       # B2: 4 combinaciones, índices completos
electoral_b3_ensemble.csv     # B3: Gallagher / seat bonus por plan del ensemble
electoral_b4_bonus.csv        # B4: seat bonus por partido (uni y binivel)
figuras/b1_distrito_ejemplo.png
figuras/b2_combinaciones.png
figuras/b3_gallagher_ensemble.png
figuras/b4_seat_bonus.png
```

---

### 9. run_chains.py — H5: Multi-cadena ReCom

Corre N cadenas ReCom independientes con distintas semillas y calcula diagnósticos de convergencia (R-hat, ESS, mezcla).

```bash
# 4 cadenas con seeds 42, 43, 44, 45
python scripts/run_chains.py --base-dir ./SHP_APC2023 --regiones 13 \
    --scenario apc_soft --n-chains 4

# Con análisis de sensibilidad a pesos de scoring
python scripts/run_chains.py --base-dir ./SHP_APC2023 --regiones 13 \
    --scenario apc_soft --n-chains 4 --sensitivity

# Solo diagnosticar cadenas ya corridas (sin re-ejecutar)
python scripts/run_chains.py --base-dir ./SHP_APC2023 --regiones 13 \
    --scenario apc_soft --skip-run
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--regiones` | `13` | Región(es) a analizar (acepta varias, ej. `--regiones 13 5`) |
| `--scenario` | `apc_soft` | Nombre de escenario predefinido (`legal`, `apc_free`, `apc_soft`) |
| `--scenario-file` | — | Ruta a YAML de escenario personalizado (override `--scenario`) |
| `--n-distritos` | _(del escenario)_ | Número de particiones territoriales a generar (NO la magnitud electoral Ley 20.840). Default: `n_districts` del escenario cargado. |
| `--n-chains` | `4` | Número de cadenas independientes |
| `--base-seed` | `42` | Semilla base; cadena k usa `base_seed + k` |
| `--n-steps` | `5000` | Pasos por cadena |
| `--pop-tol` | `0.05` | Tolerancia poblacional ReCom |
| `--sensitivity` | — | Análisis de sensibilidad a pesos de scoring |
| `--skip-run` | — | Solo leer CSVs existentes |

No tiene `--skip-viz`: `run_chains.py` siempre genera sus figuras (trazas y evolución de R-hat).

**Salidas en `datos/{REGION}/chains/{SCENARIO}/`:**

```
seed_XXXX/metricas_cadena.csv       # métricas paso a paso por cadena
seed_XXXX/ensemble_stats.csv        # estadísticas del ensemble por cadena
convergencia_diagnosticos.csv       # R-hat, ESS, ACF-1 por métrica
trace_plot.png                      # trazas superpuestas de las N cadenas
gelman_rubin_evolution.png          # evolución del R-hat (solo si ≥ 2 cadenas)
sensibilidad_ks_cadenas.csv         # test KS entre cadenas, pesos default (--sensitivity)
sensibilidad_pesos.csv              # concordancia de rankings entre 4 configuraciones de pesos
sensibilidad_pesos.png              # τ de Kendall por par de configuraciones (--sensitivity)
```

---

### 10. smc_pipeline.py — H5: Bridge Python → R/redist

Genera el script R para muestreo SMC con `redist` (ALARM Harvard) y, una vez ejecutado en R, importa los resultados para compararlos con el ensemble ReCom.

```bash
# Paso 1: generar script R y GeoPackage para la RM (salida automática en
# datos/R13_METROPOLITANA/smc/, no hay --output-dir)
python scripts/smc_pipeline.py --base-dir ./SHP_APC2023 --regiones 13 --n-sims 500

# El script imprime el comando para ejecutar en R:
#   Rscript datos/R13_METROPOLITANA/smc/apc_soft_redist.R

# Paso 2 (después de correr el R): comparar SMC vs ReCom
python scripts/smc_pipeline.py --base-dir ./SHP_APC2023 --regiones 13 \
    --compare --plans-csv datos/R13_METROPOLITANA/smc/apc_soft_smc_planes.csv \
    --recom-ensemble datos/R13_METROPOLITANA/redistritaje/contrafactual_apc_soft/ensemble_stats.csv
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--regiones` | `13` | Región(es) a analizar (acepta varias) |
| `--scenario` | `apc_soft` | Nombre de escenario (usado como prefijo de archivos, no resuelve un YAML por sí solo salvo que coincida con `SCENARIOS` o `scenarios/<nombre>.yml`) |
| `--layer` | `distrital` | Capa APC a cargar (`distrital` o `apc`) |
| `--id-col` | `ID_DIST` | Columna de ID de unidad |
| `--pop-col` | `personas` | Columna de población |
| `--n-districts` | _(del escenario)_ | Número de particiones territoriales a generar (NO la magnitud electoral Ley 20.840). Default: `n_districts` del escenario resuelto desde `--scenario` (vía `SCENARIOS` o `scenarios/<nombre>.yml`); si no se puede resolver, se exige pasar `--n-districts` explícito. |
| `--n-sims` | `1000` | Simulaciones SMC en R |
| `--extra-cols` | — | Columnas adicionales a incluir en el GPKG (ej. `CUT N_COMUNA`) |
| `--compare` | — | Activar comparación SMC vs ReCom |
| `--plans-csv` | _(auto)_ | CSV de planes SMC generado por R (default: `<output_dir>/<scenario>_smc_planes.csv`) |
| `--recom-ensemble` | — | CSV del ensemble ReCom para comparar |

No tiene `--output-dir`: la salida siempre va a `datos/{REGION}/smc/` (vía `chiledist.domain.data.REGIONES_APC`, o `R{código}` si la región no está en el mapa de 16 regiones).

**Salidas en `datos/{REGION}/smc/`:**

```
<scenario>_units.gpkg          # Geometrías + población exportadas para R
<scenario>_redist.R            # Script R para redist_smc()
<scenario>_smc_planes.csv      # (tras correr el R)
<scenario>_smc_metricas.csv    # (tras correr el R)
smc_vs_recom_ks.csv            # test KS por métrica, SMC vs ReCom (--compare)
smc_vs_recom_ks.png            # visualización KS stats (--compare)
smc_vs_recom_ranking.csv       # concordancia de rankings, Kendall τ / Spearman ρ (--compare)
```

**Requiere:** R con paquete `redist` instalado. Ver instrucciones en https://alarm-redist.org.

---

### 11. validar_dhondt.py — H4: D'Hondt binivel vs SERVEL oficial

Valida que `dhondt_binivel()` reproduce los escaños oficiales SERVEL 2025 por distrito y pacto. Estado actual: **96/96 combinaciones (distrito, pacto), PASS completo**.

```bash
# Modo por_cut (default): agrega por CUT+partido, pacto vía pacto_map_2025.json
python scripts/validar_dhondt.py

# Modo candidatos: agrega por candidato real desde servel_2025_candidatos.csv
python scripts/validar_dhondt.py --modo candidatos \
    --votos-path datos/servel_2025_candidatos.csv
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--modo` | `por_cut` | `por_cut` agrega por CUT+partido (pacto vía `pacto_map_2025.json`); `candidatos` agrega por candidato real, con el pacto que ya trae cada candidato desde SERVEL |
| `--votos-path` | _(según `--modo`)_ | Default: `datos/servel_2025_por_cut.csv` (por_cut) o `datos/servel_2025_candidatos.csv` (candidatos) |

---

### 12. validar_tricel.py — Validación electoral completa vs TRICEL

Validación candidato a candidato: D'Hondt binivel chiledist vs proclamaciones oficiales TRICEL 2025, sobre los 28 distritos reales. Ver "Validación electoral" más arriba y `VALIDATION_REPORT.md` para el detalle completo. Estado actual: **24/28 distritos validados (`PARTIAL`)**.

```bash
python scripts/validar_tricel.py \
    --data-dir "$CHILEDIST_DATA_DIR" \
    --servel-candidates datos/servel_2025_candidatos.csv \
    --pacto-map datos/pacto_map_2025.json \
    --assignment datos/asignacion_vigente.json
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--data-dir` | _(requerido)_ | Directorio raíz con `SERVEL_2025/`, `TRICEL_2025/` y `SHP_APC2023_R*` (ver `.env.example`) |
| `--base-dir` | `./SHP_APC2023` | Carpeta con shapefiles APC |
| `--servel-candidates` | _(requerido)_ | CSV de candidatos SERVEL |
| `--pacto-map` | _(requerido)_ | JSON `{partido: pacto}` |
| `--assignment` | _(requerido)_ | JSON `{CUT: n_distrito}` |
| `--verbose` | — | Muestra el detalle completo de cada discrepancia (por default solo el resumen agrupado por distrito) |

---

### 13. validar_datos_externos.py — Validación de datos externos

Valida los 4 archivos de datos externos usados por `malapportionment.py` y `electoral_analysis.py` (ver "Datos externos" más arriba): `poblacion_comunal_censo2024.csv`, `servel_2025_por_cut.csv`, `asignacion_vigente.json`, `pacto_map_2025.json`. Para cada archivo imprime shape/keys y una muestra de 3 filas, corre verificaciones específicas (columnas, nulos, formato de CUT, cobertura) etiquetadas OK/WARNING, y termina con código de salida distinto de 0 si hubo alguna WARNING (uso en CI).

```bash
# Sin argumentos — resuelve datos/ relativo a la raíz del proyecto
python scripts/validar_datos_externos.py
```

---

### 14. recalcular_reock.py — Recalcula Reock tras fix de shapely 2.x

Recalcula la métrica Reock en `ensemble_stats.csv` de corridas ya generadas, tras la corrección del bug de compatibilidad de `reock()` con shapely 2.x (ver "Problemas conocidos" más abajo) — evita tener que re-correr ReCom completo solo para refrescar Reock.

```bash
python scripts/recalcular_reock.py --base-dir . --regiones 13 --scenario legal

# Varios escenarios a la vez
python scripts/recalcular_reock.py --base-dir . --regiones 13 \
    --scenarios legal,apc_free,apc_soft
```

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--base-dir` | `.` | Directorio raíz con `SHP_APC2023_R*` y `datos/` |
| `--regiones` | `13` | Regiones: número o lista separada por coma |
| `--scenario` | — | Un solo escenario (`legal`\|`apc_free`\|`apc_soft`) — mutuamente excluyente con `--scenarios` |
| `--scenarios` | — | Lista separada por coma, ej. `legal,apc_free,apc_soft` |

---

## API de la librería

### Equivalencia censal

```python
import chiledist as cd

cd.print_equivalence()             # Tabla completa USA ↔ Chile
cd.describe_hierarchy("CHL")      # Jerarquía detallada Chile
dist = cd.get_analog("USA", 4)    # Census Tract → Distrito APC
print(dist.code_field)             # → ID_DIST
```

### Carga de datos

```python
# Capa única, todas las regiones
distritos = cd.load_layer("distrital", base_dir="./SHP_APC2023")
comunas   = cd.load_layer("comunal",   base_dir="./SHP_APC2023")

# Capa única, región específica
mz_rm = cd.load_layer("manzana_urbana", base_dir="./SHP_APC2023", regions=[13])

# Cargar y construir grafo nacional
resultado = cd.build_national(
    layer="distrital",
    base_dir="./SHP_APC2023",
    strategy="block_diagonal",
    save_prefix="distrital_nac",
)
G   = resultado["G"]
adj = resultado["adj"]
rm  = resultado["por_region"][13]

# Agregar población desde manzanas
pop = cd.aggregate_population(mz_urb, level="distrito", source="urbana")
```

### Grafos y matrices

```python
# Política de islas: "nearest" | "threshold" | "none"
G, adj, ids = cd.build_graph(
    distritos, id_col="ID_DIST",
    method="queen",
    island_policy="nearest",       # conecta cada isla al vecino más cercano
)

# Solo conectar islas dentro de 30 km (útil para archipiélagos cercanos)
G, adj, ids = cd.build_graph(
    distritos, id_col="ID_DIST",
    island_policy="threshold",
    island_threshold_km=30.0,
)

# No conectar islas (útil para SMC o análisis de componentes)
G, adj, ids = cd.build_graph(distritos, id_col="ID_DIST", island_policy="none")

# CRS automático (detecta UTM óptima desde los datos)
crs = cd.get_optimal_crs(distritos)   # "EPSG:32719" para Chile continental
G, adj, ids = cd.build_graph(distritos, id_col="ID_DIST", crs_metric=crs)

print(cd.graph_stats(G, adj))

cd.save_graph(adj, ids, distritos, "ID_DIST", prefix="mi_matriz")
adj, indice, G = cd.load_graph("mi_matriz")

# Subir de nivel: manzanas → distritos → comunas
G_dist, gdf_dist = cd.contract_graph(
    G_manzanas, manzanas,
    id_col="MANZENT", group_col="COD_DISTRITO",
    agg_cols={"viviendas": "sum"},
)
```

### Métricas

```python
metricas = cd.all_compactness(distritos, id_col="ID_DIST")
# Columnas: polsby_popper, reock, convex_hull_ratio, schwartzberg, compactness_mean

balance = cd.population_balance(
    distritos, pop_col="viviendas", partition_col="CUT"
)

resumen = cd.spatial_summary(
    distritos, id_col="ID_DIST",
    pop_col="viviendas", group_col="N_REGION"
)
```

### Visualización

```python
cd.plot_adjacency_graph(G, adj, indice, color_by="tipo", save_path="grafo.png")
cd.plot_layer(distritos, color_col="TIPO_DISTRITO", save_path="mapa.png")
cd.plot_plan(distritos, assignment=mi_plan, id_col="ID_DIST",
             pop_col="viviendas", show_pop_balance=True, save_path="plan.png")
cd.plot_compactness(distritos, metricas, id_col="ID_DIST",
                    metric="polsby_popper", save_path="compacidad.png")
```

### Escenarios (chiledist.domain.scenario, post-B1; antes config.py)

`ScenarioConfig` define todos los parámetros de un análisis en un único dataclass. Tres escenarios predefinidos cubren los casos de uso principales.

```python
import chiledist as cd
import dataclasses

# Escenario legal (predefinido)
sc = cd.SCENARIO_LEGAL
print(sc.decision_unit)    # "CUT"
print(sc.preserve_mode)    # "hard"
print(sc.pop_col)          # "viviendas"

# APC libre
sc = cd.SCENARIO_APC_FREE  # decision_unit="ID_DIST", preserve_mode="none"

# APC con penalización de comunas partidas
sc = cd.SCENARIO_APC_SOFT  # decision_unit="ID_DIST", preserve_mode="soft", split_penalty=0.25

# Override de campos — incluyendo política de islas y CRS
sc_islas = dataclasses.replace(
    cd.SCENARIO_APC_FREE,
    island_policy="threshold",
    island_threshold_km=30.0,  # solo conectar archipiélagos próximos
)
sc_crs = dataclasses.replace(
    cd.SCENARIO_LEGAL,
    crs_metric="EPSG:32719",   # forzar CRS en lugar de auto-detectar
)
sc_padron = dataclasses.replace(cd.SCENARIO_LEGAL, pop_col="inscritos")

# Cargar desde YAML (sección "connectivity" para island_policy/crs_metric)
sc = cd.load_scenario("scenarios/mi_escenario.yml")

# Guardar a YAML
cd.save_scenario(sc, "scenarios/custom.yml")
```

| Atributo | Tipo | Descripción |
|----------|------|-------------|
| `decision_unit` | `"CUT"` / `"ID_DIST"` | Unidad mínima del redistritaje |
| `preserve_mode` | `"hard"` / `"soft"` / `"none"` | Restricción de integridad comunal |
| `split_penalty` | `float` | Peso de penalización en modo `soft` (default 0.25) |
| `pop_col` | `str` | Columna de población (`"viviendas"`, `"personas"`, `"inscritos"`) |
| `pop_tolerance` | `float` | Tolerancia de desviación poblacional (default 0.05) |
| `island_policy` | `"nearest"` / `"threshold"` / `"none"` | Conexión de islas al grafo |
| `island_threshold_km` | `float` | Umbral de distancia para `island_policy="threshold"` (default 50 km) |
| `crs_metric` | `str` / `None` | CRS métrico; `None` = auto-detectar con `get_optimal_crs` |
| `name` | `str` | Nombre del escenario para rutas de salida |

---

### Jerarquía y restricciones (chiledist.domain.hierarchy, chiledist.rules.constraints, post-B1)

Funciones para contraer la capa APC a la unidad de decisión del escenario y para construir las restricciones gerrychain correspondientes.

```python
import chiledist as cd

# Contraer distritos APC a comunas (decision_unit="CUT")
comunas = cd.contract_to_decision_units(
    gdf_apc,
    scenario=cd.SCENARIO_LEGAL,
    agg_cols={"viviendas": "sum", "polsby_popper": "mean"},
)

# Construir capa de decisión (contrae + recalcula métricas)
gdf_dec = cd.build_decision_layer(gdf_apc, scenario=cd.SCENARIO_APC_SOFT)

# Validar que la asignación respeta la jerarquía
ok, violaciones = cd.validate_hierarchy(
    gdf_apc, assignment, cut_col="CUT", id_col="ID_DIST"
)

# Propagar asignación distrital → nivel APC
gdf_apc_with_plan = cd.propagate_district_assignment(
    gdf_apc, gdf_dec, assignment_col="distrito"
)

# Normalizar CUT antes de cruzar fuentes que lo representan distinto
# (int sin cero inicial vs string de 5 dígitos) — ver "Datos externos"
cd.normalize_cut(1101)     # -> "01101"
cd.normalize_cut("01101")  # -> "01101" (idempotente)
```

```python
# Restricción dura: no partir comunas (hard)
preserve_c = cd.make_preserve_constraint(partition, unit_col="CUT", mode="hard")

# Updaters y restricciones completos para un escenario
updaters    = cd.build_updaters_for_scenario(gdf, scenario=cd.SCENARIO_LEGAL)
constraints = cd.build_constraints_for_scenario(partition, scenario=cd.SCENARIO_LEGAL)

# Función de score con penalización de splits (modo soft)
score = cd.score_with_split_penalty(partition, penalty=0.25)
```

---

### Métricas de comunas partidas (chiledist.engines.metrics, post-B1; antes split_metrics.py)

Analiza cuántas comunas quedan divididas entre distritos en un plan dado.

```python
import chiledist as cd

# Número de comunas partidas y fragmentos
n_partidas, n_fragmentos = cd.count_split_units(
    gdf_apc, assignment, unit_col="CUT", dist_col="distrito"
)

# Índice de severidad: ponderado por tamaño de fragmento
isi = cd.split_severity_index(gdf_apc, assignment, unit_col="CUT", pop_col="viviendas")

# Resumen detallado: qué comunas, cuántos fragmentos, fragmento más pequeño
df_splits = cd.split_unit_summary(gdf_apc, assignment, unit_col="CUT")

# Fragmentos menores al X% de la unidad original
n_small = cd.small_fragment_count(gdf_apc, assignment, unit_col="CUT", min_frac=0.05)

# Todas las métricas juntas (para añadir a ensemble_stats)
metrics = cd.plan_split_metrics(gdf_apc, assignment, unit_col="CUT", pop_col="viviendas")
# → {"n_comunas_partidas": 3, "n_fragmentos_extra": 5, "split_severity_index": 0.12, ...}
```

---

### Fuentes de población (data/)

Subpaquete para cargar datos de población desde el Censo 2024 o el padrón SERVEL.

#### Censo 2024 — join exacto por distrito (recomendado)

```python
import chiledist.domain.data.census2024 as c24

# Cargar tabla manzana-entidad (Base_manzana_entidad_CPV24.csv, ~24 MB, TSV)
mz = c24.load_manzana_censo2024(
    "datos/Base_manzana_entidad_CPV24.csv",
    sep="\t",
    encoding="utf-8-sig",
)
# → DataFrame con columnas: CUT, COD_DISTRITO, n_per, n_hog

# Join exacto: agrega "personas" y "hogares" por ID_DIST
gdf = c24.join_manzana_to_apc(gdf_apc, mz)

# Instrucciones de descarga desde INE
c24.download_instructions()
```

#### Censo 2024 — distribución proporcional por comuna

```python
# Tabla comunal del Censo 2024
census = c24.load_census2024("datos/censo2024_comunas.csv")

# Distribuye proporcionalmente usando viviendas como proxy
gdf = c24.join_census_to_apc(gdf_apc, census, proxy_col="viviendas")
# → agrega columna "personas"
```

#### Padrón electoral SERVEL

```python
import chiledist.domain.data.servel as sv

# Cargar padrón comunal
padron = sv.load_padron_electoral("datos/padron_2024.csv")

# Join con distribución proporcional por viviendas
gdf = sv.join_padron_to_apc(gdf_apc, padron, proxy_col="viviendas")
# → agrega columna "inscritos"

# Resultados electorales por comuna (última elección parlamentaria observada)
resultados = sv.load_resultados_electorales("datos/resultados_eleccion.csv")
```

---

### Comparación de escenarios (chiledist.inference.comparison, chiledist.inference.plots, chiledist.evaluation.scoring, chiledist.domain.ensemble_store)

```python
import chiledist as cd
import dataclasses

# Cargar ensembles desde disco (estructura generada por redistritaje.py)
ensembles = cd.load_ensembles_from_disk(
    output_base="datos",
    region_code=13,
    scenario_names=["legal", "apc_free", "apc_soft"],
)
# → {"legal": DataFrame, "apc_free": DataFrame, "apc_soft": DataFrame}

# Tabla comparativa con medianas, p25, p75 y deltas respecto al baseline
tabla = cd.compare_ensembles(ensembles, baseline="legal")

# Delta de un escenario respecto al baseline
tabla_delta = cd.scenario_delta(tabla, baseline="legal")

# ── Ranking con puntaje compuesto ────────────────────────────────────────────

# Configuración por defecto (desde PESOS_DEFAULT)
ranking = cd.rank_scenarios(tabla)
# → DataFrame con composite_score, rank, score_<col> por métrica

# Priorizar compacidad (ScoringConfig)
sc = cd.ScoringConfig.from_weights({"pp_promedio": 0.6, "max_dev_pob_pct": 0.4})
ranking_custom = cd.rank_scenarios(tabla, scoring_config=sc)

# Normalización por z-score en lugar de min-max
sc_z = cd.ScoringConfig.from_weights(
    {"pp_promedio": 0.5, "max_dev_pob_pct": 0.3, "n_comunas_partidas": 0.2},
    normalization="zscore",
)
ranking_z = cd.rank_scenarios(tabla, scoring_config=sc_z)

# ── Frontera de Pareto ───────────────────────────────────────────────────────

# Pareto N-dimensional sobre puntos crudos
import numpy as np
pts = np.array([[0.1, 5, 3], [0.2, 3, 1], [0.3, 2, 4]])
idx = cd.pareto_frontier_nd(pts, minimize=[True, True, False])
# → índices de los puntos no dominados

# Pareto sobre escenarios (columnas *_median de compare_ensembles)
optimos = cd.pareto_optimal_scenarios(tabla)
print(optimos["escenario"].tolist())   # escenarios no dominados por ningún otro

# ── Visualizaciones ──────────────────────────────────────────────────────────

# Scatter de tradeoff con frontera de Pareto por escenario
cd.plot_tradeoff_frontier(
    ensembles,
    x_col="n_comunas_partidas",
    y_col="max_dev_pob_pct",
    save_path="tradeoff.png",
)

# Boxplots comparativos por métrica
cd.plot_boxplots_comparativos(ensembles, save_path="boxplots.png")

# Gráfico de araña multi-métrica (todos los ejes normalizados a [0,1]; 1=mejor)
cd.plot_radar_comparativo(tabla, save_path="radar.png")

# Tabla de frecuencia de comunas partidas por escenario
freq = cd.split_frequency_table("datos/R13_METROPOLITANA/redistritaje")

# ── Visibilidad de escenarios sin ensemble válido + completitud ─────────────
# (ver "#### Estados posibles en el resumen final" más arriba: infeasible_population,
# sin_particion, etc. — un escenario así no aparece en `ensembles`)

statuses = cd.load_scenario_statuses_from_disk(
    output_base="datos", region_code=13,
    scenario_names=["legal", "apc_free", "apc_soft"],
)
# → {"legal": {"status": "infeasible_population", "reason": "...", ...}} — solo
#   los escenarios sin ensemble válido, leídos de scenario_status.json

overview = cd.build_scenario_overview(
    ["legal", "apc_free", "apc_soft"], ensembles, statuses,
)
# → una fila por escenario ESPERADO (válido o no): escenario, status, reason,
#   included_in_scoring, n_planes — nunca se excluye de esta tabla

completeness = cd.assess_comparison_completeness(
    ["legal", "apc_free", "apc_soft"], ensembles, baseline="legal",
)
# → {"comparison_status": "COMPLETE"|"INCOMPLETE", "expected_scenarios": 3,
#    "valid_ensembles": 2, "missing_baseline": "legal"|None,
#    "ranking_scope": "full"|"partial"}
```

| Símbolo | Descripción |
|---------|-------------|
| `ScoringConfig` | Dataclass: pesos + direcciones + normalización (`minmax`/`zscore`/`rank`) |
| `compare_ensembles` | Tabla de medianas, p25/p75 y deltas por escenario |
| `rank_scenarios` | Ranking compuesto ponderado; acepta `ScoringConfig` |
| `pareto_frontier_nd` | Índices Pareto-óptimos en N dimensiones (arrays o DataFrame) |
| `pareto_optimal_scenarios` | Filas Pareto-óptimas de la tabla de `compare_ensembles` |
| `load_scenario_statuses_from_disk` | Lee `scenario_status.json` de escenarios sin ensemble válido |
| `build_scenario_overview` | Una fila por escenario esperado, válido o no; nunca oculta un escenario |
| `assess_comparison_completeness` | `comparison_status`/`ranking_scope`/`missing_baseline` de la comparación |
| `plot_tradeoff_frontier` | Scatter 2D con frontera de Pareto por escenario |
| `plot_radar_comparativo` | Gráfico de araña multi-métrica normalizada |
| `plot_boxplots_comparativos` | Boxplots de métricas por escenario |

### Preflight de factibilidad poblacional (chiledist.rules.feasibility)

```python
import chiledist as cd

# Población de cada unidad de decisión indivisible (ej. CUT en modo legal)
resultado = cd.check_population_feasibility(
    unit_populations={"13101": 66_697, "13102": 12_500, "...": "..."},
    n_districts=8,
    pop_tolerance=0.05,
)
# → PopulationFeasibilityResult(feasible=False,
#       reason="indivisible_unit_exceeds_population_bound", ...)

if not resultado.feasible:
    print(resultado.diagnostic_message())
```

`scripts/redistritaje.py` llama a esta función antes de intentar `recursive_tree_part`; si `feasible=False`, retorna `status="infeasible_population"` sin gastar tiempo de sampler (ver la tabla de estados en la sección de `redistritaje.py`).

---

### Electoral (chiledist.engines.allocation, chiledist.evaluation.proportionality)

Implementa el sistema electoral chileno: D'Hondt y magnitudes de escaño por distrito (`chiledist.engines.allocation`) y métricas de proporcionalidad (`chiledist.evaluation.proportionality`).

```python
import chiledist as cd

# D'Hondt para un distrito
resultado = cd.dhondt(
    votes={"Chile Vamos": 45000, "Apruebo Dignidad": 38000, "PDG": 12000},
    seats=5,
    threshold=0.0,   # Chile no tiene umbral legal
)
# → {"Chile Vamos": 3, "Apruebo Dignidad": 2, "PDG": 0}

# Asignar magnitudes de escaño (Hamilton acotado: min=3, max=8, total=155)
pop = gdf_comunas.set_index("CUT")["personas"]
magnitudes = cd.assign_seat_magnitudes(pop, total_seats=155, min_seats=3, max_seats=8)
# → pd.Series CUT → n_escaños

# Magnitudes vigentes Ley 20.840 Art. 179 — sin cambios en 2017, 2021, 2025 ni 2026
# (Art. 179 bis prevé revisión decenial post-Censo; SERVEL aún no emite nueva tabla)
print(cd.MAGNITUDES_LEGALES_LEY20840)  # {1: 3, 2: 3, ..., 28: 3}
assert sum(cd.MAGNITUDES_LEGALES_LEY20840.values()) == 155
# MAGNITUDES_LEGALES_2021 es un alias de la misma tabla (compatibilidad)

# Correr D'Hondt en todos los distritos de un plan
resultados = cd.run_electoral_plan(
    assignment,         # dict unit_id → distrito_electoral
    votes_df,           # DataFrame unidad × partido
    magnitudes,         # pd.Series distrito → n_escaños
)
# → DataFrame: partido × escaños_ganados por cada distrito

# Shares nacionales agregados
shares = cd.national_shares(resultados)
# → {"Chile Vamos": {"votos_pct": 42.3, "escanos_pct": 48.4}, ...}

# Índices de proporcionalidad
v = shares_votos   # pd.Series partido → %
s = shares_escanos # pd.Series partido → %
print(cd.gallagher_index(v, s))      # LSq — principal indicador
print(cd.loosemore_hanby(v, s))      # LH
print(cd.rae_index(v, s))            # Rae
print(cd.effective_number_of_parties(v))  # NEP votos (Laakso-Taagepera)

# Resumen completo
tabla = cd.proportionality_summary(v, s)
# → DataFrame: gallagher, loosemore_hanby, rae, enp_votos, enp_escanos

# Métricas electorales de un plan (para añadir a ensemble_stats)
metrics = cd.plan_electoral_metrics(assignment, votes_df, pop_by_unit)
```

---

### Fair share y distancia al ideal fraccional (chiledist.engines.fairshare, post-B1; antes fairshare.py)

Mide qué tan lejos está una asignación entera (D'Hondt) del ideal fraccional que satisface
simultáneamente proporcionalidad nacional y respeto a las magnitudes distritales.

```python
import chiledist as cd
import chiledist.engines.fairshare as fs

# ── Fair share matrix ─────────────────────────────────────────────────────────

# Método biproporcional (Balinski–Ramírez): satisface cuotas Hamilton + magnitudes
Q = fs.fair_share_matrix(
    votes_by_dist,           # salida de aggregate_votes(): district, partido, votos
    magnitudes,              # pd.Series {distrito: n_escaños}
    method="biproportional", # default — recomendado para H6
)
# → DataFrame partido × distrito con valores fraccionales
# Σ columna j = magnitud j  ✓
# Σ fila i    = cuota Hamilton del partido i  ✓

# Método distrital (más simple; NO garantiza cuotas nacionales)
Q_d = fs.fair_share_matrix(votes_by_dist, magnitudes, method="district")

# ── Convertir resultado D'Hondt a matriz ─────────────────────────────────────

results = cd.run_electoral_plan(votes_by_dist, magnitudes)
N = fs.results_to_matrix(results)   # DataFrame partido × distrito (enteros)

# También funciona con run_electoral_plan_binivel (D'Hondt binivel)
results_bi = cd.run_electoral_plan_binivel(votes_by_dist, magnitudes)
N_bi = fs.results_to_matrix(results_bi)

# ── Distancias ────────────────────────────────────────────────────────────────

# L1: escaños totales fuera de lugar
l1 = fs.l1_distance_fair_share(N, Q)                # valor absoluto
l1_norm = fs.l1_distance_fair_share(N, Q, normalize=True)  # ÷ total_escaños ∈ [0,2]

# L2: norma de Frobenius (penaliza más las desviaciones grandes)
l2 = fs.l2_distance_fair_share(N, Q)
rmse = fs.l2_distance_fair_share(N, Q, normalize=True)     # RMSE por celda

# Celda con mayor desviación
worst = fs.max_cell_deviation(N, Q)
# → {'max_dev': 1.5, 'partido': 'UDI', 'distrito': 3, 'n_obs': 4.0,
#    'q_ideal': 2.5, 'direction': 'sobre'}

# ── Resumen completo (compatible con ensemble_stats) ─────────────────────────

summary = fs.fair_share_summary(N, Q, label="legal_vigente")
# → dict con claves:
#   plan, l1, l1_norm, l2, rmse,
#   max_dev, max_dev_partido, max_dev_distrito, max_dev_direction,
#   n_celdas, n_sobre, n_sub, n_exacto, share_sobre

# Para agregar al ensemble:
import numpy as np
rows = []
for asgn, lbl in zip(ensemble_assignments, labels):
    vd = cd.aggregate_votes(votes_long, asgn, unit_col="CUT")
    Nk = fs.results_to_matrix(cd.run_electoral_plan(vd, magnitudes))
    Qk = fs.fair_share_matrix(vd, magnitudes)
    rows.append(fs.fair_share_summary(Nk, Qk, label=lbl))
df_h6 = pd.DataFrame(rows)
print(f"L1_norm mediana del ensemble: {df_h6['l1_norm'].median():.4f}")
```

| Función | Input | Output | Hipótesis |
|---------|-------|--------|-----------|
| `fair_share_matrix()` | `votes_df`, `magnitudes` | DataFrame partido × distrito (fraccional) | H6 |
| `results_to_matrix()` | `results` (salida D'Hondt) | DataFrame partido × distrito (entero) | H6 |
| `l1_distance_fair_share()` | `N`, `Q` | `float` — escaños fuera de lugar | H6 |
| `l2_distance_fair_share()` | `N`, `Q` | `float` — norma de Frobenius | H6 |
| `max_cell_deviation()` | `N`, `Q` | `dict` — celda más distante | H6 |
| `fair_share_summary()` | `N`, `Q`, `label` | `dict` — todas las métricas | H6 |

---

### Malapportionment geográfico (chiledist.evaluation.malapportionment, post-B1; antes chiledist.malapportionment)

Índices de malapportionment comparables internacionalmente. Complementa
`personas_por_escano` / `peso_relativo_del_voto` (distritales, `chiledist.evaluation.district_malapportionment`) con escalares globales
que permiten comparar planes entre sí y con sistemas de otros países. Implementa H9.

```python
import chiledist as cd
import chiledist.evaluation.malapportionment as mala
import pandas as pd

pop_d = pd.Series({1: 500_000, 2: 300_000, 3: 200_000})
mag   = pd.Series({1: 3, 2: 3, 3: 2})

# ── Índices escalares ─────────────────────────────────────────────────────────

# Índice de Samuels-Snyder M = (1/2) Σ|s_i - p_i|
# Rango [0, 1];  M=0 ↔ proporcionalidad perfecta
ss = cd.samuels_snyder_index(pop_d, mag)
print(f"Samuels-Snyder M = {ss:.4f}")

# Loosemore-Hanby aplicado a geografía (idéntico a SS; alias semántico)
lh = cd.loosemore_hanby_malapportionment(pop_d, mag)

# Coeficiente de Gini de la distribución de PxE
# pop_weighted=True (default): pondera por prob. de que un ciudadano al azar habite en ese distrito
gini = cd.gini_personas_por_escano(pop_d, mag, pop_weighted=True)
print(f"Gini PxE (pop-ponderado) = {gini:.4f}")

# Ratio máximo-mínimo de personas/escaño
mmr = cd.max_min_representation_ratio(pop_d, mag)
print(f"Ratio máx/mín = {mmr['ratio']:.2f}  "
      f"(D{mmr['max_district']} subrep. / D{mmr['min_district']} sobrerep.)")
print(f"CV = {mmr['cv']:.4f}")

# ── Resumen completo ──────────────────────────────────────────────────────────

summary = cd.malapportionment_summary(pop_d, mag, label="mi_plan")
# Claves: plan, n_districts, total_seats, total_pop,
#         samuels_snyder, loosemore_hanby_M, gini_pop_weighted, gini_unweighted,
#         max_min_ratio, cv, mean_pxe, std_pxe, max_pxe, max_district,
#         min_pxe, min_district

# ── Comparar múltiples planes ─────────────────────────────────────────────────

plans = {
    "legal":    {1: 1, 2: 1, 3: 2, 4: 2},
    "apc_soft": {1: 1, 2: 2, 3: 1, 4: 2},
}
pop_units = pd.Series({1: 400_000, 2: 300_000, 3: 200_000, 4: 100_000})

comparison = cd.compare_malapportionment_plans(
    plans,
    pop_by_unit=pop_units,
    # magnitudes=None → assign_seat_magnitudes por plan (total=155, min=3, max=8)
)
print(comparison[["samuels_snyder", "gini_pop_weighted", "max_min_ratio"]])

# ── Comparación internacional ─────────────────────────────────────────────────

# Benchmarks integrados: Chile_legal_2021, USA_House_2023,
#                        Argentina_2019, Brasil_2018, España_2019
tabla = cd.international_comparison(
    custom={"Chile_APC_soft": summary},
    include_benchmarks=True,
)
print(tabla[["samuels_snyder", "max_min_ratio", "cv", "type"]])

# ── Visualizaciones ───────────────────────────────────────────────────────────

# Histograma de distribución PxE
cd.plot_pxe_distribution(pop_d, mag, label="mi_plan")

# Ranking de distritos (barra horizontal, coloreado: sub vs sobrerrepresentado)
cd.plot_malapportionment_ranking(pop_d, mag, label="mi_plan", top_n=20)

# Dot-plot de comparación internacional
cd.plot_international_comparison(
    tabla,
    metric="samuels_snyder",
    metric_label="Índice de Samuels-Snyder (M)",
    save_path="resultados/h9_comparacion_internacional.png",
)
```

| Función | Input | Output | Hipótesis |
|---------|-------|--------|-----------|
| `samuels_snyder_index()` | `pop`, `mag` | `float` M ∈ [0, ~0.5] | H9 |
| `loosemore_hanby_malapportionment()` | `pop`, `mag` | `float` (≡ SS; alias semántico) | H9 |
| `gini_personas_por_escano()` | `pop`, `mag` | `float` Gini ∈ [0, 1) | H9 |
| `max_min_representation_ratio()` | `pop`, `mag` | `dict` ratio, CV, extremos | H9 |
| `malapportionment_summary()` | `pop`, `mag`, `label` | `dict` — todos los índices | H9 |
| `compare_malapportionment_plans()` | `plans`, `pop_by_unit` | `DataFrame` — planes × índices | H9 |
| `international_comparison()` | `custom`, benchmarks | `DataFrame` — países + planes | H9 |
| `plot_pxe_distribution()` | `pop`, `mag` | `Figure` — histograma PxE | H9 |
| `plot_malapportionment_ranking()` | `pop`, `mag` | `Figure` — ranking distritos | H9 |
| `plot_international_comparison()` | `DataFrame` | `Figure` — dot-plot comparado | H9 |

---

### Barrido paramétrico y frontera Pareto continua (chiledist.inference.pareto_sweep, post-B1; antes chiledist.pareto_sweep)

Construye la frontera Pareto real del espacio de tradeoffs operando sobre **planes individuales**
—no medianas por escenario— con bandas bootstrap de incertidumbre y detección automática del
knee point (punto de máxima eficiencia). Implementa H8.

```python
import chiledist as cd
import numpy as np, pandas as pd

penalties = np.linspace(0.0, 1.0, 11)

# Cargar ensembles ya generados (uno por nivel de penalización)
ensembles = {
    p: pd.read_csv(f"datos/R13_METROPOLITANA/redistritaje/apc_soft_p{p:.2f}/ensemble_stats.csv")
    for p in penalties
}

# ── Pool consolidado ──────────────────────────────────────────────────────────

pool = cd.sweep_split_penalty(ensembles)
# → DataFrame: columna 'penalty' + métricas de ensemble_stats
# Una fila por plan (cada nivel aporta N planes al pool)

# ── Frontera Pareto real (planes individuales) ────────────────────────────────

frontier_res = cd.build_tradeoff_frontier(
    pool,
    x_metric="max_dev_pob_pct",
    y_metric="n_comunas_partidas",
    n_bootstrap=500,      # remuestreos para IC 90% y 50%
    random_state=42,
)
print(f"Planes Pareto-óptimos: {frontier_res['metadata']['n_pareto']}")

# Subconjunto de planes no dominados
frontier_df = frontier_res["frontier"]

# Bandas bootstrap de la frontera
boot_bands  = frontier_res["bootstrap_bands"]  # x_grid, y_p5, y_p25, y_p50, y_p75, y_p95

# Estadísticas por penalización
stats       = frontier_res["per_penalty_stats"]

# ── Knee point: máxima eficiencia ─────────────────────────────────────────────

knee = cd.detect_knee_point(
    frontier_df,
    method="normalized_distance",   # espacio normalizado [0,1]×[0,1]
    diminishing_threshold=0.5,      # rendimientos decrecientes < 50% de la media
)
print(f"Penalty óptimo: {knee['knee_penalty']:.2f}")
print(f"  max_dev_pob_pct    = {knee['knee_x']:.2f}%")
print(f"  n_comunas_partidas = {knee['knee_y']:.1f}")
if knee["diminishing_start_x"] is not None:
    print(f"Rendimientos decrecientes desde x = {knee['diminishing_start_x']:.2f}")

# ── Figura publicable ─────────────────────────────────────────────────────────

fig = cd.plot_tradeoff_curve(
    pool, frontier_res,
    knee_result=knee,
    show_density_bands=True,
    show_diminishing=True,
    save_path="resultados/h8_pareto_frontier.png",
)

# ── Resumen estadístico por nivel ─────────────────────────────────────────────

summary = cd.summarize_tradeoff(pool, frontier_res, knee)
# → DataFrame indexado por penalty; columnas {metric}_mean/std/p5/p95,
#   n_planes, n_pareto, pct_pareto, is_knee
print(summary[["n_planes", "pct_pareto", "is_knee"]])
```

| Función | Input | Output | Hipótesis |
|---------|-------|--------|-----------|
| `sweep_split_penalty()` | `dict {penalty: DataFrame}` | Pool de planes individuales | H8 |
| `build_tradeoff_frontier()` | pool + métricas | `dict` — frontera + bandas bootstrap | H8 |
| `detect_knee_point()` | frontier DataFrame | `dict` — knee + rendimientos decrecientes | H8 |
| `plot_tradeoff_curve()` | pool + frontier + knee | `Figure` — scatter + frontera + IC | H8 |
| `summarize_tradeoff()` | pool + frontier + knee | `DataFrame` — por nivel de penalización | H8 |

---

### Análisis distribucional electoral sobre ensembles (chiledist.inference.electoral_ensemble, post-B1; antes chiledist.electoral_ensemble)

Evalúa cómo se distribuyen las métricas electorales (Gallagher, ENP, prima de escaños) sobre
el universo de planes de redistritaje. Permite determinar si el resultado del mapa vigente es
típico o atípico respecto a planes alternativos plausibles (H7).

```python
import chiledist as cd
import pandas as pd, json

votes_df  = cd.data.servel.votos_por_comuna()
pop       = cd.data.census2024.poblacion_comunal()["personas"]
with open("datos/pacto_map_2025.json") as f:
    pacto_map = json.load(f)

# ── Correr ensemble electoral ─────────────────────────────────────────────────

# ensemble_assignments: list[dict {CUT: n_circunscripcion}] (salida de H1)
results = cd.run_electoral_ensemble(
    ensemble_assignments,
    votes_df,
    pop,
    magnitudes=pd.Series(cd.MAGNITUDES_LEGALES_LEY20840),
    pacto_map=pacto_map,
    unit_col="CUT",
    include_seat_bonus=True,   # agrega columnas seat_bonus_{partido}
)
# → DataFrame: una fila por plan, indexado por plan_id
# Columnas: gallagher, loosemore_hanby, rae, enp_votos, enp_escanos,
#           n_partidos_con_escanos, seat_bonus_A, seat_bonus_B, ...

# ── Resumen estadístico ───────────────────────────────────────────────────────

summary = cd.summarize_electoral_ensemble(results)
# → DataFrame indexado por métrica; columnas: mean, median, std, p5, p25, p75, p95, ci95_*, n

# Gallagher: media, IC 95%
gall_stats = cd.ensemble_gallagher(results)
print(f"Gallagher: {gall_stats['mean']:.2f} (IC 95%: [{gall_stats['ci95_low']:.2f}, {gall_stats['ci95_high']:.2f}])")

# ENP (votos y escaños)
enp = cd.ensemble_enp(results)
print(f"ENP escaños media: {enp['enp_escanos']['mean']:.2f}")

# Prima de escaños por partido
sb_all = cd.ensemble_seat_bonus(results)                  # DataFrame: partido × estadísticas
sb_ps  = cd.ensemble_seat_bonus(results, partido="PS")   # dict para un partido específico

# ── Gráficos ──────────────────────────────────────────────────────────────────

import matplotlib.pyplot as plt

obs_gallagher = 4.3   # valor observado del plan vigente

# Histograma
cd.plot_ensemble_histogram(results, metric="gallagher", observed=obs_gallagher)

# Violin plots para varias métricas
cd.plot_ensemble_violin(
    results,
    metrics=["gallagher", "enp_votos", "enp_escanos"],
    observed={"gallagher": obs_gallagher, "enp_votos": 3.1, "enp_escanos": 2.8},
)

# ECDF — muestra el percentil del observado dentro del ensemble
cd.plot_ensemble_ecdf(results, metric="gallagher", observed=obs_gallagher,
                      save_path="resultados/h7_gallagher_ecdf.png")

# ── Umbral efectivo (magnitudes variables) ────────────────────────────────────

# Cuando magnitudes se calculan por plan (magnitudes=None en run_electoral_ensemble)
from chiledist.engines.allocation import assign_seat_magnitudes
mags_list = [
    assign_seat_magnitudes(
        pd.Series({d: sum(pop.get(u, 0) for u, dd in a.items() if dd == d)
                   for d in set(a.values())}),
    )
    for a in ensemble_assignments
]
threshold_df = cd.ensemble_effective_threshold(mags_list)
# → DataFrame: distrito × estadísticas del umbral efectivo T_U = 1/(M+1)
```

| Función | Input | Output | Hipótesis |
|---------|-------|--------|-----------|
| `run_electoral_ensemble()` | ensemble + votes + pop + magnitudes + pacto_map | DataFrame plan × métricas electorales | H7 |
| `ensemble_gallagher()` | ensemble_results | `dict` — estadísticas de distribución | H7 |
| `ensemble_seat_bonus()` | ensemble_results | `DataFrame` o `dict` — prima de escaños | H7 |
| `ensemble_enp()` | ensemble_results | `dict` — ENP votos y escaños | H7 |
| `ensemble_effective_threshold()` | list de magnitudes | `DataFrame` — umbral por distrito | H7 |
| `summarize_electoral_ensemble()` | ensemble_results | `DataFrame` — todas las métricas | H7 |
| `plot_ensemble_histogram()` | ensemble_results, metric | `Figure` — histograma | H7 |
| `plot_ensemble_violin()` | ensemble_results, metrics | `Figure` — violin plots | H7 |
| `plot_ensemble_ecdf()` | ensemble_results, metric | `Figure` — ECDF | H7 |

---

### Diagnósticos de convergencia (chiledist.engines.samplers.diagnostics, post-B1)

Herramientas para evaluar si la cadena MCMC ha convergido y para ejecutar análisis multi-cadena.

> **Alcance de los diagnósticos.** R-hat < 1.1 indica que las cadenas paralelas se mezclaron bien (_convergencia_), pero **no** garantiza que la distribución empírica del ensemble represente la distribución objetivo (uniforme sobre planes válidos). Para esa validación, comparar con resultados SMC como referencia independiente.

```python
import chiledist as cd
# o directamente: from chiledist.engines.samplers.diagnostics import ...
import numpy as np

# Función de autocorrelación
serie = ensemble_stats["pp_mean"].values
acf = cd.autocorrelation_function(serie, max_lag=50)
# → np.ndarray shape (51,), acf[0] = 1.0

# Tamaño de muestra efectivo (considera correlaciones en la cadena)
ess = cd.effective_sample_size(serie, max_lag=200)
print(f"ESS = {ess:.1f} de {len(serie)} muestras")

# Gelman-Rubin R-hat (requiere ≥ 2 cadenas)
chains = [df1["pp_mean"].values, df2["pp_mean"].values, df3["pp_mean"].values]
rhat = cd.gelman_rubin(chains)
print(f"R-hat = {rhat:.4f} ({'converge' if rhat < cd.RHAT_THRESHOLD else 'NO converge'})")

# Diagnósticos completos de varias métricas — recibe list[pd.DataFrame]
cadenas = [df1, df2, df3]
tabla = cd.mixing_diagnostics(cadenas, metrics=["max_dev_pct", "cut_edges"])
# → DataFrame: metrica, n_cadenas, n_muestras, rhat, convergido, ess_promedio, acf_lag1_promedio

# Visualizaciones de diagnóstico
cd.plot_trace(cadenas, metrics=["max_dev_pct", "cut_edges"], save_path="trace.png")
cd.plot_acf(serie, max_lag=50, save_path="acf.png")
cd.plot_gelman_rubin_evolution(cadenas, metrics=["max_dev_pct"], save_path="rhat_evol.png")
```

#### Multi-cadena automático

```python
# Correr N cadenas con semillas distintas y calcular diagnósticos
planes, chain_metrics = cd.run_multiple_chains(
    gdf_apc,
    n_chains=4,
    scenario=cd.SCENARIO_APC_FREE,
    n_distritos=8,
    n_steps=5000,
    base_seed=42,
    output_dir="datos/R13/redistritaje/apc_free",
)
tabla = cd.mixing_diagnostics(chain_metrics)
```

#### Bridge R / redist (chiledist.engines.samplers.smc, post-B1)

```python
# Exportar a GeoPackage + generar script R completo para SMC
r_script = cd.generate_redist_script(
    gdf_apc,
    id_col="ID_DIST",
    pop_col="personas",
    n_districts=8,
    output_dir="datos/R13/redist",
    n_sims=1000,
)
# → "datos/R13/redist/run_redist.R" — ejecutar con Rscript

# Importar resultados SMC desde R de vuelta a Python
planes = cd.load_redist_results(
    plans_csv="datos/R13/redist/chiledist_smc_planes.csv",
    id_list=gdf_apc["ID_DIST"].tolist(),
)
# → list[dict] compatible con analyze_ensemble()
```

---

## Redistritaje — Detalles técnicos

### Algoritmo ReCom

En cada paso de la cadena:
1. Selecciona aleatoriamente dos distritos adyacentes
2. Une sus unidades y construye un spanning tree aleatorio
3. Corta el árbol para generar dos nuevos distritos balanceados
4. Acepta el nuevo estado si cumple las restricciones

**Implementación:** `gerrychain 0.3.2` con `functools.partial` para pasar argumentos explícitos.

### Estrategia de dos fases

```
Fase 1 — Warm-up (~500 pasos, solo contigüidad):
    Lleva la partición inicial desde la desviación de arranque
    (~15-40%) hacia el rango objetivo. Se detiene cuando
    la desviación baja al 1.5× la tolerancia objetivo.

Fase 2 — Sampling (n_steps pasos, contigüidad + balance):
    Explora el espacio de planes válidos. El epsilon de ReCom
    se calibra a la desviación real post-warmup.
```

### Robustez para regiones difíciles

El script implementa las siguientes estrategias automáticas:

**Ajuste de `n_distritos`:** si se piden más grupos que `n_dist_apc // 4`, se baja automáticamente al máximo viable.

**`node_repeats` dinámico:**

| Tamaño región (APC) | `node_repeats` |
|---------------------|----------------|
| < 60 | 40 |
| 60–99 | 30 |
| 100–199 | 20 |
| ≥ 200 | 10 |

**`pair_reselection=True`:** si la versión instalada de gerrychain lo soporta, se habilita automáticamente. Permite elegir otro par de distritos cuando el spanning tree no encuentra cortes balanceados.

**Conexión de islas en gerrychain:** `gc.Graph.from_geodataframe` construye su propio grafo sin respetar las conexiones artificiales de chiledist. El script conecta explícitamente los nodos aislados (grado 0) y los componentes desconectados por distancia de centroides.

**`try/except` en warmup y cadena:** `IndexError` y `RuntimeError` de gerrychain son capturados. Si el warmup falla, continúa con la partición inicial. Si la cadena falla a mitad, guarda los planes generados hasta ese punto.

### Restricciones implementadas

| Restricción | Tipo | Parámetro |
|-------------|------|-----------|
| Contigüidad geográfica | Dura | `contiguous` |
| Balance poblacional ±X% | Dura | `--pop-tol` |
| No partir comunas (Ley 18.700) | Solo en modo `legal` / `nacional_comunal` | unidades mínimas = comunas (CUT) |
| Compacidad | Blanda (análisis posterior) | `all_compactness()` |

### Score del plan de referencia

> **Nota metodológica.** En redistritaje MCMC, el resultado estadístico principal es la **distribución** del ensemble completo (`ensemble_stats.csv`), no un plan individual. El script selecciona un _plan de referencia_ conveniente para visualización usando el score heurístico a continuación. Este plan **no es** el plan "óptimo" ni el "correcto" — es simplemente representativo del extremo de la distribución con mejor balance/compacidad.

```
score = -dev_norm + pp_norm - cut_norm

dev_norm = desviación_pob / max(desviaciones)   # menor es mejor
pp_norm  = (PP - min_PP) / (max_PP - min_PP)    # mayor es mejor (cuando disponible)
cut_norm = aristas_cortadas / max(aristas)       # menor es mejor
```

---

## Autocorrelación espacial — Detalles técnicos

### I de Moran global

```
I > 0  →  clustering   (valores similares agrupados espacialmente)
I ≈ 0  →  aleatoriedad espacial
I < 0  →  dispersión   (valores disímiles agrupados)
```

Resultados típicos Chile a nivel distrital nacional:

| Variable | I de Moran | p-value |
|----------|-----------|---------|
| `viviendas` | 0.41 | < 0.001 |
| `densidad_viv_km2` | 0.43 | < 0.001 |
| `polsby_popper` | 0.49 | < 0.001 |

### Mapas LISA

| Cuadrante | Color | Significado geográfico en Chile |
|-----------|-------|--------------------------------|
| HH | Rojo | Clusters urbanos densos |
| LL | Azul | Zonas rurales y Patagonia |
| LH | Azul claro | Periferia de ciudades |
| HL | Naranja | Ciudades intermedias aisladas |

### Correlograma

Implementado con multiplicación de matrices sparse (`A^k`) sin dependencia de `higher_order_sp` (movido en libpysal 4.x). Patrón Chile: decaimiento de ~0.41 (orden 1) a ~0.05 (orden 7) — autocorrelación significativa hasta ~100 km.

---

## Problemas conocidos y soluciones

### gerrychain 0.3.2 en Python 3.11

Los submódulos no son accesibles como atributos del objeto `gc`. Usar imports directos:

```python
from gerrychain.proposals   import recom
from gerrychain.constraints import contiguous
from gerrychain.accept      import always_accept
from gerrychain.tree        import recursive_tree_part
from functools import partial

recom_proposal = partial(
    recom,
    pop_col="viviendas",
    pop_target=ideal_pop,
    epsilon=epsilon,
    node_repeats=10,
)
```

El updater de población debe llamarse exactamente `"population"`:

```python
updaters = {
    "population": gc.updaters.Tally("viviendas", alias="population"),
    "cut_edges":  gc.updaters.cut_edges,
}
```

`within_percent_of_ideal_population` no acepta `pop_col=`:

```python
# Correcto en 0.3.2:
pop_constraint = gc.constraints.within_percent_of_ideal_population(
    partition, POP_TOL   # sin pop_col=
)
```

### Error `aspect must be finite and positive`

Ocurre al plotear con CRS geográfico. Usar `get_optimal_crs` para determinar automáticamente el UTM correcto:

```python
# Automático — elige UTM según el centroide longitudinal del GeoDataFrame
crs = cd.get_optimal_crs(gdf)      # "EPSG:32719" para Chile continental
gdf = gdf.to_crs(crs)
gdf.plot(ax=ax)

# Alternativa manual (UTM 19S cubre todo Chile continental)
gdf = gdf.to_crs("EPSG:32719")
gdf.plot(ax=ax)
```

### Islas sin vecinos en gerrychain

`gc.Graph.from_geodataframe` ignora las conexiones de isla que chiledist establece en `build_graph`, por lo que puede dejar nodos de grado 0. `run_recom` aplica automáticamente la `island_policy` al grafo de gerrychain. Para controlar el comportamiento usa `island_policy` en `ScenarioConfig` o directamente en `run_recom`:

```python
# Conectar cada isla al vecino más cercano (comportamiento por defecto)
plans = cd.run_recom(gdf, ..., island_policy="nearest")

# Solo conectar archipiélagos dentro de 30 km
plans = cd.run_recom(gdf, ..., island_policy="threshold", island_threshold_km=30.0)

# No conectar islas (el grafo puede quedar desconectado — se emite warning)
plans = cd.run_recom(gdf, ..., island_policy="none")
```

### `Failed to find a balanced cut` / `Cannot choose from an empty sequence`

Ocurre en regiones con pocos nodos por grupo (spanning trees lineales sin aristas internas). Soluciones en orden de preferencia:

1. Pedir menos grupos: `--n-distritos 3` para regiones con <40 APC
2. El script ya habilita `pair_reselection=True` automáticamente si disponible
3. El script ya aumenta `node_repeats` para regiones pequeñas
4. Si retorna `status="sin_particion"` (`reason="initialization_search_exhausted"`), es un fallo de la búsqueda de inicialización, no una prueba de inviabilidad — la prueba matemática es `status="infeasible_population"` (`reason="indivisible_unit_exceeds_population_bound"`), emitida por el preflight *antes* de intentar `recursive_tree_part`

### Columnas truncadas en DBF

El formato DBF trunca nombres a 10 caracteres. `chiledist/domain/loader.py` lo normaliza automáticamente. Si se carga manualmente:

```python
distritos = distritos.rename(columns={
    "N_PROVINCI": "N_PROVINCIA",
    "COD_DISTRI": "COD_DISTRITO",
    "TIPO_DISTR": "TIPO_DISTRITO",
})
```

### `higher_order_sp` no disponible (libpysal 4.x)

El módulo fue movido. El correlograma de chiledist no depende de él — usa multiplicación de matrices sparse directamente:

```python
A_k = A.copy()
for k in range(1, max_order + 1):
    if k > 1:
        A_next = A_k.dot(A)
        A_k = (A_next > 0).astype(float)
        A_k.setdiag(0)
    W_norm = diags(1 / row_sums).dot(A_k)
    w_k = WSP(W_norm).to_W()
    mi_k = Moran(y, w_k, permutations=199)
```

### Bugs corregidos (agosto 2026)

Los siguientes problemas fueron detectados y corregidos durante la validación post-B1; se listan aquí para trazabilidad, no son problemas abiertos.

| Bug | Estado | Detalle |
|---|---|---|
| `reock()` incompatible con shapely 2.x | **RESUELTO** | `scripts/recalcular_reock.py` permite recalcular Reock en `ensemble_stats.csv` de corridas antiguas sin re-correr ReCom completo. Ver `tests/test_metrics.py` (`test_reock_circulo_perfecto`, `test_reock_cuadrado_unitario`, `test_reock_l_shape_en_rango`). |
| `normalize_party_name()` no toleraba mayúsculas/acentos en el cruce D'Hondt binivel | **RESUELTO** | Necesario para cruzar nombres de partido entre SERVEL (mayúsculas sin tildes) y `pacto_map_2025.json` (formato título con tildes). Ver `chiledist/domain/utils.py` y `tests/test_electoral_binivel.py`. |
| `Puntos_Edificacion_Rural` sin `COD_DISTRITO` (solo CUT a nivel comuna) rompía el pipeline en regiones sin cobertura urbana completa | **RESUELTO** | Manejado como proxy rural especial en `chiledist/domain/loader.py`. Ver `tests/test_integration_r11.py`. |
| `datos/asignacion_vigente.json`: 8 CUT de la Región Metropolitana mal asignados a distrito | **RESUELTO** | Corrección validada indirectamente: la asignación corregida reproduce 96/96 combinaciones (distrito, pacto) contra SERVEL 2025 (ver `scripts/validar_dhondt.py`) y 24/28 distritos contra TRICEL 2025 (ver "Validación electoral" más arriba, `VALIDATION_REPORT.md`). |

---

## Dependencias

| Paquete | Versión | Uso |
|---------|---------|-----|
| geopandas | 1.1.3 | Lectura y manipulación de shapefiles |
| pyogrio | 0.12.1 | Backend rápido de I/O geoespacial |
| shapely | 2.1.2 | Geometrías y operaciones espaciales |
| fiona | 1.10.1 | Lectura de formatos vectoriales |
| pyproj | 3.7.2 | Reproyección de coordenadas |
| pandas | 3.0.3 | Tablas y manipulación de datos |
| numpy | 2.4.6 | Álgebra lineal y arrays |
| scipy | 1.17.1 | Matrices sparse CSR |
| networkx | 3.6.1 | Grafos y análisis de redes |
| matplotlib | 3.11.0 | Visualización |
| libpysal | 4.14.1 | Pesos espaciales Queen/Rook |
| esda | 2.6.0 | I de Moran, LISA, G* |
| pyarrow | >=14.0.0 | `PlanEnsemble.save()` / `assignments.parquet` |
| scikit-learn | 1.9.0 | Dependencia de gerrychain |
| gerrychain | 0.3.2 | Redistritaje ReCom |
| pyyaml | >=6.0 | Escenarios YAML (`load_scenario`/`save_scenario`) |

---

## Limitaciones metodológicas

- **`viviendas` como proxy de población.** El conteo de viviendas del APC 2023 es un proxy de población, no una medida directa. La relación viviendas/personas varía por densidad (≈2.1 en RM, ≈2.8 en zonas rurales). Usar Censo 2024 (`pop_col="personas"`) o padrón SERVEL (`pop_col="inscritos"`) para resultados publicables. El `ScenarioConfig.validate()` emite una advertencia al usar `viviendas` con restricciones activas.

- **Contiguidad artificial de islas.** Las conexiones de isla (`island_policy`) garantizan factibilidad algorítmica, no contigüidad electoral. Los planes con unidades insulares (Chiloé, Aysén, Magallanes) deben verificarse manualmente antes de presentarlos como propuestas.

- **Redistritaje regional ≠ redistritaje nacional.** Los análisis por región son independientes y no producen un plan nacional coherente. El modo `nacional_comunal` corre ReCom sobre 345 comunas con `n_districts` arbitrario — no reproduce el mapa de 28 distritos legales.

- **El "plan de referencia" no es el plan óptimo.** Es un representante del extremo de mayor score heurístico del ensemble, útil para visualización. El resultado estadístico del análisis es la distribución completa (`ensemble_stats.csv`).

- **R-hat < 1.1 indica convergencia, no representatividad distribucional.** Con propuestas ReCom y restricciones duras, la distribución empírica puede diferir de la uniforme sobre planes válidos. Para verificación, comparar con resultados SMC como referencia.

- **Bridge SMC requiere R externo.** `generate_redist_script()` produce un script R pero no lo ejecuta. El flujo Python→R→Python requiere R instalado con el paquete `redist`. La librería emite una advertencia si `Rscript` no está en el PATH.

- **Sin tests automatizados.** El proyecto no tiene suite de tests. Los resultados dependen de la integridad de los datos de entrada (APC 2023, Censo 2024, padrón SERVEL).

---

## Estado de madurez

### Funciones de la librería — validadas con suite automatizada

| Módulo | Función | Tests | Estado |
|--------|---------|-------|--------|
| `electoral` | `dhondt` | 8 | ✓ validado |
| `electoral` | `dhondt_binivel` | 5 | ✓ validado |
| `electoral` | `personas_por_escano` | 7 | ✓ validado |
| `electoral` | `peso_relativo_del_voto` | 7 | ✓ validado |
| `electoral` | `comparar_magnitudes` | 9 | ✓ validado |
| `electoral` | `plan_electoral_metrics` | 24 | ✓ validado |
| `split_metrics` | `pop_afectada_pct` | 7 | ✓ validado |
| `split_metrics` | `plan_split_metrics` | 9 | ✓ validado |
| `scenario_comparison` | `pareto_frontier_nd` | 10 | ✓ validado |
| `scenario_comparison` | `ranking_concordance` | 8 | ✓ validado |
| `scenario_comparison` | `compare_sensitivity` | 10 | ✓ validado |
| `fairshare` | `fair_share_matrix` (district + biproportional) | 17 | ✓ validado |
| `fairshare` | `results_to_matrix` | 6 | ✓ validado |
| `fairshare` | `l1_distance_fair_share` | 6 | ✓ validado |
| `fairshare` | `l2_distance_fair_share` | 5 | ✓ validado |
| `fairshare` | `max_cell_deviation` | 6 | ✓ validado |
| `fairshare` | `fair_share_summary` | 12 | ✓ validado |
| `electoral_ensemble` | `run_electoral_ensemble` | 15 | ✓ validado |
| `electoral_ensemble` | `ensemble_gallagher` | 5 | ✓ validado |
| `electoral_ensemble` | `ensemble_seat_bonus` | 6 | ✓ validado |
| `electoral_ensemble` | `ensemble_enp` | 4 | ✓ validado |
| `electoral_ensemble` | `ensemble_effective_threshold` | 5 | ✓ validado |
| `electoral_ensemble` | `summarize_electoral_ensemble` | 6 | ✓ validado |
| `electoral_ensemble` | `plot_ensemble_histogram/violin/ecdf` | 12 | ✓ validado |
| `electoral_ensemble` | `_dist_stats`, `_normalize_assignments` | 8 | ✓ validado |
| `pareto_sweep` | `sweep_split_penalty` | 9 | ✓ validado |
| `pareto_sweep` | `build_tradeoff_frontier` | 14 | ✓ validado |
| `pareto_sweep` | `detect_knee_point` | 11 | ✓ validado |
| `pareto_sweep` | `plot_tradeoff_curve` | 7 | ✓ validado |
| `pareto_sweep` | `summarize_tradeoff` | 9 | ✓ validado |
| `pareto_sweep` | constants (`SWEEP_METRICS`, `METRIC_DIRECTIONS`, `METRIC_LABELS`) | 4 | ✓ validado |
| `malapportionment` | `samuels_snyder_index` | 10 | ✓ validado |
| `malapportionment` | `loosemore_hanby_malapportionment` | 4 | ✓ validado |
| `malapportionment` | `gini_personas_por_escano` | 10 | ✓ validado |
| `malapportionment` | `max_min_representation_ratio` | 8 | ✓ validado |
| `malapportionment` | `malapportionment_summary` | 8 | ✓ validado |
| `malapportionment` | `compare_malapportionment_plans` | 6 | ✓ validado |
| `malapportionment` | `international_comparison` | 7 | ✓ validado |
| `malapportionment` | `BENCHMARK_MALAPPORTIONMENT` | 4 | ✓ validado |
| `malapportionment` | `plot_pxe_distribution / ranking / international` | 9 | ✓ validado |

Total: **421 tests** pasan en CI sin datos externos (`pytest tests/ -q`).
(398 tests unitarios + 23 tests de integración de scripts; los tests de scripts requieren ~80 s por subprocesos.)

### Scripts — ejecutables en modo demo o con fixtures

| Script | Modo sin datos reales | Estado |
|--------|-----------------------|--------|
| `malapportionment.py` | `--demo --skip-viz` | ✓ validado |
| `electoral_analysis.py` | `--demo --skip-viz` | ✓ validado |
| `pareto_sweep.py` | `--skip-run --no-anchors` con fixture CSVs | ✓ validado |
| `run_chains.py` | funciones internas con DataFrames sintéticos | ✓ validado |
| `compare_scenarios.py` | `--skip-run` con ensemble CSVs existentes | integración manual |
| `redistritaje.py` | requiere SHP_APC2023 | solo con datos reales |
| `smc_pipeline.py` | requiere SHP_APC2023 + R/redist | solo con datos reales |

### Análisis completos (H1–H5) — requieren datos externos

Todos los análisis de las hipótesis del paper dependen de los datos del INE/SERVEL
que **no se distribuyen con esta librería**:

| Datos | Fuente | Usado en |
|-------|--------|----------|
| SHP_APC2023 (shapefiles de distritos APC) | INE — solicitar en geodatos.ine.cl | redistritaje.py, smc_pipeline.py (H1, H5) |
| Base_manzana_entidad_CPV24.csv (~24 MB) | INE — Censo 2024 | redistritaje.py con `--censo-path` |
| Resultados electorales por CUT y partido (cualquier elección: 2021, 2025, …) | SERVEL — Open Data | malapportionment.py, electoral_analysis.py (H3, H4) |

Para reproducir H1–H5 en su totalidad, sigue el flujo descrito en `setup_env.sh`.

### Limitaciones conocidas del estado actual

- `pareto_sweep.py` con `--skip-run` y sin fixture CSVs: imprime advertencia y termina sin crear output (comportamiento correcto, no es un error).
- El escenario `legal_comunas` puede fallar el preflight de factibilidad poblacional (`status: "infeasible_population"`) o agotar la búsqueda de partición inicial (`status: "sin_particion"`) para regiones donde una comuna indivisible por sí sola excede la tolerancia poblacional al `n_districts` solicitado (ver la tabla de estados en la sección de `redistritaje.py`, y `compare_scenarios.py` para cómo se refleja esto en una comparación marcada `INCOMPLETE`). No es un bug: es exactamente lo que el preflight está diseñado para detectar.
- Los tests de scripts subprocess son lentos (~80 s) porque cada test arranca un proceso Python nuevo. Se recomienda ejecutar la suite completa una vez, no en modo `--watch`.

---

## Referencias

### Software
- **ALARM Project** — Algorithmic Redistricting and Mapping, Harvard: https://alarm-redist.org
- **redist** (R) — SMC para redistritaje: https://redist.alarm-redist.org
- **gerrychain** (Python) — ReCom MCMC: https://gerrychain.readthedocs.io

### Metodología
- DeFord, D., Duchin, M., & Solomon, J. (2021). Recombination: A family of Markov chains for redistricting. *Harvard Data Science Review*, 3(1).    
- McCartan, C., & Imai, K. (2023). Sequential Monte Carlo for sampling balanced and compact redistricting plans. *Annals of Applied Statistics*, 17(4).
- Polsby, D. D., & Popper, R. D. (1991). The third criterion: Compactness as a procedural safeguard against partisan gerrymandering. *Yale Law & Policy Review*, 9(2), 301–353.
- Gallagher, M. (1991). Proportionality, disproportionality and electoral systems. *Electoral Studies*, 10(1), 33–51.

### Marco legal Chile
- **Ley 18.700** — Ley Orgánica Constitucional sobre Votaciones Populares y Escrutinios
- **Ley 20.840** — Reforma electoral 2015; Art. 179 define los 28 distritos y magnitudes vigentes
- **APC 2023** — INE Chile: https://www.ine.gob.cl
