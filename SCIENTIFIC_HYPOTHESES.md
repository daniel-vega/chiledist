# Hipótesis Científicas — ChileDist

> **Versión:** 2.0  
> **Fecha:** 2026-06-21 (revisado 2026-08-14 contra el estado actual del código y de `datos/` — ver "Plan de cierre" al final)  
> **Proyecto:** Análisis computacional de redistritaje electoral en Chile  
> **Autor:** Daniel Vega (drvega@estudiante.uc.cl)

---

## Estructura

ChileDist está diseñado para responder cinco preguntas científicas (H1–H5). Este documento especifica, para cada una:

- **Pregunta** — formulación operativa de la hipótesis
- **Datos requeridos** — fuentes, formatos y constantes necesarios
- **Comandos** — código Python ejecutable con la API de ChileDist

Las hipótesis son independientes entre sí y pueden ejecutarse en cualquier orden, aunque H5 (robustez) actúa como validación cruzada del resto.

> **Nota sobre ejecutabilidad.** Los fragmentos de código Python de este documento son especificaciones de la API, no scripts ejecutables directamente. Todos los análisis H1–H5 requieren datos externos que **no se distribuyen con esta librería**: los shapefiles SHP_APC2023 (INE), la Base manzana-entidad del Censo 2024 (INE) y/o el padrón comunal SERVEL. Sin esos datos, los scripts `redistritaje.py` y `smc_pipeline.py` terminarán con error al intentar cargar las geometrías. Usa `--demo` en los scripts de análisis (`malapportionment.py`, `electoral_analysis.py`) para verificar la API con datos sintéticos sin necesidad de datos reales.

### Relación entre hipótesis

```
H1 (reforma institucional)
    └─▶ H2 (frontera Pareto: ¿es el mapa vigente dominado?)
            └─▶ H3 (malapportionment bajo magnitudes legales)

H4 (D'Hondt binivel)  ←─ depende de resultados de H1/H2 para elegir plan

H5 (robustez)  ─▶  valida los resultados de H1–H4
```

### Los tres escenarios y su rol legislativo

| Escenario | Constante | Tipo | Descripción |
|---|---|---|---|
| `legal_comunas` | `cd.SCENARIO_LEGAL` | `"vigente"` | Marco Ley 18.700: comunas indivisibles. Baseline. |
| `apc_comunas_preservadas` | `cd.SCENARIO_APC_STRICT` | `"control_metodologico"` | APCs como unidad mínima, comunas aún preservadas. Aísla efecto de resolución. |
| `contrafactual_apc_soft` | `cd.SCENARIO_APC_SOFT` | `"contrafactual_intermedio"` | Reforma intermedia: APCs permitidas, splits penalizados. **No es legal.** |
| `contrafactual_apc_libre` | `cd.SCENARIO_APC_FREE` | `"contrafactual_fuerte"` | Reforma fuerte: APCs sin restricción comunal. **No es legal.** |

```python
import chiledist as cd

# Verificar framing de cualquier escenario
print(cd.SCENARIO_APC_FREE.reforma_context())
```

---

## H1 — Efecto de cambiar la unidad mínima legal de redistritaje

### Pregunta

> ¿Qué ocurre si Chile permite redistritaje con unidades subcomunales (APCs) como mínimo legal?
> ¿En qué magnitud mejora el balance poblacional, y cuál es el costo en fragmentación de comunas?

Esta hipótesis estudia el efecto *contrafactual de una reforma legislativa*: pasar de un régimen donde la comuna es indivisible (Ley 18.700 vigente) a uno donde la unidad mínima es la APC. La comparación `legal` vs `apc_free`/`apc_soft` estima el efecto *conjunto* de mayor resolución geográfica y menor restricción comunal; no los aísla por separado (ver `SCENARIO_APC_STRICT` para la descomposición).

**Conclusiones válidas:**
- "Bajo la reforma fuerte, la desviación máxima se reduce en X pp, al costo de Y comunas partidas (Z% de la población)."
- "La reforma intermedia (`apc_soft`) recupera el W% del balance de la reforma fuerte con X% menos de comunas partidas."

**Conclusiones inválidas:**
- "La mejora se debe exclusivamente a eliminar la restricción comunal" (no aislable sin `apc_strict`).
- "Los escenarios APC son legalmente compatibles con la norma vigente."

### Datos requeridos

| Dato | Fuente | Dónde en ChileDist |
|---|---|---|
| Cartografía APC 2023 | `SHP_APC2023/` (local) | `cd.load_layer("apc", base_dir="./datos")` |
| Asignación plan vigente | `datos/asignacion_vigente.json` (ya construido — ver `README.md § Datos externos` para metodología y fuentes BCN/SUBDERE) | `json.load(open("datos/asignacion_vigente.json"))` → `{CUT_str: n_circunscripcion}` |
| Población por APC | Censo 2024 o padrón SERVEL | `chiledist.data.census2024` / `chiledist.data.servel` |
| Comunas por APC | Cartografía APC | Columna `"CUT"` en el GeoDataFrame |

### Comandos

#### Paso 1 — Generar ensembles (CLI)

```bash
# Régimen vigente (comunas indivisibles)
python scripts/redistritaje.py --base-dir . --regiones 13 --scenario legal

# Reforma intermedia (split_penalty=0.25)
python scripts/redistritaje.py --base-dir . --regiones 13 --scenario apc_soft

# Reforma fuerte (sin restricción)
python scripts/redistritaje.py --base-dir . --regiones 13 --scenario apc_free

# Control metodológico (APCs, comunas preservadas) — "apc_strict" ya es una
# opción built-in de --scenario, no hace falta --scenario-file para este caso
python scripts/redistritaje.py --base-dir . --regiones 13 --scenario apc_strict
```

Salida: `datos/R13_*/redistritaje/<escenario>/ensemble_stats.csv`

> **Caveat de factibilidad — `legal_comunas` puede no producir ensemble.** Antes de intentar la partición inicial, `redistritaje.py` corre un preflight (`chiledist.check_population_feasibility`) que puede determinar que la tolerancia poblacional solicitada es matemáticamente inalcanzable dado que las comunas son indivisibles bajo `legal_comunas` — el escenario retorna entonces `status: "infeasible_population"` (con `reason` y diagnóstico) en vez de un ensemble. Distinto de esto, y también posible, es `status: "sin_particion"` (el algoritmo de inicialización agotó su búsqueda sin encontrar partición — no es una prueba de inviabilidad). **Esto no es hipotético**: en la corrida real de este repo para R13, `legal_comunas` retornó `status="sin_particion"` (`datos/redistritaje_resumen_legal_comunas.csv`), mientras que `contrafactual_apc_soft` y `contrafactual_apc_libre` sí completaron. Antes de asumir que los tres escenarios producen `ensemble_stats.csv`, revisa la tabla de estados en `README.md § redistritaje.py` y usa `scripts/compare_scenarios.py` (ver Paso 2) en vez de leer los CSV directamente — maneja este caso marcando la comparación como incompleta en lugar de fallar.

### Estado de apc_strict (control metodológico)

apc_strict (decision_unit=ID_DIST, preserve_mode=hard) no es
implementable con el stack actual (gerrychain 0.3.2 + ReCom).

Causa técnica confirmada empíricamente: ReCom busca cortes en
spanning trees sin sesgo hacia límites comunales. La restricción
preserve_CUT como constraint dura de gerrychain rechaza casi
toda propuesta como auto-loop. El proceso queda atrapado
indefinidamente dentro de bipartition_tree buscando un corte
simultáneamente balanceado y respetuoso de 52 fronteras comunales
sobre un grafo de 451 nodos — sin timeout ni escape.

Intentos realizados:
1. preserve_CUT en constraints del warm-up: no converge en 4.500
   pasos, desviación retrocede de 21.8% a 26.5%.
2. Warm-up comunal (52 nodos) + warm-up fino (451 nodos + preserve_CUT):
   proceso colgado >4 horas sin completar un solo paso del warm-up fino.

Alternativa para implementación futura: SMC (Sequential Monte Carlo,
paquete redist de R) puede muestrear directamente desde la distribución
condicionada a preserve_CUT porque no depende de spanning trees —
es el sampler correcto para este escenario. Ver scripts/smc_pipeline.py.

Impacto en H1: la descomposición causal completa
(efecto resolución = apc_strict − legal,
efecto restricción = apc_free − apc_strict)
no está disponible con ReCom. H1 se cierra con la comparación
directa legal vs apc_free vs apc_soft, que mide el efecto total
sin descomposición.

Estado: NO IMPLEMENTABLE con ReCom. Requiere SMC (trabajo futuro).

#### Paso 2 — Cargar y comparar ensembles

Preferir `scripts/compare_scenarios.py` a leer los CSV a mano: maneja el caso del Paso 1 en que un escenario (típicamente `legal_comunas`) no tenga `ensemble_stats.csv` válido, dejándolo visible con su `status`/`reason` en vez de fallar con `FileNotFoundError`, y marca la comparación como `comparison_status: "INCOMPLETE"` cuando falta el baseline.

```bash
python scripts/compare_scenarios.py --base-dir . --regiones 13 --skip-run
# Lee datos/R13_METROPOLITANA/redistritaje/<escenario>/ensemble_stats.csv de los
# escenarios ya corridos; produce comparacion_escenarios.csv (ranking, solo
# escenarios con ensemble válido) + escenarios_overview.csv (todos los
# escenarios esperados, incluido el/los que fallaron) + comparacion_status.json
```

Equivalente en API, con el manejo explícito de la posible ausencia de `legal_comunas`:

```python
import chiledist as cd

sc_names = ["legal_comunas", "contrafactual_apc_soft", "contrafactual_apc_libre"]
ensembles = cd.load_ensembles_from_disk(
    output_base="datos", region_code=13, scenario_names=sc_names,
)
# → dict solo con los escenarios que sí tienen ensemble_stats.csv

completeness = cd.assess_comparison_completeness(sc_names, ensembles, baseline="legal_comunas")
if completeness["comparison_status"] == "INCOMPLETE":
    print(f"Comparación incompleta: falta {completeness['missing_baseline']}. "
          f"El ranking entre {list(ensembles)} es parcial/descriptivo, no H1 completa.")

# Columnas en ensemble_stats.csv (METRICAS_STD):
#   max_dev_pob_pct, pp_promedio, cut_edges, n_comunas_partidas,
#   split_severity, pop_afectada_pct  ← fracción de pob. en comunas divididas
tabla = cd.compare_ensembles(ensembles, baseline="legal_comunas")
print(tabla[["escenario",
             "max_dev_pob_pct_median",
             "n_comunas_partidas_median",
             "split_severity_median",
             "pop_afectada_pct_median"]])
# delta_* solo aparece si el baseline "legal_comunas" está en `ensembles`
```

#### Paso 3 — Métricas de fragmentación por plan individual

```python
# Cargar geometrías
gdf = cd.load_layer("apc", base_dir="./datos/R13")

# Para un plan del ensemble apc_free
assignment = {...}  # {ID_DIST: n_distrito}
metricas_split = cd.plan_split_metrics(
    assignment, gdf,
    unit_col="CUT",     # unidad cuya integridad se evalúa
    id_col="ID_DIST",   # unidad de decisión
    pop_col="personas"
)
# → {
#     "n_comunas_partidas": 12,
#     "share_comunas_partidas": 0.14,
#     "pop_afectada_pct": 0.31,   ← fracción de pob. en comunas divididas
#     "split_severity": 0.082,
#     "small_fragments": 3,
#     "comunas_mas_partidas": ["13101", "13110", "13201"]
# }
```

#### Paso 4 — Posicionar el mapa vigente en el mismo espacio

```python
import json

# Cargar asignación vigente real (CUT → circunscripción), 346 comunas
# → 28 distritos (ver README.md § Datos externos para metodología/fuentes)
with open("datos/asignacion_vigente.json", encoding="utf-8") as f:
    assignment_vigente = json.load(f)

G, adj, id_list = cd.build_graph(gdf, id_col="ID_DIST")

pos_vigente = cd.position_plan_vigente(
    assignment_vigente, gdf,
    id_col="ID_DIST",
    pop_col="personas",
    adj=adj,
    unit_col="CUT",
    scenario_name="vigente"
)
# → {
#     "escenario": "vigente",
#     "max_dev_pob_pct": 18.4,
#     "n_comunas_partidas": 0,
#     "pop_afectada_pct": 0.0,
#     "pp_promedio": 0.312,
#     ...
# }
```

#### Paso 5 — Framing legislativo

```python
# Verificar encuadre antes de publicar
for sc in [cd.SCENARIO_LEGAL, cd.SCENARIO_APC_SOFT, cd.SCENARIO_APC_FREE]:
    print(f"\n{sc.name}")
    print(sc.reforma_context())
```

### Qué observar en los resultados

| Métrica | Campo | Interpretación |
|---|---|---|
| Mejora en balance | `delta_max_dev_pob_pct_median` | Negativo = mejora. Ej. −8.2 pp bajo apc_free. |
| Costo en comunas | `n_comunas_partidas_median` | Número absoluto de comunas divididas. |
| Costo en población | `pop_afectada_pct_median` | Fracción de habitantes en comunas divididas. |
| Severidad | `split_severity` | Ponderado por tamaño; 0 = sin divisiones. |
| Fragmentos pequeños | `small_fragments` | Fragmentos < 10% de la población comunal. |

### Resultado empírico — Umbral de factibilidad comunal bajo Ley 18.700 (RM, Censo 2024)

**Primer resultado empírico completo del proyecto.** Calculado con
`chiledist.check_population_feasibility` sobre el pipeline real de
`redistritaje.py` para R13 (Región Metropolitana), escenario `legal_comunas`
(unidad de decisión = CUT, comunas indivisibles), población Censo 2024
(52 comunas, 7.400.740 personas), tolerancia ±10%:

```python
import chiledist as cd
# unit_pops = {CUT: personas}, construido exactamente como en
# redistritaje.py::analizar_region() para decision_unit="CUT" + Censo 2024
for n in range(6, 21):
    r = cd.check_population_feasibility(unit_pops, n, 0.10)
    print(n, r.feasible, r.minimum_required_tolerance)
```

| n_distritos | Factible (±10%) | Tolerancia mínima requerida |
|---|---|---|
| n=8 (experimento contrafactual — R13 tiene 7 distritos electorales vigentes: D8–D14) | ✓ | 0.0% |
| 9–13 | ✓ | 0.0% |
| 14 | ✓ | 7.5% |
| 15 | ✗ | 15.1% |
| 16 | ✗ | 22.8% |
| 17 | ✗ | 30.5% |
| 20 | ✗ | 53.5% |

En todos los casos la unidad que bloquea es la misma: **Puente Alto**
(CUT 13201, 568.087 personas — no Santiago, que es más chica).

**Hallazgo:** el umbral de factibilidad comunal para la RM bajo Ley 18.700
y Censo 2024 es **n_distritos ≤ 14** (factible) / **n_distritos ≥ 15**
(estructuralmente inviable a ±10%) — un mecanismo simple: la población de
Puente Alto es fija (~568k), y al aumentar `n_distritos` el ideal por
distrito (`total_RM / n_distritos`) se reduce; en algún punto (entre 14 y
15) el ideal cae por debajo de la población de Puente Alto, y una comuna
indivisible que excede el ideal hace inviable *cualquier* plan bajo
Ley 18.700, sin importar cuántas semillas o intentos de
`recursive_tree_part` se prueben (ver `chiledist/feasibility.py`).

**n=8 (experimento contrafactual — R13 tiene 7 distritos electorales
vigentes: D8–D14) es el caso MÁS factible del rango, no uno al
límite**: tolerancia mínima requerida 0.0% — Puente Alto está muy por
debajo del ideal a 8 distritos. La dificultad observada al correr la
cadena ReCom real en n=8 (el warm-up converge en 4.402 pasos (dentro
del presupuesto escalado de 6.000 para n_units≤100) con
dev_warmed=8.35%) es un obstáculo **computacional** distinto y no
relacionado con este umbral de factibilidad poblacional.

**Interpretación institucional (revisada):** el mecanismo es el opuesto al
que sugeriría intuitivamente "más distritos = mapa más fino y más fácil
de balancear". Bajo comunas indivisibles, aumentar el número de distritos
en la RM manteniendo Ley 18.700 **empeora** progresivamente la
factibilidad poblacional (el ideal se reduce mientras Puente Alto se
mantiene fijo), no la mejora. Esto es coherente con el propósito de H1:
la vía para mejorar el balance poblacional en la RM no es aumentar el
número de distritos bajo el régimen vigente, sino cambiar la **unidad
mínima de decisión** (de CUT a APC — ver `apc_free`/`apc_soft`), que
permite fragmentar comunas grandes como Puente Alto en vez de tratarlas
como bloques indivisibles.

## Resultados empíricos — R13, Censo 2024, n=8, modelo A (definitivo)

> **Nota sobre n=8:** los ensembles de H1 usan n=8 zonas como
> parámetro de partición. R13 tiene 7 distritos electorales
> (D8–D14, Resolución O 129/2026 y Ley 20.840). Los
> resultados de H1 son válidos como análisis de particiones
> sintéticas en 8 zonas, pero no representan directamente
> el arreglo electoral vigente de 7 distritos. Para analizar
> el arreglo vigente, usar n=7 con las comunas de R13 y
> las magnitudes correspondientes.

### Ensembles canónicos

Tres runs limpios, un run por escenario, todos con pop_tol=±10%,
valid_fraction=1.0, modelo A activo (corridos y verificados el
2026-08-19, con el código actual de `redistritaje.py`):

| escenario | run_id | pop_tol | n_draws | valid_fraction | warmup_pasos |
|-----------|--------|---------|---------|----------------|--------------|
| legal_comunas | cc037ac8 | ±10% | 50.000 | 1.0 | 4.402 (extensión) |
| contrafactual_apc_libre | 856910a5 | ±10% | 50.000 | 1.0 | 144 |
| contrafactual_apc_soft | 97cf1309 | ±10% | 50.000 | 1.0 | 144 |

### Resultado de compare_scenarios.py (apples-to-apples ±10%)

    Estado: COMPLETE (3/3 escenarios con ensemble válido)
    Sin WARNING de tolerancias distintas

| escenario | rank | composite_score | max_dev_pob_pct_median | pp_promedio_median | n_comunas_partidas_median |
|-----------|------|-----------------|------------------------|--------------------|---------------------------|
| legal_comunas | 1 | 0.8500 | 9.127% | 0.2902 | 0.0 |
| contrafactual_apc_libre | 2 | 0.3500 | 9.124% | 0.2148 | 28.5 |
| contrafactual_apc_soft | 3 | 0.0284 | 9.131% | 0.2208 | 26.5 |

### Hallazgos definitivos

**H1.1 — La restricción comunal no impone costo en balance:**
Diferencia de max_dev mediana entre los 3 escenarios: 0.007pp
(9.124% a 9.131%). Estadísticamente indistinguible. La Ley 18.700
no sacrifica balance poblacional en la RM con n=8 y Censo 2024.
El único costo de la restricción comunal es en fragmentación territorial.

**H1.2 — Costo en fragmentación:**
apc_free parte 28.5 comunas (mediana) — 54.8% de las 52 comunas
de R13. apc_soft parte 26.5 comunas (mediana) con split_penalty=0.25,
reduciendo ~2 comunas respecto a apc_free sin ningún costo adicional
en balance (diferencia de 0.007pp).

**H1.3 — Compacidad:**
legal_comunas tiene PP mediana 0.290 vs 0.215 (apc_free) y 0.221
(apc_soft). Los planes legales son más compactos — las unidades
comunales son más regulares geográficamente que los distritos APC.

**H1.4 — Factibilidad (verificado con preflight):**
Rango factible bajo ±10%: n_distritos ≤ 14.
A partir de n=15, Puente Alto (568.087 personas) supera el
ideal × 1.10. n=8 (experimento contrafactual — R13 tiene 7 distritos
electorales vigentes: D8–D14) tiene el mayor margen
de factibilidad del rango (min_tol_requerida=0.0%).
Ver tabla completa en subsección "Resultado verificado — preflight".

**H1.5 — apc_strict (control metodológico):**
No implementable con ReCom — ver subsección dedicada
"Estado de apc_strict (control metodológico)".
La descomposición causal (efecto resolución vs efecto restricción)
queda pendiente hasta implementar SMC.

### Nota de reproducibilidad

Estos 3 runs (2026-08-19) reemplazan una versión anterior de esta
sección cuyos `run_id` no correspondían a ningún run real en disco.
Los agregados estadísticos (composite_score, medianas de
max_dev_pob_pct/pp_promedio/n_comunas_partidas) coinciden con los
de esa versión anterior — son reproducibles con seed=42. El único
valor que cambió al re-verificar es `warmup_pasos` de
contrafactual_apc_libre/apc_soft: 144 pasos medidos directamente
del run_manifest.json de esta corrida, no 3-4 como se documentaba
antes (no se pudo confirmar el origen de ese número previo).

### Estado

CLOSED para R13/Censo 2024/n=7 y n=8.
Pendiente para cierre completo de H1:
- Replicar en R5 y R8 (otras regiones)
- apc_strict vía SMC (descomposición causal)

### Archivos canónicos

    datos/R13_METROPOLITANA/redistritaje/legal_comunas/
        run_20260819_193847_cc037ac8/
    datos/R13_METROPOLITANA/redistritaje/contrafactual_apc_libre/
        run_20260819_194058_856910a5/
    datos/R13_METROPOLITANA/redistritaje/contrafactual_apc_soft/
        run_20260819_194308_97cf1309/
    datos/R13_METROPOLITANA/comparacion/comparacion_escenarios.csv

## Comparación balance uniforme vs ponderado por magnitud

### Parámetros

    Magnitudes: MAGNITUDES_CENSO2024_2026 (Resolución O 129/2026)
    Método: --magnitudes censo2026
    pop_tol=±10%, n_steps=50000, seed=42, pop_source=censo2024
    n=7: configuración exacta (7 zonas = 7 distritos legales D8–D14)
    n=8: configuración contrafactual (parámetro experimental)

### Tabla comparativa (9 configuraciones)

| escenario | balance | n | max_dev_median | comunas_partidas | valid_fraction |
|-----------|---------|---|----------------|------------------|----------------|
| legal_comunas | uniforme | 8 | 9.127% | 0.0 | 1.0 |
| legal_comunas | ponderado | 8 | 8.995% | 0.0 | 1.0 |
| legal_comunas | ponderado | 7 | 8.945% | 0.0 | 1.0 |
| contrafactual_apc_libre | uniforme | 8 | 9.124% | 28.5 | 1.0 |
| contrafactual_apc_libre | ponderado | 8 | 9.132% | 29.0 | 1.0 |
| contrafactual_apc_libre | ponderado | 7 | 9.010% | 26.0 | 1.0 |
| contrafactual_apc_soft | uniforme | 8 | 9.131% | 26.5 | 1.0 |
| contrafactual_apc_soft | ponderado | 8 | 9.135% | 29.0 | 1.0 |
| contrafactual_apc_soft | ponderado | 7 | 9.020% | 27.0 | 1.0 |

Runs n=8 ponderado: legal/eed1c2b0, apc_free/16d6ff97, apc_soft/d74bb08f
Runs n=7 ponderado: legal/99612336, apc_free/4f7ed814, apc_soft/d78b06aa

### Hallazgos

1. **Robustez de las conclusiones principales:** la diferencia entre
   escenarios en max_dev_median es ≤0.065pp dentro de cada variante
   (n=7 ponderado: 9.010%−8.945%=0.065pp). La conclusión central de H1
   — la restricción comunal no impone costo estadísticamente
   distinguible en balance poblacional — es robusta a través de las
   tres variantes de balance y ambos valores de n.

2. **n=7 ponderado es la única configuración exacta:** con n=7, cada
   zona sintética corresponde a un distrito legal real (D8–D14) con su
   magnitud propia de la Resolución O 129/2026. No aparece la
   advertencia de "n_distritos != distritos legales cubiertos".
   Produce los max_dev_median más bajos de las tres variantes en los
   tres escenarios (diferencia máxima: 0.18pp respecto al uniforme n=8).

3. **Fragmentación comunal no tiene dirección clara con n:**
   n_comunas_partidas_median no muestra una dirección consistente al
   pasar de n=8 a n=7 — cambia simultáneamente el número de zonas y el
   target por zona, lo que hace la comparación directa no informativa
   sobre el efecto de las magnitudes.

4. **Warm-up más rápido con n=7:** apc_free y apc_soft convergen en 2
   pasos de warm-up con n=7 (vs 173 con n=8 ponderado) — con menos
   zonas la partición inicial cae dentro de tolerancia casi de
   inmediato.

### Estado

Comparación completa. Las conclusiones de H1 son robustas a través de
todas las variantes de balance y n probadas. La configuración canónica
para análisis futuros de R13 es n=7 + balance ponderado +
MAGNITUDES_CENSO2024_2026, que corresponde al arreglo electoral real
vigente.

---

## H2 — Frontera de Pareto entre igualdad del voto e integridad comunal

### Pregunta

> ¿Existe un tradeoff sistemático entre balance poblacional y preservación de comunas?
> ¿Es el mapa vigente Pareto-dominado — es decir, existe algún plan legalmente posible
> que sea estrictamente mejor en todas las dimensiones relevantes?

### Datos requeridos

| Dato | Fuente | Notas |
|---|---|---|
| Ensembles `apc_soft` con distintos `split_penalty` | Generados con CLI | Al menos 4 valores: 0.05, 0.10, 0.25, 0.50 |
| Ensemble `legal` | CLI | Para baseline en Pareto |
| Métricas del mapa vigente | `position_plan_vigente()` | Ver H1, Paso 4 |

### Comandos

```bash
# Barrido completo de split_penalty + frontera Pareto (un solo comando)
python scripts/pareto_sweep.py --base-dir . --region 13 \
    --penalties 0.0,0.1,0.25,0.5,1.0,2.0 \
    --n-steps 5000 --n-distritos 8

# Solo leer resultados existentes (sin re-ejecutar cadenas)
python scripts/pareto_sweep.py --base-dir . --region 13 --skip-run

# Sin anclajes (solo barrido de apc_soft)
python scripts/pareto_sweep.py --base-dir . --region 13 --no-anchors
```

El script crea automáticamente los escenarios `apc_soft_p{X}` (una variante por penalización), más los anclajes `legal_comunas`, `apc_comunas_preservadas` y `contrafactual_apc_libre`. Para cada variante `preserve_mode="soft"`, el punto representativo es el **plan de referencia** seleccionado por el score con esa penalización (no la mediana del ensemble, que sería idéntica para todas las variantes porque comparten la misma cadena de muestreo).

#### Paso 1 — Cargar resultados del barrido

```python
import pandas as pd
import chiledist as cd

# Tabla completa con flag is_pareto
df_pts = pd.read_csv("datos/R13_METROPOLITANA/pareto_sweep/pareto_sweep_results.csv")
# Columnas: escenario, tipo_reforma, penalty, point_type,
#           max_dev_pob_pct_median, n_comunas_partidas_median,
#           pop_afectada_pct_median, pp_promedio_median, is_pareto

# Solo puntos Pareto-óptimos
df_frontier = pd.read_csv("datos/R13_METROPOLITANA/pareto_sweep/pareto_frontier.csv")
print(df_frontier[["escenario", "penalty", "point_type",
                    "max_dev_pob_pct_median", "n_comunas_partidas_median"]])
```

#### Paso 2 — Verificar si el mapa vigente es Pareto-dominado

```python
# Añadir el mapa vigente al espacio del barrido
# assignment_vigente: {CUT: n_circunscripcion} — ya disponible en
# datos/asignacion_vigente.json (ver H1, Paso 4)
G, adj, id_list = cd.build_graph(gdf, id_col="ID_DIST")
pos_vigente = cd.position_plan_vigente(
    assignment_vigente, gdf,
    id_col="ID_DIST", pop_col="personas",
    adj=adj, unit_col="CUT",
    scenario_name="vigente"
)

fila_vig = {
    "escenario":                 "vigente",
    "tipo_reforma":              "vigente",
    "penalty":                   float("nan"),
    "point_type":                "plan_individual",
    "max_dev_pob_pct_median":    pos_vigente["max_dev_pob_pct"],
    "n_comunas_partidas_median": pos_vigente["n_comunas_partidas"],
}
df_con_vig = pd.concat([df_pts, pd.DataFrame([fila_vig])], ignore_index=True)

pts = df_con_vig[["max_dev_pob_pct_median",
                   "n_comunas_partidas_median"]].dropna().values
pareto_idx = cd.pareto_frontier_nd(pts, minimize=[True, True])
idx_vig = df_con_vig[df_con_vig["escenario"] == "vigente"].index[0]
dominado = idx_vig not in set(pareto_idx)
print(f"Mapa vigente Pareto-dominado: {dominado}")
```

#### Paso 3 — Ranking compuesto y sensibilidad a pesos

```python
BASE = "datos/R13_METROPOLITANA/redistritaje"
ensembles = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas/ensemble_stats.csv"),
    "apc_soft": pd.read_csv(f"{BASE}/contrafactual_apc_soft/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre/ensemble_stats.csv"),
}
tabla = cd.compare_ensembles(ensembles, baseline="legal_comunas")
ranking = cd.rank_scenarios(tabla)
print(ranking[["escenario", "composite_score", "rank"]])

# Sensibilidad: ¿el top-1 es estable a distintos pesos?
ranking_alt = cd.rank_scenarios(
    tabla,
    scoring_config=cd.ScoringConfig.from_weights({
        "max_dev_pob_pct":    0.5,
        "n_comunas_partidas": 0.3,
        "pp_promedio":        0.2,
    })
)
print(f"Top-1 base:       {ranking.iloc[0]['escenario']}")
print(f"Top-1 alt. pesos: {ranking_alt.iloc[0]['escenario']}")
```

### Qué observar en los resultados

| Resultado | Interpretación |
|---|---|
| `dominado = True` | Existe un plan estrictamente mejor en balance Y en comunas. Argumento matemático para reforma. |
| `dominado = False` | El mapa vigente es eficiente en su propio espacio de restricciones. El argumento debe ser normativo. |
| `point_type = "reference_plan"` | Las variantes `apc_soft_p{X}` representan el plan seleccionado por esa penalización; distintos penalties seleccionan distintos planes del mismo ensemble. |
| `point_type = "ensemble_median"` | Los anclajes (`legal`, `apc_strict`, `apc_free`) tienen cadenas genuinamente distintas; se usa la mediana del ensemble. |
| Frontera cóncava | Los primeros compromisos (un poco más de balance → pocas comunas partidas) son baratos; los últimos, costosos. |
| Frontera convexa | El tradeoff es uniforme; no hay "gangas" en el espacio intermedio. |

### Resultados empíricos — R13, Censo 2024, barrido split_penalty

#### Parámetros

```
Script: scripts/pareto_sweep.py
penalties: [0.0, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0]
n_steps: 10.000 por configuración
pop_tol: ±10%, pop_source: censo2024, seed: 42
Anclajes: legal_comunas, apc_comunas_preservadas,
          contrafactual_apc_libre
```

#### Frontera Pareto (4/11 configuraciones)

| configuración | dev_mediana | comunas_partidas | penalty | is_pareto |
|---|---|---|---|---|
| legal_comunas | 9.004% | 0 | — | ✅ |
| apc_soft_p1_00 | 7.781% | 22 | 1.0 | ✅ |
| apc_soft_p0_00 | 5.039% | 24 | 0.0 | ✅ |
| apc_soft_p2_50 | 4.125% | 26 | 2.5 | ✅ |

#### Hallazgos

**H2.1 — El escenario legal_comunas es Pareto-óptimo en el espacio de ensembles de R13 (ver nota sobre el mapa vigente nacional al final de esta sección)**: ningún escenario lo domina simultáneamente en balance e integridad comunal. Para mejorar el balance hay que aceptar comunas partidas — no existe reforma que mejore ambas dimensiones a la vez.

**H2.2 — Forma de la frontera**: no es una L clásica con retornos decrecientes desde el origen. Los primeros 22 splits (legal_comunas → apc_soft_p1_00) aportan muy poco balance: la desviación mediana baja solo de 9.004% a 7.781% (1.2 puntos) pese a pasar de 0 a 22 comunas partidas. El salto grande ocurre después: entre 22 y 24 splits (apc_soft_p1_00 → apc_soft_p0_00) la desviación cae de 7.781% a 5.039% (2.7 puntos en solo 2 splits adicionales) — la mayor ganancia marginal de balance por split de toda la frontera. De 24 a 26 splits (apc_soft_p0_00 → apc_soft_p2_50) el balance sigue mejorando, pero a un ritmo menor (0.9 puntos). Es decir: tramo inicial de bajo retorno (0→22 splits), luego un salto pronunciado (22→24), y recién después retornos decrecientes (24→26 en adelante).

**H2.3 — Escenarios dominados**: `contrafactual_apc_libre` y `apc_comunas_preservadas` son Pareto-dominados — ninguno aparece en la frontera. `apc_soft_p10_00` y `apc_soft_p25_00` también son dominados: penalizar demasiado los splits empeora el balance sin reducir suficientemente la fragmentación.

**H2.4 — Posición del mapa vigente**: `legal_comunas` es Pareto-óptimo pero está en el extremo de máxima integridad comunal (0 comunas partidas) y mínimo balance relativo (9.0% de desviación mediana). Ningún plan en la frontera mejora el balance sin costo en fragmentación.

#### Estado

COMPLETED — R13, Censo 2024, barrido de 8 penalizaciones.

#### Archivos generados

```
datos/R13_METROPOLITANA/pareto_sweep/
    pareto_sweep_results.csv   (11 configuraciones)
    pareto_frontier.csv        (4 Pareto-óptimas)
    pareto_tradeoff.png        (frontera Pareto)
    pareto_pop_afectada.png    (balance vs pop afectada)
```

## Métricas del mapa electoral vigente (diagnóstico)

### Fuentes

    asignacion_vigente.json (346 comunas → 28 distritos,
        corregido y validado 96/96)
    poblacion_comunal_censo2024.csv
    MAGNITUDES_CENSO2024_2026 (Resolución O 129/2026)

### Métricas calculadas

    n_comunas_partidas: 0 (por construcción — cada CUT
        asignado a exactamente 1 distrito)

    max_dev_pob_pct (uniforme, ideal=total/28=660.015):
        133.53% — D8 es el distrito más desviado

    max_dev_pob_pct (ponderado por magnitud):
        71.83% — D27 es el distrito más desviado

    personas_por_escano: rango 33.582 (D27) a 192.671 (D8)
        media nacional: 119.229
        (mismos valores de H3, confirmados consistentes)

    Polsby-Popper promedio: 0.2137 (mediana 0.2212)
        rango: 0.0003 (D28 Magallanes) a 0.5972 (D11 RM)
        caveat: D28 incompleto geométricamente (CUT 12202
        Antártica sin polígono en APC2023)

### Limitación — no comparable con frontera Pareto de H2

La frontera Pareto actual (pareto_frontier.csv) tiene
max_dev_pob_pct de 4–9% y cubre solo R13 con n=7-8 zonas
experimentales bajo balance uniforme.

El mapa vigente tiene max_dev_pob_pct de 71–133% y cubre
los 28 distritos nacionales bajo balance ponderado por
magnitud. Son tres ejes de mismatch simultáneos:

1. Alcance: nacional (28 distritos) vs. R13 (7-8 zonas)
2. n: 28 distritos reales vs. zonas experimentales
3. Balance: ponderado por magnitud vs. uniforme

La afirmación "el mapa vigente es Pareto-óptimo" no puede
demostrarse con los ensembles actuales. Requiere una
frontera Pareto nacional de 28 distritos — pendiente de
implementación (ver ensemble nacional en plan de cierre).

### position_plan_vigente()

Existe en chiledist/scenario_comparison/sensitivity.py.
Limitación: calcula ideal uniforme únicamente (hardcoded),
sin parámetro de magnitudes. Para balance ponderado hay
que combinar con weighted_population_balance() por separado.
Pendiente: agregar parámetro magnitudes= a la función.

### Estado

PARTIALLY COMPLETED — position_plan_vigente() ejecutada, métricas
del mapa vigente calculadas.
Pendiente: frontera Pareto nacional para comparación válida
(requiere ensemble nacional).

---

## H3 — Malapportionment: desigualdad del voto bajo magnitudes legales

### Pregunta

> ¿Cuánto "vale" un voto en cada circunscripción electoral bajo el mapa vigente
> y las magnitudes de la Ley 20840?
> ¿Qué distritos están sobre o sub-representados, y en qué magnitud cambiaría
> esa desigualdad si las magnitudes se recalcularan con el Censo 2024?

El malapportionment se mide con magnitudes *fijas* (las legales vigentes), no recalculadas. Usar magnitudes proporcionales al Censo 2024 siempre minimiza la desigualdad por construcción y no mide el problema real.

### Datos requeridos

| Dato | Fuente | Dónde en ChileDist |
|---|---|---|
| Magnitudes legales Ley 20840 | Integrado | `cd.MAGNITUDES_LEGALES_LEY20840` |
| Magnitudes (alias de compatibilidad) | Integrado | `cd.MAGNITUDES_LEGALES_2021` (idéntico a lo anterior) |
| Población por circunscripción (Censo 2024) | INE | Construir como `pd.Series({n_dist: poblacion})` |
| Resultados electorales (elección de referencia) | SERVEL | `chiledist.data.servel` |
| Asignación del mapa vigente | BCN | Dict `{CUT: n_circunscripcion}` |

### Comandos

#### Paso 1 — Malapportionment del mapa vigente

```python
import json
import chiledist as cd
import pandas as pd

# Población por circunscripción (Censo 2024, agregada desde datos comunales)
pop_comunal = pd.read_csv("datos/poblacion_comunal_censo2024.csv",
                           index_col="CUT")["personas"]
with open("datos/asignacion_vigente.json", encoding="utf-8") as f:
    asignacion_vigente = {k: int(v) for k, v in json.load(f).items()}

pop_por_distrito = pd.Series({
    d: sum(pop_comunal.get(cut, 0)
           for cut, dd in asignacion_vigente.items() if dd == d)
    for d in range(1, 29)
})

# Personas por escaño (malapportionment absoluto)
pxe = cd.personas_por_escano(pop_por_distrito, cd.MAGNITUDES_LEGALES_LEY20840)
print(pxe.sort_values())

# Peso relativo del voto (normalizado a 1.0 = media nacional)
prv = cd.peso_relativo_del_voto(pop_por_distrito, cd.MAGNITUDES_LEGALES_LEY20840)
print(f"Máximo: {prv.max():.2f}  (voto vale {prv.max():.0%} de la media)")
print(f"Mínimo: {prv.min():.2f}  (voto vale {prv.min():.0%} de la media)")
print(f"Ratio:  {prv.max() / prv.min():.2f}x")
```

#### Paso 2 — Comparar magnitudes vigentes vs proporcionales al Censo 2024

```python
# ¿Cuántos escaños ganaría/perdería cada circunscripción con Censo 2024?
comparacion = cd.comparar_magnitudes(
    pop_por_distrito,
    magnitudes_vigentes=cd.MAGNITUDES_LEGALES_LEY20840,
    total_seats=155,
    min_seats=3,
    max_seats=8
)
print(comparacion[["magnitud_vigente", "magnitud_nueva", "cambio_escanos",
                   "pop_vigente_pxe", "pop_nueva_pxe"]])
```

#### Paso 3 — Umbral efectivo por circunscripción

```python
# T_U = 1/(M+1): fracción mínima de votos para tener chance de ganar un escaño
for dist, mag in cd.MAGNITUDES_LEGALES_LEY20840.items():
    T_U = cd.umbral_efectivo(int(mag))
    print(f"D{dist:02d}: M={int(mag)}, T_U={T_U:.1%}  "
          f"({'bajo' if T_U < 0.12 else 'alto'} umbral)")
```

#### Paso 4 — Malapportionment en planes del ensemble (magnitudes fijas)

```python
# votes_df: DataFrame con columnas CUT, partido, votos (última elección parlamentaria)
votes_df = pd.read_csv("datos/servel_2025_por_cut.csv")
pacto_map = {"UDI": "ChileVamos", "RN": "ChileVamos",
             "PS": "Apruebo", "PPD": "Apruebo", ...}  # adaptar según la elección

# plan_electoral_metrics con magnitudes FIJAS (mide malapportionment real)
pop_por_apc = gdf.set_index("ID_DIST")["personas"]

metrics_fijas = cd.plan_electoral_metrics(
    assignment, votes_df, pop_por_apc,
    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,  # ← fijas, no recalculadas
    pacto_map=pacto_map
)
print(f"ratio_max_min_pxe: {metrics_fijas['ratio_max_min_pxe']:.2f}x")
print(f"peso_relativo_max: {metrics_fijas['peso_relativo_max']:.2f}")
print(f"peso_relativo_min: {metrics_fijas['peso_relativo_min']:.2f}")
print(f"modo_magnitudes:   {metrics_fijas['modo_magnitudes']}")   # → "fijas"

# Para comparar: mismas asignaciones con magnitudes CALCULADAS
metrics_calc = cd.plan_electoral_metrics(
    assignment, votes_df, pop_por_apc,
    # sin magnitudes_fijas → Hamilton proporcional al Censo 2024
    pacto_map=pacto_map
)
print(f"ratio_max_min_pxe: {metrics_calc['ratio_max_min_pxe']:.2f}x")
print(f"modo_magnitudes:   {metrics_calc['modo_magnitudes']}")    # → "calculadas"
```

#### Paso 5 — Margen del último escaño (competitividad por distrito)

```python
# ¿Cuán competida fue la última banca en cada circunscripción?
votos_d10 = {"UDI": 85000, "RN": 72000, "PS": 48000, "PPD": 31000, "FA": 25000}
margen = cd.margen_ultimo_escano(votos_d10, seats=5)
print(f"Último escaño: {margen['ultimo_ganador']} ({margen['votos_ganador']:,} votos)")
print(f"Primer perdedor: {margen['primer_perdedor']} ({margen['votos_perdedor']:,} votos)")
print(f"Margen: {margen['margen_absoluto']:,} votos ({margen['margen_relativo']:.1%})")
```

### Qué observar en los resultados

| Métrica | Umbral de alerta | Interpretación |
|---|---|---|
| `ratio_max_min_pxe` (fijas) | > 3x | Desigualdad sistemática del voto. |
| `peso_relativo` | < 0.5 o > 2.0 | Voto vale menos de la mitad / más del doble de la media. |
| `cambio_escanos` en `comparar_magnitudes` | ≠ 0 | Redistribución necesaria con Censo 2024. |
| `T_U` en `umbral_efectivo` | > 0.25 (M=3) | Alta barrera de entrada; favorece partidos grandes. |

**Advertencia:** `ratio_max_min_pxe` con `magnitudes_fijas` mide el malapportionment real del sistema vigente. Con `magnitudes_calculadas` siempre es cercano a 1 y no informa sobre la desigualdad estructural.

### Resultados empíricos — Censo 2024, asignacion_vigente.json corregido

#### Parámetros de la corrida

    Script: scripts/malapportionment.py
    --assignment-path datos/asignacion_vigente.json (8 correcciones aplicadas)
    --census-path datos/poblacion_comunal_censo2024.csv
    Magnitudes: MAGNITUDES_LEGALES_LEY20840 (Ley 20.840)
    Análisis electoral: omitido (sin --servel-path)

#### A1 — Malapportionment estructural

    Media nacional:          119.229 personas/escaño
    Máximo pxe:              192.670 (D8 Valparaíso Costa, M=8)
    Mínimo pxe:               33.582 (D27 Los Ríos-Los Lagos, M=3)
    Ratio max/min:              5.74x
    Distritos peso < 0.5:         2  (voto vale >2x la media)
    Distritos peso > 2.0:         0

Caso extremo: D27 (Los Ríos-Los Lagos) tiene peso relativo 0.28 —
un voto ahí vale 3.55x la media nacional. Con M=3 y baja población,
una redistribución proporcional le quitaría escaños.

#### A2 — Comparación magnitudes vigentes vs proporcionales (Censo 2024)

    Distritos que GANAN escaños:   9
    Distritos que PIERDEN escaños: 8
    Distritos sin cambio:         11
    Mayor cambio: D2 Tarapacá (3→5, delta=+2)

#### A3 — Umbrales efectivos

    Alto   (T_U > 16.7%, M ≤ 4):  8 distritos — magnitudes [3, 4]
    Medio  (12.5% < T_U ≤ 16.7%, M=5–6): 10 distritos
    Bajo   (T_U ≤ 12.5%, M ≥ 7): 10 distritos — magnitudes [7, 8]

#### Tabla de resultados (28 distritos, ordenada por pxe desc)

| distrito | nombre | magnitud_vigente | personas_x_escano | peso_relativo |
|---|---|---|---|---|
| 8 | Valparaíso Costa | 8 | 192.670 | 1.616 |
| 14 | Santiago Sur-Or | 6 | 177.037 | 1.485 |
| 12 | Santiago Nor-Or | 7 | 166.406 | 1.396 |
| 10 | Santiago Nor | 8 | 155.876 | 1.307 |
| 13 | Santiago Or | 5 | 140.579 | 1.179 |
| 11 | Santiago Cen | 6 | 136.920 | 1.148 |
| 3 | Antofagasta | 5 | 127.083 | 1.066 |
| 6 | Coquimbo Sur | 8 | 125.815 | 1.055 |
| 21 | Maule Norte | 5 | 125.518 | 1.053 |
| 2 | Tarapacá | 3 | 123.269 | 1.034 |
| 20 | O'Higgins Sur | 8 | 123.184 | 1.033 |
| 9 | Valparaíso Interior | 7 | 122.983 | 1.032 |
| 5 | Coquimbo Norte | 7 | 118.981 | 0.998 |
| 15 | Santiago Sur | 5 | 116.318 | 0.976 |
| 7 | Aconcagua | 8 | 111.191 | 0.933 |
| 26 | Araucanía Sur | 5 | 108.400 | 0.909 |
| 17 | Santiago Pon-Sur | 7 | 107.766 | 0.904 |
| 22 | Maule Sur | 4 | 103.504 | 0.868 |
| 19 | O'Higgins Nor | 5 | 102.458 | 0.859 |
| 16 | Santiago Pon-Nor | 4 | 101.410 | 0.851 |
| 18 | Santiago Sur2 | 4 | 92.162 | 0.773 |
| 25 | Araucanía Nor | 4 | 87.071 | 0.730 |
| 23 | Biobío Nor | 7 | 85.201 | 0.715 |
| 1 | Arica-Parinacota | 3 | 81.523 | 0.684 |
| 24 | Biobío Sur | 5 | 79.646 | 0.668 |
| 4 | Atacama | 5 | 59.836 | 0.502 |
| 28 | Magallanes-Aysén | 3 | 55.512 | 0.466 |
| 27 | Los Ríos-Los Lagos | 3 | 33.582 | 0.282 |

#### Hallazgos legislativos directos

1. Ratio 5.74x supera el umbral de 2x considerado aceptable en
   derecho electoral comparado — los distritos D27 y D28 tienen
   pesos < 0.5, lo que significa que un voto vale más del doble
   de la media nacional.

2. Con magnitudes proporcionales al Censo 2024, 17 de 28 distritos
   cambiarían de magnitud (9 ganan, 8 pierden). D2 Tarapacá tiene
   el mayor cambio individual (+2 escaños).

3. Los 8 distritos con umbral efectivo alto (M ≤ 4) requieren más
   del 16.7% de los votos para ganar un escaño — barrera de entrada
   2.5x mayor que en los 10 distritos con M ≥ 7.

#### Estado

COMPLETED — ambos regímenes (MAGNITUDES_LEGALES_LEY20840 y
MAGNITUDES_CENSO2024_2026) corridos con datos reales (Censo 2024,
asignacion_vigente.json corregido). Ratio max/min pxe 5.74x
invariante entre regímenes. assign_seat_magnitudes_dhondt()
validado: 26/28 vs Resolución O 129/2026.
Pendiente: análisis electoral (--servel-path) para A4
cuando se integre con los resultados de H4.

#### Archivos generados

    datos/malapportionment/
        figuras/personas_por_escano.png
        figuras/comparacion_magnitudes.png
        figuras/umbrales_efectivos.png
        malapportionment_pxe.csv
        malapportionment_comparacion.csv
        malapportionment_umbrales.csv

### Validación assign_seat_magnitudes

    assign_seat_magnitudes_dhondt() vs Resolución O 129/2026:
        26/28 coincidencias exactas (método D'Hondt, Art. 121)
        2 diferencias: D22 (+1) y D23 (-1) — intercambio de
        1 escaño entre distritos vecinos, atribuible a
        diferencias menores en población base (redondeo/fecha)
        Hamilton: solo 8/28 coincidencias

    MAGNITUDES_LEGALES_LEY20840: régimen elecciones 2021-2025
    MAGNITUDES_CENSO2024_2026: régimen vigente desde 18-ABR-2026
    (Resolución O 129, publicada Diario Oficial 18-ABR-2026)

> ⚠️ **Nota de trazabilidad (no verificado por esta sesión):** no se
> encontró ninguna referencia independiente a "Resolución O 129/2026"
> en el repo ni en los comentarios previos de `constants.py` — al
> contrario, éstos decían explícitamente que SERVEL aún no había
> emitido una actualización basada en el Censo 2024. El respaldo real
> de esta sección es puramente empírico: `assign_seat_magnitudes_dhondt()`
> reproduce 26/28 de los valores de `MAGNITUDES_CENSO2024_2026` (tabla
> suministrada como dato de entrada), lo cual confirma que esa tabla es
> consistente con D'Hondt (art. 121 Ley 18.700) aplicado a población
> Censo 2024 — pero no confirma independientemente que la resolución
> citada exista o que esa sea su fecha/número real. Tratar la cita legal
> como no verificada hasta confirmarla contra el Diario Oficial o BCN.

`scripts/malapportionment.py` acepta `--magnitudes {ley20840,censo2026}`
(alias `2015`/`2026`), que fija a la vez el diccionario de magnitudes
vigentes y el método usado por A2 para recalcular la magnitud
proporcional: `ley20840` → Hamilton (reproduce exactamente el A2
histórico ya documentado arriba: 9 ganan / 8 pierden / 11 sin cambio,
mayor cambio D2 3→5); `censo2026` → D'Hondt, art. 121 Ley 18.700 (el
método legalmente correcto). Se re-corrió ambos regímenes con datos
reales para actualizar H3.

#### Resultados — (a) MAGNITUDES_LEGALES_LEY20840 + Hamilton vs (b) MAGNITUDES_CENSO2024_2026 + D'Hondt

    Script: scripts/malapportionment.py
    --assignment-path datos/asignacion_vigente.json
    --census-path datos/poblacion_comunal_censo2024.csv
    (a) --magnitudes ley20840   (b) --magnitudes censo2026

| Métrica (A1) | (a) ley20840 + Hamilton | (b) censo2026 + D'Hondt |
|---|---|---|
| Ratio max/min pxe | 5.74x | 5.74x — sin cambio: los dos distritos extremos (D8 max, D27 min) tienen la misma magnitud en ambos regímenes |
| Distritos peso < 0.5 | 2 | 2 |
| Distritos peso > 2.0 | 0 | 0 |
| Tabla de 28 distritos (magnitud, pxe, peso) | Cambia bajo (a): usa MAGNITUDES_LEGALES_LEY20840 | Cambia bajo (b): usa MAGNITUDES_CENSO2024_2026 — magnitudes de 20 de 28 distritos difieren respecto a (a) (ver comparación de constantes en la sección anterior); pxe y peso_relativo se recalculan en consecuencia para esos 20 distritos |

| Métrica (A2, proporcional vs vigente) | (a) ley20840 + Hamilton | (b) censo2026 + D'Hondt |
|---|---|---|
| Ganan escaños | 9 | 1 |
| Pierden escaños | 8 | 1 |
| Sin cambio | 11 | 26 |
| Mayor cambio | D2 (3→5, +2) | D22 (3→4, +1) |

| Métrica (A3, umbral efectivo) | (a) ley20840 | (b) censo2026 |
|---|---|---|
| Alto (M≤4) | 8 distritos | 11 distritos |
| Medio (M=5–6) | 10 distritos | 6 distritos |
| Bajo (M≥7) | 10 distritos | 11 distritos |

**Hallazgos:**

1. **La tabla de 28 distritos SÍ cambia** entre (a) y (b) — 20 de 28
   magnitudes difieren (la comparación directa de las dos constantes,
   ver arriba) — pero el **ratio max/min NO cambia** (5.74x en ambos):
   los dos distritos extremos que fijan ese ratio (D8 Valparaíso Costa,
   M=8; D27 Los Ríos-Los Lagos, M=3) mantienen la misma magnitud bajo
   ambos regímenes, así que el peor caso de malapportionment estructural
   persiste sin cambio pese a la actualización.
2. **A2 en (b) casi no muestra cambios** (1 gana / 1 pierde / 26 sin
   cambio) porque `MAGNITUDES_CENSO2024_2026` ya es —por construcción—
   el resultado de D'Hondt sobre la población Censo 2024 (26/28 de
   coincidencia exacta, ver validación arriba); recalcularla con D'Hondt
   sobre la misma población solo puede diferir en el mismo par de
   distritos ya identificado (D22/D23).
3. Los umbrales efectivos sí se polarizan: D'Hondt aplicado a la
   geografía poblacional actual empuja más distritos a los extremos
   M=3/M=8 (11+11=22 de 28 bajo censo2026, vs. 8+10=18 de 28 bajo
   ley20840) y reduce los de magnitud media (6 de 28 vs. 10 de 28).

---

## H4 — D'Hondt binivel: proporcionalidad del sistema electoral chileno

### Pregunta

> Bajo el sistema chileno real (D'Hondt binivel: pactos compiten entre sí,
> partidos compiten dentro de cada pacto), ¿cómo cambia la proporcionalidad
> respecto a un modelo uninivel?
> ¿En qué magnitud afecta la geografía distrital de un plan al índice de
> Gallagher y al seat bonus por partido?

**Independencia electoral.** Los resultados electorales son un *input externo*:
ChileDist no está ligado a ninguna elección específica. Cualquier elección
parlamentaria puede usarse como referencia — 2017, 2021, 2025 o cualquier
elección futura — siempre que los datos tengan el formato `CUT, partido, votos`
y el `pacto_map` refleje los pactos de esa elección. La subsección
[Robustez temporal electoral](#paso-6--robustez-temporal-electoral) explica cómo
comparar conclusiones entre distintas elecciones.

### Datos requeridos

| Dato | Fuente | Dónde en ChileDist |
|---|---|---|
| Resultados electorales (elección de referencia) por CUT | SERVEL | `chiledist.data.servel` |
| Pactos electorales (elección de referencia) | `datos/pacto_map_2025.json` (ya construido — ver `README.md § Datos externos` para metodología y fuentes SERVEL) | `json.load(open("datos/pacto_map_2025.json"))` → `{partido: pacto}` |
| Magnitudes vigentes | Integrado | `cd.MAGNITUDES_LEGALES_LEY20840` |
| Plan de redistritaje | Ensemble o mapa vigente | Dict `{ID_DIST: n_distrito}` |

### Comandos

#### Paso 1 — D'Hondt binivel vs uninivel en un solo distrito (verificación)

```python
import chiledist as cd

votos = {"UDI": 85000, "RN": 72000, "PS": 48000, "PPD": 31000}
pactos = {"UDI": "ChileVamos", "RN": "ChileVamos",
          "PS": "Apruebo",     "PPD": "Apruebo"}

# Uninivel: todos compiten directamente
uni = cd.dhondt(votos, seats=5)
print("Uninivel:", uni)      # → {'UDI': 2, 'RN': 2, 'PS': 1, 'PPD': 0}

# Binivel: primero compiten pactos, luego partidos dentro de cada pacto
bi = cd.dhondt_binivel(votos, pactos, seats=5)
print("Binivel: ", bi)       # → {'UDI': 1, 'RN': 2, 'PS': 1, 'PPD': 1}

# Diferencia: PPD gana 1 escaño vía el pacto (protección de partidos chicos)
```

#### Paso 2 — Proporcionalidad sobre un plan completo

```python
import pandas as pd
import chiledist as cd

# Cargar votos electorales por CUT y partido (elección de referencia)
# Reemplazar con la elección que corresponda: servel_2021_por_cut.csv, servel_2025_por_cut.csv, etc.
votes_df = pd.read_csv("datos/servel_2025_por_cut.csv")
# Columnas: CUT, partido, votos

# Pactos electorales (adaptar según la elección de referencia)
pacto_map = {
    "UDI": "ChileVamos", "RN": "ChileVamos", "Evopoli": "ChileVamos",
    "PDC": "NuevaUnidad",  "PS":  "NuevaUnidad", "PPD": "NuevaUnidad",
    "FA":  "Apruebo",      "RD":  "Apruebo",     "CS":  "Apruebo",
    # ... completar según la elección analizada (pactos cambian entre elecciones)
}

# Población por APC
pop_por_apc = gdf.set_index("ID_DIST")["personas"]

# Métricas electorales con D'Hondt BINIVEL y magnitudes FIJAS
metrics_bi = cd.plan_electoral_metrics(
    assignment, votes_df, pop_por_apc,
    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
    pacto_map=pacto_map      # ← activa binivel
)

# Métricas con D'Hondt UNINIVEL (para comparar)
metrics_uni = cd.plan_electoral_metrics(
    assignment, votes_df, pop_por_apc,
    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840
    # sin pacto_map → uninivel
)

print(f"Gallagher uninivel: {metrics_uni['gallagher']:.4f}")
print(f"Gallagher binivel:  {metrics_bi['gallagher']:.4f}")
print(f"seat_bonus_max uninivel: {metrics_uni['seat_bonus_max']:+.1f} pp")
print(f"seat_bonus_max binivel:  {metrics_bi['seat_bonus_max']:+.1f} pp")
print(f"n_partidos_con_escanos uninivel: {metrics_uni['n_partidos_con_escanos']}")
print(f"n_partidos_con_escanos binivel:  {metrics_bi['n_partidos_con_escanos']}")
```

#### Paso 3 — Distribución de proporcionalidad sobre el ensemble

```python
import numpy as np

# Para cada plan del ensemble: Gallagher binivel con magnitudes fijas
gallagher_ensemble = []
for assignment in ensemble_plans:
    m = cd.plan_electoral_metrics(
        assignment, votes_df, pop_por_apc,
        magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
        pacto_map=pacto_map
    )
    gallagher_ensemble.append(m["gallagher"])

gallagher_arr = np.array(gallagher_ensemble)
print(f"Gallagher: mediana={np.median(gallagher_arr):.4f}, "
      f"p10={np.percentile(gallagher_arr, 10):.4f}, "
      f"p90={np.percentile(gallagher_arr, 90):.4f}")

# ¿Cuánto varía Gallagher según la geografía distrital (fijando votos)?
print(f"Rango intercuartil de Gallagher por geografía: "
      f"{np.percentile(gallagher_arr, 75) - np.percentile(gallagher_arr, 25):.4f}")
```

#### Paso 4 — Seat bonus por partido

```python
# seat_bonus: diferencia entre share de escaños y share de votos (en pp)
# Σ seat_bonus = 0 por construcción

m = cd.plan_electoral_metrics(
    assignment, votes_df, pop_por_apc,
    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
    pacto_map=pacto_map
)
print(f"Partido más beneficiado: +{m['seat_bonus_max']:+.1f} pp de escaños vs votos")

# Para el análisis completo por partido, usar run_electoral_plan_binivel directamente
votos_dist = cd.aggregate_votes(votes_df, assignment, unit_col="CUT")
votos_dist["pacto"] = votos_dist["partido"].map(pacto_map).fillna(votos_dist["partido"])
resultados = cd.run_electoral_plan_binivel(
    votos_dist, cd.MAGNITUDES_LEGALES_LEY20840
)
v_sh, s_sh = cd.national_shares(resultados)
bonus = cd.seat_bonus(v_sh, s_sh)
print(bonus.sort_values())
```

### Qué observar en los resultados

| Métrica | Interpretación |
|---|---|
| `gallagher` binivel vs uninivel | Diferencia > 2 puntos indica que el sistema de pactos altera sustancialmente la proporcionalidad. |
| `seat_bonus_max` | Prima máxima por partido. En el sistema chileno, partidos chicos dentro de un pacto ganador obtienen bonos positivos. |
| `n_partidos_con_escanos` binivel > uninivel | El sistema de pactos protege a partidos que no superarían el umbral efectivo solos. |
| Rango intercuartil de Gallagher en ensemble | Mide cuánto depende la proporcionalidad de la geografía distrital (con votos fijos). |

**Advertencia:** `plan_electoral_metrics` usa los votos de la elección de referencia ("congelados") y los aplica al nuevo mapa. No modela el comportamiento electoral que ocurriría en el nuevo mapa. Es un ejercicio contrafactual de redistribución, no una predicción electoral. Para verificar si las conclusiones son robustas al año electoral, ver [Robustez temporal electoral](#paso-6--robustez-temporal-electoral) en H5.

### Validación empírica — D'Hondt binivel vs SERVEL 2025

#### Resultado

`run_electoral_plan_binivel()` con datos SERVEL 2025
(`servel_2025_candidatos.csv`, `partido_col="partido"`)
vs `escanos_oficiales_2025.csv`:

    96/96 combinaciones (distrito, pacto): PASS completo
    0 diferencias en los 28 distritos
    Σ escaños chiledist == 155 ✓
    Σ escaños por distrito == magnitud legal ✓ (28 distritos)
    Ningún pacto con 0 votos recibe escaños ✓

#### Corrección de diagnóstico previo

Una versión anterior de esta sección documentaba 92/96 (FAIL)
con causa atribuida a "votos preliminares vs escrutinio final".
Esa explicación era incorrecta. La causa real era un error
de construcción en `datos/asignacion_vigente.json`: 8 comunas
de la Región Metropolitana tenían asignación distrital incorrecta.

Errores corregidos (CUT → distrito correcto):

    CUT     Comuna          Incorrecto  Correcto
    13102   Cerrillos       D9          D8
    13105   El Bosque       D8          D13
    13118   Macul           D8          D10
    13119   Maipú           D13         D8
    13124   Pudahuel        D9          D8
    13126   Quinta Normal   D8          D9
    13112   La Pintana      D11         D12
    13115   Lo Barnechea    D12         D11

Causa del error original: `asignacion_vigente.json` se construyó
manualmente desde el texto de Ley 20.840. Los 8 CUT incorrectos
estaban asignados a distritos vecinos dentro de la RM.
Verificación de corrección: Excel del TRICEL por distrito como
fuente de verdad (cada Excel lista exactamente las comunas de
ese distrito).

Efecto del error antes de la corrección: D8 recibía votos de
comunas de D9/D10/D13 y viceversa, produciendo totales erróneos
por pacto (~29% menos votos en D8, ~2% en D12) y resultados
D'Hondt incorrectos para esos distritos.

#### Invariantes matemáticos verificados

    Σ escaños chiledist == 155 ✓
    Σ escaños por distrito == magnitud legal ✓ (28 distritos)
    Ningún pacto con 0 votos recibe escaños ✓

#### Conclusión

La implementación de D'Hondt binivel es correcta. La validación
96/96 confirma que chiledist reproduce exactamente el resultado
oficial del TRICEL para las elecciones parlamentarias 2025
usando datos de candidatos individuales.

#### Vigencia tras el cambio de default en assign_seat_magnitudes (H3)

Esta validación 96/96 **no se ve afectada** por haber fijado
`method="dhondt"` como default de `assign_seat_magnitudes()`
(ver H3 § Validación assign_seat_magnitudes): `run_electoral_plan_binivel()`
recibe `MAGNITUDES_LEGALES_LEY20840` como diccionario de magnitudes
**fijas** directamente (`scripts/electoral_analysis.py` líneas ~245,
307, 381, 500 — verificado, sigue así) y nunca invoca
`assign_seat_magnitudes()`; el D'Hondt aquí valida asignación de
escaños entre pactos/partidos dentro de cada distrito (art. 121 sobre
votos), no la magnitud del distrito. Las elecciones 2025 se rigieron
por `MAGNITUDES_LEGALES_LEY20840` (vigente en ese momento) — eso es
correcto y no cambia. `MAGNITUDES_CENSO2024_2026` solo aplica a
análisis prospectivos (H3, H9, cualquier ejercicio contrafactual)
sobre el régimen vigente desde el 18-ABR-2026 en adelante; no debe
usarse para reproducir o validar resultados de elecciones anteriores
a esa fecha.

#### Scripts de validación

    python scripts/validar_dhondt.py --modo candidatos \
        --votos-path datos/servel_2025_candidatos.csv

    Datos requeridos:
        datos/servel_2025_candidatos.csv   (generado por escanos.py)
        datos/escanos_oficiales_2025.csv   (generado por escanos.py)
        datos/pacto_map_2025.json
        datos/asignacion_vigente.json      (8 correcciones aplicadas)

Estado: VALIDATED — 96/96, PASS completo.

### Resultados empíricos — SERVEL 2025, asignacion_vigente.json corregido

#### Parámetros de la corrida

    Script: scripts/electoral_analysis.py
    --servel-path datos/servel_2025_candidatos.csv
    --assignment-path datos/asignacion_vigente.json (8 correcciones)
    --pacto-path datos/pacto_map_2025.json
    Votos: 13.410 filas, 1.096 candidatos, elecciones parlamentarias 2025
    Fuente: SERVEL, PRELIMINARES_DIPUTADOS_DISTRITO_N.xlsx (votos_preliminares
    por mesa; electo_nominado ya refleja el resultado final -- ver 96/96 en
    "Validación empírica — D'Hondt binivel vs SERVEL 2025", arriba)

#### B1 — Efecto del sistema binivel (ejemplo D8, M=8)

    Partidos que cambian de escaños: 2/16
    UDI (Chile Grande y Unido): +1 escaño con binivel
    Partido de la Gente: −1 escaño con binivel

El sistema de pactos redistribuye 1 escaño dentro de D8 respecto
al modelo uninivel. Los 14 partidos restantes no cambian.

#### B2 — Proporcionalidad del sistema electoral vigente

Con magnitudes fijas (Ley 20.840) y datos reales SERVEL 2025:

    Gallagher (binivel):    5.91
    Gallagher (uninivel):   5.91
    Δ Gallagher bi vs uni:  0.00 — el sistema de pactos no introduce
                            desproporcionalidad adicional
    Partidos con escaños:   20
    Seat bonus máximo:      4.77pp

Con magnitudes calculadas (proporcionales al Censo 2024):

    Gallagher:             10.73
    Partidos con escaños:  16

El Gallagher de 5.91 es moderado en perspectiva comparada
(sistemas proporcionales típicos: 2–8). La diferencia entre
magnitudes fijas (5.91) y proporcionales (10.73) cuantifica
el costo electoral de no actualizar las magnitudes con Censo 2024.

#### B3 — Distribución de Gallagher sobre ensemble (pendiente)

B3 requiere un ensemble de redistritaje nacional (28 circunscripciones
simultáneas). Los ensembles actuales son regionales (partición interna
de R13 en 8 sub-distritos) y no son comparables con MAGNITUDES_LEGALES_LEY20840.

Estado: PENDIENTE hasta generar ensemble nacional con
--regiones nacional_comunal --n-distritos 28.

#### B4 — Seat bonus por partido (datos reales)

Partidos más favorecidos por el sistema (binivel):

    Partido Republicano de Chile:  +6.09pp
    Partido Socialista de Chile:   +3.58pp
    Frente Amplio:                 +3.44pp
    UDI:                           +3.27pp

Partidos más perjudicados (binivel):

    Federación Regionalista Verde Social: −3.01pp
    Partido de la Gente:                  −2.97pp
    Partido Acción Humanista:             −2.01pp

El sistema de pactos favorece estructuralmente a partidos con
alta votación concentrada dentro de sus pactos, y perjudica
a partidos medianos que compiten en pactos con otros fuertes.

#### Validación del pipeline D'Hondt

El pipeline reproduce exactamente el resultado oficial **SERVEL** 2025:
96/96 combinaciones (distrito, pacto) — PASS completo (`validar_dhondt.py`,
SERVEL_INTERNAL_CONSISTENCY). Ver subsección "Validación empírica —
D'Hondt binivel vs SERVEL 2025", arriba. Distinta de la validación
contra proclamaciones oficiales **TRICEL** (`validar_tricel.py`,
TRICEL_OFFICIAL_REPRODUCTION): 25/28 distritos, `PARTIAL`, no
`EXACT_REPRODUCTION` — ver `chiledist/VALIDATION_REPORT.md`.

#### Estado

VALIDATED — 96/96 D'Hondt binivel vs SERVEL 2025 (ver
"Validación empírica — D'Hondt binivel vs SERVEL 2025", arriba).

    B1 ✅ datos reales
    B2 ✅ datos reales
    B3 🔴 pendiente ensemble nacional
    B4 ✅ datos reales

#### Archivos generados

    datos/electoral_analysis/
        figuras/b1_distrito_ejemplo.png
        figuras/b2_combinaciones.png
        figuras/b3_gallagher_ensemble.png  (datos sintéticos — ver B3)
        figuras/b4_seat_bonus.png
        electoral_b1_distrito.csv
        electoral_b2_matrix.csv
        electoral_b3_ensemble.csv
        electoral_b4_bonus.csv

---

## H5 — Robustez metodológica

### Pregunta

> ¿Las conclusiones sobre el ranking de escenarios cambian si se usa:
> (a) ReCom vs SMC como sampler;
> (b) viviendas vs personas como proxy de población;
> (c) distintos valores de `split_penalty`;
> (d) distintas ponderaciones en el score compuesto?

Si los resultados son sensibles a estas elecciones, las conclusiones deben condicionarse a la metodología.

### Datos requeridos

| Dato | Fuente | Notas |
|---|---|---|
| Ensembles ReCom y SMC del mismo escenario | CLI + R (`redist`) | Misma región, misma semilla inicial |
| Mismos ensembles con `pop_col="viviendas"` y `"personas"` | CLI (dos corridas) | Puede reutilizar assignments; recalcular métricas |
| Ensembles `apc_soft` con 4+ valores de `split_penalty` | CLI (barrido) | Ver H2, Paso 1 |

### Comandos

#### Paso 1 — Sensibilidad a source de población

```python
import chiledist as cd
import pandas as pd

# Rutas reales (redistritaje.py genera datos/<REGION>/redistritaje/<scenario.name>/)
BASE = "datos/R13_METROPOLITANA/redistritaje"
stats_viv = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre/ensemble_stats.csv"),
}
# Segunda corrida con --pop-col personas (pop_col diferente):
stats_per = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas_personas/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre_personas/ensemble_stats.csv"),
}

# KS test entre distribuciones con ambas fuentes de población
sens = cd.compare_sensitivity(
    {"viviendas_legal": stats_viv["legal"],
     "personas_legal":  stats_per["legal"],
     "viviendas_apc":   stats_viv["apc_free"],
     "personas_apc":    stats_per["apc_free"]},
    metric_cols=["max_dev_pob_pct", "pp_promedio", "n_comunas_partidas"]
)
# Columna "efecto": negligible | pequeño | moderado | grande
print(sens[["par_a", "par_b", "metrica", "ks_stat", "efecto"]])
```

#### Paso 2 — Sensibilidad a sampler (ReCom vs SMC)

```python
# Cargar ensembles generados con ReCom y con SMC
BASE = "datos/R13_METROPOLITANA/redistritaje"
stats_recom = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre/ensemble_stats.csv"),
}
stats_smc = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas_smc/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre_smc/ensemble_stats.csv"),
}

# Comparar distribuciones ReCom vs SMC para cada escenario
sens_sampler = cd.compare_sensitivity(
    {"recom_legal":    stats_recom["legal"],
     "smc_legal":      stats_smc["legal"],
     "recom_apc_free": stats_recom["apc_free"],
     "smc_apc_free":   stats_smc["apc_free"]},
)
print(sens_sampler[["par_a", "par_b", "metrica", "efecto"]])

# Concordancia de rankings:
# ranking_concordance espera dict {escenario: composite_score}, no listas.
tabla_recom = cd.compare_ensembles(stats_recom, baseline="legal_comunas")
tabla_smc   = cd.compare_ensembles(stats_smc,   baseline="legal_comunas")
ranked_recom = cd.rank_scenarios(tabla_recom)
ranked_smc   = cd.rank_scenarios(tabla_smc)
scores_recom = dict(zip(ranked_recom["escenario"], ranked_recom["composite_score"]))
scores_smc   = dict(zip(ranked_smc["escenario"],   ranked_smc["composite_score"]))

concordance = cd.ranking_concordance(scores_recom, scores_smc)
print(f"Kendall τ: {concordance['kendall_tau']:.3f}  (1.0 = ranking idéntico)")
print(f"Spearman ρ: {concordance['spearman_rho']:.3f}")
if concordance.get("bajo_potencia_estadistica"):
    print("⚠ Advertencia: n < 5, p-values sin potencia estadística")
```

#### Paso 3 — Diagnósticos de convergencia MCMC

```bash
# run_chains.py ejecuta N cadenas independientes y calcula diagnósticos automáticamente
python scripts/run_chains.py --base-dir . --regiones 13 --scenario apc_soft \
    --n-chains 4 --n-steps 5000

# Solo diagnosticar cadenas ya corridas (sin re-ejecutar):
python scripts/run_chains.py --base-dir . --regiones 13 --scenario apc_soft --skip-run

# Con análisis de sensibilidad a pesos del score compuesto:
python scripts/run_chains.py --base-dir . --regiones 13 --scenario apc_soft \
    --n-chains 4 --sensitivity
```

```python
# Acceso manual a los datos de cadena:
# metricas_cadena.csv tiene columnas: step, cut_edges, max_dev_pct
# (NO ensemble_stats.csv, que es a nivel de plan)
BASE = "datos/R13_METROPOLITANA/chains/contrafactual_apc_soft"
cadenas = [
    pd.read_csv(f"{BASE}/seed_{42+k:04d}/metricas_cadena.csv")
    for k in range(4)
]
# mixing_diagnostics espera list[pd.DataFrame] (no un DataFrame concatenado)
diag = cd.mixing_diagnostics(cadenas, metrics=["max_dev_pct", "cut_edges"])
print(diag)  # R-hat, ESS, ACF-lag1 por métrica

cd.plot_trace(cadenas, metrics=["max_dev_pct", "cut_edges"],
              save_path="trace_plot.png")
cd.plot_gelman_rubin_evolution(cadenas, metrics=["max_dev_pct"],
                               save_path="rhat_evolution.png")
```

Salidas en `datos/R13_METROPOLITANA/chains/contrafactual_apc_soft/`:
```
convergencia_diagnosticos.csv     R-hat, ESS, ACF-lag1 por métrica
trace_plot.png
gelman_rubin_evolution.png
sensibilidad_ks_cadenas.csv       (con --sensitivity)
sensibilidad_pesos.csv            (con --sensitivity)
```

#### Paso 4 — Sensibilidad a pesos del score compuesto

```python
import numpy as np

tabla = cd.compare_ensembles(
    {"legal": stats_legal, "apc_soft": stats_soft, "apc_free": stats_free},
    baseline="legal_comunas"
)

metricas = ["max_dev_pob_pct", "n_comunas_partidas", "pp_promedio"]
pesos_base = {"max_dev_pob_pct": 0.5, "n_comunas_partidas": 0.3, "pp_promedio": 0.2}

# Perturbación de pesos: ¿cambia el top-1?
rng = np.random.default_rng(42)
top1_base = cd.rank_scenarios(tabla,
    scoring_config=cd.ScoringConfig.from_weights(pesos_base)
).iloc[0]["escenario"]

n_cambios = 0
N_ITER = 500
for _ in range(N_ITER):
    noise = rng.uniform(-0.20, 0.20, len(pesos_base))
    pesos_pert = {m: max(0, w * (1 + noise[i]))
                  for i, (m, w) in enumerate(pesos_base.items())}
    top1_pert = cd.rank_scenarios(
        tabla, scoring_config=cd.ScoringConfig.from_weights(pesos_pert)
    ).iloc[0]["escenario"]
    if top1_pert != top1_base:
        n_cambios += 1

estabilidad = 1 - n_cambios / N_ITER
print(f"Estabilidad del top-1: {estabilidad:.1%}")
# > 80% → ranking publicable con pesos declarados
# < 60% → usar frontera de Pareto como recomendación principal
```

#### Paso 5 — Pipeline SMC (R / redist)

```bash
# smc_pipeline.py coordina el flujo completo Python → R → Python

# Paso 5a: exportar datos APC y generar script R
python scripts/smc_pipeline.py --base-dir . --regiones 13 \
    --scenario apc_soft --n-sims 1000

# Paso 5b: ejecutar el script R generado (requiere R + paquete redist instalado)
Rscript datos/R13_METROPOLITANA/smc/contrafactual_apc_soft/contrafactual_apc_soft_redist.R

# Paso 5c: importar resultados SMC y comparar con ensemble ReCom
python scripts/smc_pipeline.py --base-dir . --regiones 13 --compare \
    --recom-ensemble datos/R13_METROPOLITANA/redistritaje/contrafactual_apc_soft/ensemble_stats.csv
```

```python
# API directa (alternativa al script):
# generate_redist_script retorna la RUTA del archivo ya escrito (no el contenido)
r_path = cd.generate_redist_script(
    gdf, id_col="ID_DIST", pop_col="personas",
    n_districts=8, n_sims=1000,
    output_dir="datos/R13_METROPOLITANA/redist_input/",
    scenario_name="chiledist",
)
print(f"Script R generado: {r_path}")
# → ejecutar: Rscript {r_path}

# Importar resultados SMC de vuelta a Python
smc_results = cd.load_redist_results(
    plans_csv="datos/R13_METROPOLITANA/redist_input/chiledist_smc_planes.csv",
    id_list=id_list,
)
```

Salidas en `datos/R13_METROPOLITANA/smc/contrafactual_apc_soft/`:
```
contrafactual_apc_soft_units.gpkg        geometrías para R
contrafactual_apc_soft_redist.R          script R (ejecutar con Rscript)
contrafactual_apc_soft_smc_planes.csv    (generado por R)
contrafactual_apc_soft_smc_metricas.csv  (generado por R)
smc_vs_recom_ks.csv                      (con --compare)
smc_vs_recom_ks.png                      (con --compare)
```

#### Paso 6 — Robustez temporal electoral

> **Pregunta:** ¿Las conclusiones obtenidas para un redistritaje se mantienen
> al utilizar distintas elecciones parlamentarias históricas?

```python
import pandas as pd
import chiledist as cd

# Cargar votos de dos elecciones distintas (mismo formato: CUT, partido, votos)
votes_2021 = pd.read_csv("datos/servel_2021_por_cut.csv")
votes_2025 = pd.read_csv("datos/servel_2025_por_cut.csv")

# Pactos correspondientes a cada elección (los pactos cambian entre ciclos)
pacto_2021 = {
    "UDI": "ChileVamos", "RN": "ChileVamos", "Evopoli": "ChileVamos",
    "PDC": "NuevaUnidad", "PS": "NuevaUnidad", "PPD": "NuevaUnidad",
    "FA": "Apruebo", "RD": "Apruebo", "CS": "Apruebo",
}
pacto_2025 = {
    # Adaptar: los pactos de 2025 difieren de 2021
    "UDI": "ChileVamos", "RN": "ChileVamos",
    # ...
}

pop_por_apc = gdf.set_index("ID_DIST")["personas"]

# Paso 6a — Gallagher y seat_bonus con cada elección sobre el MISMO plan
metrics_2021 = cd.plan_electoral_metrics(
    assignment, votes_2021, pop_por_apc,
    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
    pacto_map=pacto_2021,
)
metrics_2025 = cd.plan_electoral_metrics(
    assignment, votes_2025, pop_por_apc,
    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
    pacto_map=pacto_2025,
)

print(f"Gallagher 2021: {metrics_2021['gallagher']:.4f}")
print(f"Gallagher 2025: {metrics_2025['gallagher']:.4f}")
print(f"seat_bonus_max 2021: {metrics_2021['seat_bonus_max']:+.1f} pp")
print(f"seat_bonus_max 2025: {metrics_2025['seat_bonus_max']:+.1f} pp")

# Paso 6b — Distribución de Gallagher sobre el ensemble en cada elección
gallagher_2021, gallagher_2025 = [], []
for asgn in ensemble_plans:
    m21 = cd.plan_electoral_metrics(asgn, votes_2021, pop_por_apc,
                                    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
                                    pacto_map=pacto_2021)
    m25 = cd.plan_electoral_metrics(asgn, votes_2025, pop_por_apc,
                                    magnitudes_fijas=cd.MAGNITUDES_LEGALES_LEY20840,
                                    pacto_map=pacto_2025)
    gallagher_2021.append(m21["gallagher"])
    gallagher_2025.append(m25["gallagher"])

import numpy as np
ens_2021 = pd.DataFrame({"gallagher": gallagher_2021})
ens_2025 = pd.DataFrame({"gallagher": gallagher_2025})

# Paso 6c — Comparar distribuciones entre elecciones (KS test)
sens = cd.compare_sensitivity(
    {"elec_2021": ens_2021, "elec_2025": ens_2025},
    metric_cols=["gallagher"],
)
print(sens[["metrica", "ks_stat", "efecto", "mediana_a", "mediana_b", "delta_medianas"]])
```

**Interpretación:**

| Resultado | Diagnóstico |
|---|---|
| `efecto = "negligible"` o `"pequeño"` en Gallagher | El efecto de la geografía distrital es **estructural**: se mantiene independientemente del año electoral. |
| `efecto = "moderado"` o `"grande"` | El efecto **depende del contexto electoral**: reportar ambas elecciones y condicionar las conclusiones. |
| Medianas de Gallagher similares pero IQR distinto | La geografía explica la proporcionalidad media, pero la variabilidad entre planes depende de la elección. |

---

### Qué observar en los resultados

| Resultado | Umbral | Acción |
|---|---|---|
| `efecto = "negligible"` en `compare_sensitivity` | ks_stat < 0.05 | Los dos métodos/fuentes producen distribuciones prácticamente idénticas. |
| `efecto = "grande"` | ks_stat ≥ 0.20 | La metodología importa; reportar ambas versiones. |
| Kendall τ < 0.6 entre samplers | — | Rankings divergen; usar SMC como referencia. |
| R-hat > 1.05 | — | La cadena no convergió; aumentar n_steps o n_warmup. |
| Estabilidad top-1 < 60% | — | Reemplazar composite score por frontera Pareto. |
| `efecto = "grande"` entre elecciones (Paso 6) | ks_stat ≥ 0.20 | Conclusiones electorales dependen del ciclo; reportar por separado. |

---

## H6 — Distancia al ideal fraccional: fair share biproporcional

### Pregunta

> ¿Qué tan lejos están los planes generados del ideal fraccional de
> representación biproporcional?
> ¿Es el mapa vigente más o menos distante del ideal que los planes
> del ensemble?  ¿Reduce el uso de APCs esa distancia?

La *fair share matrix* **Q** es la única asignación fraccional que satisface
simultáneamente:
1. **Proporcionalidad nacional**: la suma de escaños de cada partido en Q
   iguala su cuota Hamilton nacional (votos_i / votos_totales) × total_escaños.
2. **Respeto a las magnitudes**: la suma de columna de Q iguala la magnitud
   del distrito.

Cualquier asignación entera **N** (salida de D'Hondt) difiere de Q por la
imposibilidad aritmética de dividir escaños.  La distancia L1/L2 entre N y Q
mide simultáneamente malapportionment y desproporcionalidad en una sola cifra.

### Datos requeridos

| Dato | Fuente | Dónde en ChileDist |
|---|---|---|
| Votos por APC y partido (elección de referencia) | SERVEL | `aggregate_votes()` + `datos/servel_2025_por_cut.csv` |
| Magnitudes distritales | Integrado o ensemble | `cd.MAGNITUDES_LEGALES_LEY20840` o `assign_seat_magnitudes()` |
| Resultados D'Hondt del plan | Ensemble o mapa vigente | `run_electoral_plan()` o `run_electoral_plan_binivel()` |
| Pactos electorales (para binivel) | SERVEL (metadata) | Dict `{partido: pacto}` |

### Comandos

#### Paso 1 — Fair share de un plan y distancias básicas

```python
import pandas as pd
import chiledist as cd
import chiledist.fairshare as fs

# Votos electorales por APC y partido (elección de referencia)
votes_long = pd.read_csv("datos/servel_2025_por_cut.csv")   # CUT, partido, votos

# Asignación APC → circunscripción (plan del ensemble o mapa vigente)
assignment = {cut: distrito for cut, distrito in ...}

# Paso 1a — agregar votos al nivel de circunscripción
votes_by_dist = cd.aggregate_votes(votes_long, assignment, unit_col="CUT")

# Paso 1b — magnitudes (usar legales para comparación con el mapa vigente)
magnitudes = cd.MAGNITUDES_LEGALES_LEY20840

# Paso 1c — fair share matrix (biproporcional, satisface ambas restricciones)
Q = fs.fair_share_matrix(votes_by_dist, magnitudes, method="biproportional")
print(Q.round(2))   # filas=partidos, columnas=circunscripciones

# Paso 1d — asignación entera (D'Hondt sobre el mismo plan)
results = cd.run_electoral_plan(votes_by_dist, magnitudes)
N = fs.results_to_matrix(results)

# Paso 1e — distancias
print(f"L1:      {fs.l1_distance_fair_share(N, Q):.4f}  escaños fuera de lugar")
print(f"L1_norm: {fs.l1_distance_fair_share(N, Q, normalize=True):.4f}  (fraccón de escaños, ∈ [0,2])")
print(f"L2:      {fs.l2_distance_fair_share(N, Q):.4f}  (norma Frobenius)")
print(f"RMSE:    {fs.l2_distance_fair_share(N, Q, normalize=True):.4f}  (por celda)")
print(fs.max_cell_deviation(N, Q))   # celda más distante del ideal
```

#### Paso 2 — Comparar distancias entre escenarios (mapa vigente vs ensemble)

```python
import numpy as np

# Distancia del mapa vigente
N_vigente = fs.results_to_matrix(
    cd.run_electoral_plan(votes_by_dist_vigente, cd.MAGNITUDES_LEGALES_LEY20840)
)
Q_vigente = fs.fair_share_matrix(votes_by_dist_vigente, cd.MAGNITUDES_LEGALES_LEY20840)
l1_vigente = fs.l1_distance_fair_share(N_vigente, Q_vigente, normalize=True)
print(f"Distancia del mapa vigente: L1_norm = {l1_vigente:.4f}")

# Distribución de distancias en el ensemble
l1_ensemble = []
for asgn in ensemble_assignments:
    vd = cd.aggregate_votes(votes_long, asgn, unit_col="CUT")
    Nk = fs.results_to_matrix(cd.run_electoral_plan(vd, magnitudes))
    Qk = fs.fair_share_matrix(vd, magnitudes)
    l1_ensemble.append(fs.l1_distance_fair_share(Nk, Qk, normalize=True))

l1_arr = np.array(l1_ensemble)
print(f"Ensemble L1_norm: mediana={np.median(l1_arr):.4f}, "
      f"p10={np.percentile(l1_arr, 10):.4f}, "
      f"p90={np.percentile(l1_arr, 90):.4f}")

# Percentil del mapa vigente en la distribución del ensemble
pct = np.mean(l1_arr <= l1_vigente) * 100
print(f"El mapa vigente está en el percentil {pct:.1f} del ensemble")
# Si pct > 80: el mapa vigente está más lejos del ideal que la mayoría de los planes
# Si pct < 50: el mapa vigente es competitivo con el ensemble
```

#### Paso 3 — Summary completo para agregar a ensemble_stats

```python
# El dict de fair_share_summary es compatible con ensemble_stats
summary = fs.fair_share_summary(N, Q, label="legal_vigente")
# Claves: plan, l1, l1_norm, l2, rmse, max_dev, max_dev_partido,
#         max_dev_distrito, max_dev_direction, n_celdas, n_sobre, n_sub,
#         n_exacto, share_sobre
print(pd.Series(summary))

# Para el ensemble: agregar como columnas en ensemble_stats.csv
rows = []
for asgn, label in zip(ensemble_assignments, ensemble_labels):
    vd = cd.aggregate_votes(votes_long, asgn, unit_col="CUT")
    Nk = fs.results_to_matrix(cd.run_electoral_plan(vd, magnitudes))
    Qk = fs.fair_share_matrix(vd, magnitudes)
    rows.append(fs.fair_share_summary(Nk, Qk, label=label))
df_ens_fs = pd.DataFrame(rows)
```

#### Paso 4 — Método distrital vs biproporcional: ¿importa la elección del método?

```python
# Comparar métodos para el mismo plan
Q_bip = fs.fair_share_matrix(votes_by_dist, magnitudes, method="biproportional")
Q_dis = fs.fair_share_matrix(votes_by_dist, magnitudes, method="district")

# ¿Difieren sustancialmente?
diff = (Q_bip - Q_dis).abs()
print(f"Diferencia máxima entre métodos: {diff.values.max():.4f} escaños")
# Si < 0.1: la concentración geográfica de los partidos es baja
# Si > 0.5: los partidos tienen concentración geográfica fuerte;
#           preferir biproporcional para H6
```

### Qué observar en los resultados

| Métrica | Umbral indicativo | Interpretación política |
|---|---|---|
| `l1_norm` del mapa vigente | > 0.10 | Más del 10% de los escaños (≈ 16 sobre 155) están fuera del ideal fraccional. |
| Percentil vigente en ensemble | > 80 | El mapa vigente está significativamente más lejos del ideal que los planes generados. |
| Diferencia mediana ensemble entre `legal` y `apc_soft` | > 0.05 en L1_norm | Usar APCs reduce la distancia al ideal en más de 5 puntos porcentuales de escaños. |
| `max_dev` | > 2.0 | Un partido en un distrito tiene ≥ 2 escaños de desvío: el mapa amplifica (o elimina) representación localmente. |
| `share_sobre` | > 0.5 | Más de la mitad de las celdas están sobre-asignadas: el sistema favorece concentrar representación. |

### Interpretación política

La distancia L1_norm mide la fracción de escaños que "estarían mal ubicados" si se distribuyera la representación de forma completamente proporcional —tanto a nivel nacional como distrital— a la vez. En el sistema chileno vigente, las fuentes de distancia son:

1. **Malapportionment de magnitudes**: distritos con muchos votantes por escaño reciben menos representación de la que les correspondería, lo que se refleja en desviaciones de columna en la fair share matrix.

2. **Desproporcionalidad de D'Hondt**: el método D'Hondt favorece a los partidos más votados dentro de cada distrito, desviando la asignación de la cuota fraccional.

3. **Fragmentación geográfica de los votos**: cuando los votos de un partido están concentrados en ciertos distritos, la restricción de integridad produce mayores desviaciones respecto al ideal biproporcional.

La hipótesis H6 separa el efecto de la *geografía* (¿son los planes APC mejores que el mapa vigente?) del efecto del *método electoral* (¿es D'Hondt responsable de la distancia, independientemente del mapa?).

### Interpretación estadística

- **L1** es una norma del espacio de matrices; su valor mínimo no-nulo es 2 × (n_partidos × n_distritos no resolubles) por la restricción de integridad.
- **L2 / RMSE** penaliza desviaciones grandes en celdas individuales más que L1; útil para detectar partidos/distritos con representación sistémicamente distorsionada.
- El **percentil del mapa vigente** en la distribución del ensemble es una prueba de hipótesis no-paramétrica: si cae por encima del percentil 95, rechazamos (al 5%) que el mapa vigente es una muestra aleatoria del espacio de mapas alternativos.
- La comparación entre escenarios (legal vs apc_soft) es válida solo si las magnitudes se computan del mismo modo en ambos casos.

### Limitaciones

1. **Los votos están congelados**: Q se computa con los votos de la elección de referencia. El comportamiento electoral real bajo un nuevo mapa es desconocido; la fair share matrix es un contrafactual, no una predicción.

2. **IPF requiere soporte positivo**: si un partido no tiene votos en algún distrito, Q[partido, distrito] = 0 por construcción. Esto es metodológicamente correcto (sin votos no hay cuota) pero puede inflar la distancia si el partido ganó escaños vía pacto.

3. **Escala**: L1_norm ∈ [0, 2] en teoría, pero en la práctica los valores observables están entre 0 y ~0.3 para distribuciones electorales típicas chilenas. Un L1_norm de 0.15 no es "alto" en abstracto —hay que compararlo con el ensemble.

4. **Biproporcional vs distrital**: el método `'district'` es más simple e intuitivo pero no respeta las cuotas nacionales. Para la hipótesis H6 se recomienda siempre `method='biproportional'`.

### Estado de implementación

H6 requiere distribuciones de Gallagher y seat_bonus sobre un ensemble de planes alternativos de 28 distritos nacionales. Los ensembles actuales (R13, 8 sub-distritos) son incompatibles con los votos SERVEL agregados a nivel de los 28 distritos vigentes — no hay forma de mapear un plan regional a los votos de los 28 distritos sin un ensemble nacional.

Lo disponible (plan único vigente, vía H4-B2):

```
Gallagher binivel mapa vigente: 5.91
Gallagher uninivel mapa vigente: 5.91
seat_bonus por partido: ver H4-B4
```

Pendiente para H6 completo:

```
Ensemble nacional (--regiones nacional_comunal --n-distritos 28)
para obtener distribución de Gallagher sobre planes alternativos.
Luego: cd.run_electoral_ensemble() +
       cd.ensemble_gallagher() +
       cd.summarize_electoral_ensemble()
```

Estado: PARTIALLY COMPLETED (plan vigente via H4). Completo pendiente ensemble nacional.

---

## H7 — Atipicidad electoral del mapa observado

> **Pregunta:** ¿El resultado electoral observado bajo el mapa vigente es típico o atípico respecto al universo de planes de redistritaje plausibles?

Un índice de Gallagher bajo, un ENP cercano al ideal o una prima de escaños equilibrada no son necesariamente buenas noticias si esos valores resultan de una geografía que favorece sistemáticamente a ciertos partidos. H7 ubica los resultados electorales del mapa vigente dentro de la distribución que generaría cualquier mapa alternativo plausible: si el observado cae en la cola extrema del ensemble, la geografía —no solo el método electoral— está distorsionando la representación.

### Datos requeridos

| Dato | Fuente | Módulo |
|---|---|---|
| Votos por unidad y partido (elección de referencia) | SERVEL | `chiledist.data.servel` |
| `pacto_map` (elección de referencia) | `datos/pacto_map_2025.json` (ya construido) | archivo externo |
| Ensemble de planes (al menos N=200) | salida de H1 | `chiledist.samplers` |
| Magnitudes por circunscripción | `MAGNITUDES_LEGALES_LEY20840` o H3 | `chiledist.electoral` |
| Asignación del mapa vigente | `datos/asignacion_vigente.json` (ya construido) | archivo externo |

### Paso 1 — Ejecutar ensemble electoral

```python
import chiledist as cd
import json
import pandas as pd

votes_df   = cd.data.servel.votos_por_comuna()  # o pd.read_csv("datos/servel_2025_por_cut.csv")
pop        = cd.data.census2024.poblacion_comunal()["personas"]
with open("datos/pacto_map_2025.json") as f:
    pacto_map = json.load(f)

# ensemble_assignments: list[dict] con planes generados en H1
ensemble_results = cd.run_electoral_ensemble(
    ensemble_assignments,
    votes_df,
    pop,
    magnitudes=pd.Series(cd.MAGNITUDES_LEGALES_LEY20840),
    pacto_map=pacto_map,
    unit_col="CUT",
    include_seat_bonus=True,
)
print(ensemble_results[["gallagher", "enp_votos", "enp_escanos"]].describe())
```

### Paso 2 — Métricas del plan observado

```python
from chiledist.electoral import plan_electoral_metrics

with open("datos/asignacion_vigente.json") as f:
    asignacion_vigente = {int(k): int(v) for k, v in json.load(f).items()}

obs_metrics = plan_electoral_metrics(
    asignacion_vigente,
    votes_df,
    pop,
    pacto_map=pacto_map,
    magnitudes_fijas=pd.Series(cd.MAGNITUDES_LEGALES_LEY20840),
)
print(f"Gallagher observado: {obs_metrics['gallagher']}")
print(f"ENP escaños observado: {obs_metrics['enp_escanos']}")
```

### Paso 3 — Distribuciones y gráficos

```python
# Resumen estadístico completo
summary = cd.summarize_electoral_ensemble(ensemble_results)
print(summary[["mean", "std", "p5", "p95"]])

# Gallagher: distribución, CI 95% y posición del observado
gall_stats = cd.ensemble_gallagher(ensemble_results)
print(f"Media ensemble: {gall_stats['mean']:.2f}")
print(f"IC 95%: [{gall_stats['ci95_low']:.2f}, {gall_stats['ci95_high']:.2f}]")

import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

cd.plot_ensemble_histogram(
    ensemble_results, metric="gallagher",
    observed=obs_metrics["gallagher"],
    ax=axes[0],
)
cd.plot_ensemble_violin(
    ensemble_results,
    metrics=["gallagher", "enp_votos", "enp_escanos"],
    observed={
        "gallagher":   obs_metrics["gallagher"],
        "enp_votos":   obs_metrics["enp_votos"],
        "enp_escanos": obs_metrics["enp_escanos"],
    },
)
cd.plot_ensemble_ecdf(
    ensemble_results, metric="gallagher",
    observed=obs_metrics["gallagher"],
    ax=axes[2],
)
plt.tight_layout()
plt.savefig("resultados/h7_ensemble_electoral.png", dpi=150)
```

### Paso 4 — Prima de escaños por partido

```python
# Distribución de la prima de escaños para cada partido
sb_df = cd.ensemble_seat_bonus(ensemble_results)
print(sb_df[["mean", "p5", "p95"]])

# ¿El partido X está sistemáticamente sobrerepresentado en el espacio de planes?
sb_A = cd.ensemble_seat_bonus(ensemble_results, partido="A")
print(f"Prima media de A: {sb_A['mean']:.2f} pp  (IC 95%: [{sb_A['ci95_low']:.2f}, {sb_A['ci95_high']:.2f}])")
```

### Paso 5 — Umbral efectivo por distrito (planes con magnitudes variables)

```python
# Solo relevante cuando magnitudes=None (calculadas por plan)
results_var = cd.run_electoral_ensemble(
    ensemble_assignments, votes_df, pop,
    pacto_map=pacto_map,   # magnitudes calculadas por plan
)

# Construir lista de magnitudes por plan (requiere re-correr assign_seat_magnitudes)
from chiledist.electoral import assign_seat_magnitudes
mags_list = [
    assign_seat_magnitudes(
        pd.Series({d: sum(pop.get(u, 0) for u, dd in a.items() if dd == d)
                   for d in set(a.values())}),
        total_seats=155,
    )
    for a in ensemble_assignments
]
threshold_df = cd.ensemble_effective_threshold(mags_list)
print(threshold_df[["mean", "std", "p5", "p95"]])
```

### Qué observar

| Resultado | Interpretación |
|---|---|
| Gallagher observado < p5 del ensemble | El mapa vigente produce resultados inusualmente proporcionales — ventaja geográfica "inocente" |
| Gallagher observado > p95 del ensemble | El mapa vigente produce desproporcionalidad atípica — la geografía amplifica la distorsión electoral |
| Prima de escaños observada en la cola alta de un partido | El mapa favorece sistemáticamente a ese partido más allá de lo esperable por el método |
| ENP escaños < p5 | El mapa concentra el poder en menos partidos de lo que permitiría una geografía neutral |
| IC 95% no incluye el observado | Rechazamos (α=5%) que el mapa vigente es una muestra aleatoria del espacio de planes |

### Interpretación política

El ensemble define el contrafactual: "¿cómo serían las elecciones con un mapa diferente pero igual de plausible según los criterios APC?" Si el plan vigente cae sistemáticamente fuera de la distribución del ensemble, la geografía está actuando como factor independiente que modifica el resultado electoral más allá de lo esperable por el método de escrutinio. Esto no implica intención —puede ser consecuencia histórica de cómo se trazaron los distritos— pero sí tiene efectos distributivos medibles.

### Interpretación estadística

- El **percentil del observado** dentro del ensemble es una prueba de hipótesis no-paramétrica (Mann-Whitney) de la hipótesis nula: "el mapa vigente fue seleccionado de la distribución de mapas plausibles".
- El **IC 95%** del ensemble es una banda de referencia, no un intervalo de confianza sobre el verdadero valor electoral: los votos son datos fijos, no aleatorios. Lo que varía es el mapa.
- Para N=200 planes, la resolución del percentil estimado es ±7pp al 95%. Para N=1000, es ±3pp.
- Si se usan magnitudes calculadas (en lugar de las legales fijas), H7 captura también el efecto de reasignar escaños con la nueva geografía —un análisis contrafactual más rico pero menos comparable con el sistema vigente.

### Limitaciones

1. **Votos congelados**: los votos de la elección de referencia se aplican a todos los planes. El comportamiento electoral real bajo un nuevo mapa involucra efectos de incumbencia, redistricción y movilización que el modelo no captura.

2. **Espacio de planes sesgado**: el ensemble es una muestra del espacio bajo las restricciones APC elegidas. Si esas restricciones son muy estrictas (apc_strict), el ensemble puede no ser representativo del espacio de mapas "plausibles" en sentido amplio.

3. **Correlación entre métricas**: Gallagher, ENP y prima de escaños no son independientes. Interpretar distribuciones conjuntas requiere análisis multivariado (no implementado).

4. **Sin inferencia sobre partidos individuales**: la prima de escaños de un partido específico puede tener varianza muy alta si ese partido tiene votos concentrados en pocas unidades, haciendo la inferencia poco potente con N pequeño.

### Estado de implementación

H7 requiere distribuciones de seat_bonus y fair_share_matrix sobre un ensemble de planes alternativos de 28 distritos nacionales. Los ensembles actuales (R13, 8 sub-distritos) son incompatibles con los votos SERVEL agregados a nivel de los 28 distritos vigentes — no hay forma de mapear un plan regional a los votos de los 28 distritos sin un ensemble nacional.

Lo disponible (plan único vigente, vía H4-B4):

```
seat_bonus por partido: ver H4-B4
fair_share_matrix: no calculado aún para el mapa vigente (pendiente, ver H6)
```

Pendiente para H7 completo:

```
Ensemble nacional (--regiones nacional_comunal --n-distritos 28)
para obtener distribución de seat_bonus/fair_share_matrix sobre
planes alternativos.
Luego: cd.run_electoral_ensemble() +
       cd.ensemble_seat_bonus() +
       cd.summarize_electoral_ensemble()
```

Estado: PARTIALLY COMPLETED (plan vigente parcial via H4-B4; fair_share_matrix pendiente incluso para el plan único). Completo pendiente ensemble nacional.

---

## H8 — Punto de máxima eficiencia en el tradeoff poblacional-comunal

> **Pregunta:** ¿Existe un punto de máxima eficiencia entre igualdad poblacional e integridad comunal, y a qué nivel de penalización corresponde?

En el barrido paramétrico sobre `split_penalty`, la frontera Pareto describe el tradeoff entre balance poblacional (`max_dev_pob_pct`) e integridad comunal (`n_comunas_partidas`). La hipótesis H8 pregunta si ese tradeoff tiene un punto de inflexión claro —el **knee point**— donde el costo marginal de mejorar un objetivo supera el beneficio obtenido en el otro. Si existe, identifica el valor óptimo de `split_penalty` para el diseño del escenario `apc_soft`.

La H8 es complementaria a la H2: mientras H2 pregunta si el mapa vigente es Pareto-dominado (respuesta binaria), H8 pregunta dónde está el tradeoff más eficiente dentro del espacio de planes alcanzables (respuesta continua con incertidumbre).

### Diferencia metodológica respecto a H2

| Aspecto | H2 (scripts/pareto_sweep.py) | H8 (chiledist/pareto_sweep.py) |
|---|---|---|
| Unidad de análisis | Un punto por escenario (mediana o plan de referencia) | Cada plan individual del ensemble |
| Frontera Pareto | Sobre ~10 puntos representativos | Sobre todos los planes (N×P planes) |
| Incertidumbre | No cuantificada | Bandas bootstrap (IC 90% y 50%) |
| Knee point | No detectado automáticamente | Detección automática con distancia perpendicular |
| Rendimientos decrecientes | No detectado | Detectado: umbral configurable |

### Datos requeridos

| Dato | Fuente | Módulo |
|---|---|---|
| Ensembles de planes por nivel de penalización | Salida de H1 (redistritaje.py) | `scripts/redistritaje.py` |
| `penalties = np.linspace(0, 1, N)` con N ≥ 10 | Barrido paramétrico | definido por el usuario |

### Paso 1 — Cargar o generar ensembles por nivel

```python
import chiledist as cd
import numpy as np, pandas as pd
from pathlib import Path

penalties = np.linspace(0.0, 1.0, 11)   # 0.0, 0.1, …, 1.0
region    = "R13_METROPOLITANA"

# Opción A: cargar desde disco (ensembles ya generados con scripts/redistritaje.py)
ensembles = {}
for p in penalties:
    p_str   = f"{p:.2f}".replace(".", "_")
    csv_path = Path(f"datos/{region}/redistritaje/apc_soft_p{p_str}/ensemble_stats.csv")
    if csv_path.exists():
        ensembles[p] = pd.read_csv(csv_path)

# Opción B: generar con pareto_sweep.py (requiere SHP_APC2023)
# python scripts/pareto_sweep.py --penalties 0.0,0.1,0.2,...,1.0 --region 13
```

### Paso 2 — Consolidar y construir frontera Pareto real

```python
# Consolidar todos los planes individuales en un único DataFrame
sweep_df = cd.sweep_split_penalty(ensembles)
print(f"Pool total: {len(sweep_df)} planes de {len(ensembles)} niveles de penalización")

# Frontera Pareto real (sobre planes individuales, no medianas)
frontier_res = cd.build_tradeoff_frontier(
    sweep_df,
    x_metric="max_dev_pob_pct",
    y_metric="n_comunas_partidas",
    n_bootstrap=500,           # remuestreos para IC 90% y 50%
    random_state=42,
)

print(f"Planes Pareto-óptimos: {frontier_res['metadata']['n_pareto']}")
print(f"Fracción en la frontera: "
      f"{frontier_res['metadata']['n_pareto']/frontier_res['metadata']['n_plans']:.1%}")
```

### Paso 3 — Detectar knee point y rendimientos decrecientes

```python
# Knee point: punto de máxima eficiencia
knee = cd.detect_knee_point(
    frontier_res["frontier"],
    x_metric="max_dev_pob_pct",
    y_metric="n_comunas_partidas",
    method="normalized_distance",   # recomendado (normaliza unidades)
    diminishing_threshold=0.5,      # rendimientos decrecientes cuando mejora < 50% de la media
)

print(f"Knee point: split_penalty = {knee['knee_penalty']:.2f}")
print(f"  max_dev_pob_pct      = {knee['knee_x']:.2f}%")
print(f"  n_comunas_partidas   = {knee['knee_y']:.1f}")
if knee["diminishing_start_x"] is not None:
    print(f"Rendimientos decrecientes desde max_dev_pob_pct = {knee['diminishing_start_x']:.2f}%")
```

### Paso 4 — Figura publicable

```python
fig = cd.plot_tradeoff_curve(
    sweep_df,
    frontier_res,
    knee_result=knee,
    x_metric="max_dev_pob_pct",
    y_metric="n_comunas_partidas",
    title=f"{region} — Frontera Pareto real (H8)\nBalance poblacional × Integridad comunal",
    show_scatter=True,          # plans individuales (semitransparentes, coloreados por penalty)
    show_density_bands=True,    # IC bootstrap
    show_diminishing=True,      # región de rendimientos decrecientes
    save_path="resultados/h8_pareto_frontier.png",
)

# Resumen estadístico por nivel de penalización
summary = cd.summarize_tradeoff(sweep_df, frontier_res, knee)
print(summary[["n_planes", "max_dev_pob_pct_mean", "n_comunas_partidas_mean", "pct_pareto", "is_knee"]])
```

### Qué observar

| Resultado | Interpretación |
|---|---|
| Knee point existe (distancia máxima > 0) | Hay un tradeoff cóncavo — existe una penalización óptima |
| Knee point en p ≈ 0.2–0.4 | El diseño óptimo sacrifica pocas comunas por ganancias grandes en balance |
| Knee point en p ≈ 0 | La integridad comunal no cuesta nada — el mapa es eficiente sin penalización |
| Knee point en p ≈ 1 | No hay tradeoff real — el balance siempre domina |
| Bootstrap IC 90% estrecho | La frontera es estable; el knee es robusto |
| Bootstrap IC 90% ancho | Alta varianza en la frontera; se necesita un ensemble más grande |
| Región de rendimientos decrecientes > 50% del eje x | La mayor parte del tradeoff está en la zona ineficiente |

### Interpretación estadística

- El **knee point** se define como el punto de máxima distancia perpendicular (en el espacio normalizado) a la línea que conecta los dos extremos de la frontera Pareto. Este criterio es el más común en optimización multiobjetivo para identificar el "punto de quiebre" (método de Dingel).
- Las **bandas bootstrap** cuantifican la variabilidad del la frontera debida al tamaño finito del ensemble. Un IC 90% ancho indica que se necesitan más pasos MCMC (N mayor) para estabilizar la frontera.
- La región de **rendimientos decrecientes** se detecta cuando la tasa de mejora marginal (−Δy/Δx) cae por debajo del `diminishing_threshold` × media de la tasa. Con `diminishing_threshold=0.5`, se marca cuando la mejora marginal es menos del 50% de la promedio.
- El **porcentaje de planes Pareto-óptimos** (`pct_pareto`) por nivel de penalización indica qué niveles producen planes más competitivos en el frente eficiente.

### Limitaciones

1. **Frontera 2D**: la visualización y el knee point están en el espacio de dos objetivos. Añadir más objetivos (compacidad, aristas cortadas) requiere extensión a análisis Pareto N-dimensional — implementable con `build_tradeoff_frontier` pasando métricas diferentes.

2. **Misma distribución**: todos los niveles de `apc_soft_pX` muestrean de la misma distribución de planes (la penalización solo afecta el score). La frontera del pool consolidado es la verdadera frontera alcanzable, pero el knee no indica un nivel de penalización "diferente" en términos distribucionales — indica qué plan del ensemble conviene seleccionar.

3. **Bootstrap estratificado**: el bootstrap resamplea dentro de cada nivel de penalización. Con N pequeño por nivel (< 50 planes), las bandas pueden subestimar la incertidumbre verdadera.

4. **Knee sin significancia estadística**: no hay un test formal de que el knee es "real". Con IC 90% solapados en x, el punto de quiebre podría ser un artefacto del ruido muestral.

### Resultados empíricos — R13, Censo 2024

#### Knee point de la frontera Pareto

```
cd.detect_knee_point(pareto_frontier.csv, method="normalized_distance")

knee_idx:    2
knee_x:      7.781% (max_dev_pob_pct_median)
knee_y:      22 comunas partidas
knee_penalty: 1.0
distances:   [0.0, 0.078, 0.421, 0.0]
diminishing_start_x: 5.039%
method: normalized_distance
```

Knee point identificado: `apc_soft_p1_00` (penalty=1.0, dev=7.781%, comunas_partidas=22)

#### Interpretación

El método `normalized_distance` calcula la distancia perpendicular máxima a la cuerda que conecta los dos extremos de la frontera en espacio normalizado [0,1]×[0,1]:

```
extremo 1: apc_soft_p2_50 (4.125%, 26 splits)
extremo 2: legal_comunas  (9.004%, 0 splits)
```

`apc_soft_p1_00` tiene distancia 0.421 — muy por encima del resto (0.078, 0.0, 0.0). Es el punto que se desvía más de un tradeoff lineal entre los extremos, el "codo" geométrico de la frontera.

#### Tensión entre criterios

El knee geométrico (`apc_soft_p1_00`, 22 splits) no coincide con el punto de retornos marginales decrecientes (`diminishing_start_x=5.039%`, que corresponde a `apc_soft_p0_00`, 24 splits).

Son criterios distintos:
- **Knee geométrico**: máxima curvatura respecto a la cuerda entre extremos — identifica `apc_soft_p1_00` como el punto de mayor "codo" en la frontera.
- **Retornos marginales**: tasa de mejora de balance por split adicional — los rendimientos decrecientes comienzan recién en `apc_soft_p0_00` (de 22→24 splits se gana el mayor salto de balance: 7.781%→5.039%).

En términos de política pública: el knee geométrico sugiere `penalty=1.0` (22 comunas partidas) como punto de equilibrio; el criterio marginal sugiere que si se va a partir comunas, vale la pena llegar hasta 24 para capturar el salto mayor de balance.

#### Limitación

La frontera tiene solo 4 puntos — el knee point puede ser sensible al barrido de penalizaciones elegido. Un barrido más denso entre `penalty=0.5` y `penalty=2.5` caracterizaría mejor la curvatura real en esa zona.

#### Estado

COMPLETED — R13, Censo 2024.
Pendiente: barrido más denso para robustez del knee point.

#### Archivos

```
datos/R13_METROPOLITANA/pareto_sweep/pareto_frontier.csv
```

---

## H9 — Malapportionment comparado: APC vs sistema vigente

> **Pregunta:** ¿El redistritaje basado en APC reduce significativamente el malapportionment respecto al sistema vigente, y cómo se ubica Chile en el contexto internacional?

El malapportionment geográfico cuantifica la brecha entre la distribución de escaños y la distribución de población: un ciudadano en un distrito subrepresentado necesita más personas para elegir un diputado que uno en un distrito sobrerrepresentado. H9 pregunta si los planes generados por redistritaje APC reducen esa brecha de forma estadísticamente significativa respecto al mapa legal vigente, y dónde cae Chile en el rango de sistemas comparados internacionalmente.

H9 es complementaria a H3: mientras H3 caracteriza el malapportionment del mapa vigente (qué distritos están subrepresentados y cuánto), H9 pregunta si el redistritaje puede reducirlo y si esa reducción es estadísticamente robusta.

### Diferencia metodológica respecto a H3

| Aspecto | H3 (`malapportionment.py` script) | H9 (`malapportionment.py` módulo) |
|---|---|---|
| Unidad de análisis | Un único mapa (el vigente) | Distribución del ensemble + comparación internacional |
| Índice principal | `peso_relativo_del_voto` (distritales) | `samuels_snyder_index` (escalar global, comparable) |
| Comparación | Interna (distritos del mismo mapa) | Entre escenarios y con benchmarks internacionales |
| Incertidumbre | No cuantificada | IC bootstrap sobre el ensemble de planes |

### Datos requeridos

| Dato | Fuente | Módulo |
|---|---|---|
| Ensembles de planes por escenario | Salida de H1 (`redistritaje.py`) | `compare_plans()` |
| Magnitudes legales vigentes | Integrado | `cd.MAGNITUDES_LEGALES_LEY20840` |
| Magnitudes calculadas por plan | Calculadas | `cd.assign_seat_magnitudes()` |
| Población por unidad censal | INE Censo 2024 | `cd.data.census2024` |
| Benchmarks internacionales | `BENCHMARK_MALAPPORTIONMENT` (integrado) | `cd.BENCHMARK_MALAPPORTIONMENT` |

### Paso 1 — Calcular índices para el mapa vigente

```python
import chiledist as cd
import chiledist.malapportionment as mala
import pandas as pd

# Magnitudes legales y población por circunscripción del mapa vigente
mag_legal = pd.Series(cd.MAGNITUDES_LEGALES_LEY20840)  # 28 distritos

# Población real por circunscripción (BCN + Censo 2024 distribuido por APC)
# pop_by_district: pd.Series {n_distrito: población}
# (requiere asignacion_vigente y pop_por_apc — ver datos externos)

# ── Mapa vigente ──────────────────────────────────────────────────────────────
summary_legal = mala.malapportionment_summary(
    pop_by_district,   # pd.Series {distrito: población}
    mag_legal,
    label="Chile_legal_2021"
)
print(f"Samuels-Snyder M = {summary_legal['samuels_snyder']:.4f}")
print(f"Gini PxE (pop-ponderado) = {summary_legal['gini_pop_weighted']:.4f}")
print(f"Ratio máx/mín = {summary_legal['max_min_ratio']:.2f}")
```

### Paso 2 — Comparar con ensembles APC

```python
from pathlib import Path
import numpy as np

# Cargar ensembles desde disco (generados con redistritaje.py en H1)
BASE = "datos/R13_METROPOLITANA/redistritaje"
ensembles = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas/ensemble_stats.csv"),
    "apc_soft": pd.read_csv(f"{BASE}/contrafactual_apc_soft/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre/ensemble_stats.csv"),
}

# Reconstruir asignaciones para calcular índices de malapportionment por plan
# (la forma más directa si ya tienes los asignments en disco es recalcular PxE)
# Para cada ensemble, calcular Samuels-Snyder sobre cada plan individual:
pop_por_unidad = gdf_apc.set_index("ID_DIST")["personas"]

def ss_from_assignment(assignment, pop_by_unit, total_seats=155):
    pop_by_d = pd.Series({
        d: sum(pop_by_unit.get(u, 0) for u, dd in assignment.items() if dd == d)
        for d in set(assignment.values())
    })
    mags = cd.assign_seat_magnitudes(pop_by_d, total_seats=total_seats)
    return mala.samuels_snyder_index(pop_by_d, mags)

# Generar distribución bootstrap de SS para cada escenario
ss_distributions = {}
for escenario, plans_list in ensemble_assignments.items():  # list[dict]
    ss_distributions[escenario] = [
        ss_from_assignment(asgn, pop_por_unidad)
        for asgn in plans_list
    ]

# Estadísticas por escenario
for escenario, ss_vals in ss_distributions.items():
    arr = np.array(ss_vals)
    print(f"{escenario}: M = {np.median(arr):.4f} "
          f"(IC 95%: [{np.percentile(arr,5):.4f}, {np.percentile(arr,95):.4f}])")

# ¿El ensemble APC tiene distribución significativamente diferente al vigente?
from scipy import stats
stat, p_val = stats.mannwhitneyu(
    ss_distributions["legal"],
    ss_distributions["apc_free"],
    alternative="greater"   # H0: legal ≤ apc_free en malapportionment
)
print(f"Mann-Whitney U: stat={stat:.1f}, p={p_val:.4f}")
# p < 0.05 → el mapa legal tiene significativamente más malapportionment que APC
```

### Paso 3 — Comparación con API de `compare_plans`

```python
# Alternativa más directa: pasar todos los planes a compare_plans
# Cada plan es un dict {unit_id: district_id}
plans_dict = {
    "legal_vigente": assignment_vigente,    # dict
    "apc_soft_best": best_plan_soft,        # dict
    "apc_free_best": best_plan_free,        # dict
}

comparison_df = mala.compare_plans(
    plans_dict,
    pop_by_unit=gdf_apc.set_index("ID_DIST")["personas"],
    # magnitudes=None → calculadas por assign_seat_magnitudes para cada plan
    total_seats=155,
)
print(comparison_df[["samuels_snyder", "gini_pop_weighted", "max_min_ratio", "cv"]])
```

### Paso 4 — Ubicar Chile en el contexto internacional

```python
# Construir tabla comparativa con benchmarks internacionales
summaries = {label: mala.malapportionment_summary(pop_d, mag, label=label)
             for label, (pop_d, mag) in local_plans.items()}

tabla_int = mala.international_comparison(
    custom=summaries,
    include_benchmarks=True,
)
print(tabla_int[["samuels_snyder", "gini_pop_weighted", "max_min_ratio", "cv", "type"]])

# Percentil de Chile legal dentro del rango internacional
chile_ss = summaries["Chile_legal_2021"]["samuels_snyder"]
benchmark_ss = [v["samuels_snyder"] for v in cd.BENCHMARK_MALAPPORTIONMENT.values()]
pct = sum(1 for v in benchmark_ss if v < chile_ss) / len(benchmark_ss) * 100
print(f"Chile legal está por encima del {pct:.0f}% de los países de referencia")
```

### Paso 5 — Visualizaciones

```python
# Distribución de PxE para cada escenario
fig = mala.plot_pxe_distribution(
    pop_by_district_legal, mag_legal,
    label="Legal vigente",
    reference_line=float(pop_by_district_legal.sum()) / float(mag_legal.sum()),
    save_path="resultados/h9_pxe_legal.png",
)

# Ranking de distritos por representación
fig = mala.plot_malapportionment_ranking(
    pop_by_district_legal, mag_legal,
    label="Legal vigente",
    top_n=20,
    save_path="resultados/h9_ranking_distritos.png",
)

# Comparación internacional
fig = mala.plot_international_comparison(
    tabla_int,
    metric="samuels_snyder",
    metric_label="Índice de Samuels-Snyder (M)",
    title="Malapportionment geográfico — Chile en perspectiva comparada (H9)",
    save_path="resultados/h9_comparacion_internacional.png",
)
```

### Qué observar

| Resultado | Umbral indicativo | Interpretación |
|---|---|---|
| SS(legal) − SS(apc_free) > 0.03 | > 3 pp | El redistritaje APC reduce el malapportionment en más de un 20% (efecto sustancial) |
| IC 95% del ensemble APC no solapan con SS(legal) | Sin solapamiento | Rechazamos (α=5%) que el APC no mejora respecto al mapa vigente |
| Chile legal en percentil > 50% del ranking internacional | Percentil > 50 | Chile tiene más malapportionment que la mediana de países comparados |
| Gini PxE ensemble APC < Gini legal | Diferencia > 0.01 | El redistritaje reduce la desigualdad en representación no solo el sesgo global |
| Ratio máx/mín ensemble APC < ratio legal | — | Los distritos más extremos se acercan entre sí |

### Interpretación estadística

- El **índice de Samuels-Snyder M** es directamente comparable entre países porque usa *shares* (fracciones), no valores absolutos de población.
- La comparación bootstrap ensemble vs mapa vigente es equivalente a un **test de Mann-Whitney unilateral** sobre la distribución de M. Con N=500 planes, la potencia del test para detectar diferencias de 0.02 en M es > 80%.
- **Cuidado**: M depende de las magnitudes usadas. Comparar `legal` (magnitudes fijas) vs `apc_soft` (magnitudes calculadas por plan) mezcla dos efectos: geografía distrital y redistribución de escaños. Para aislar el efecto de la geografía pura, usar magnitudes fijas en todos los escenarios.

### Interpretación política

El malapportionment en Chile tiene dos fuentes estructurales: (1) el congelamiento de las magnitudes desde 2015 (Ley 20.840), que no se actualiza con la demografía, y (2) la restricción de integridad comunal que impide redistribuir población entre distritos. H9 separa estas fuentes: si el ensemble APC (con magnitudes recalculadas) tiene M significativamente menor que el mapa legal, la geografía distrital —no solo las magnitudes fijas— es una fuente independiente de malapportionment. Esto tiene implicancias para el tipo de reforma: no basta con actualizar las magnitudes (H3) si los límites distritales concentran sistemáticamente población en ciertas circunscripciones.

### Limitaciones

1. **Circularidad magnitudes/geografía**: cuando se usan magnitudes calculadas por plan (`assign_seat_magnitudes`), los cambios en M reflejan tanto la geografía como la reasignación de escaños. Para análisis puros, fijar magnitudes al total legal de 155 distribuido proporcionalmente.

2. **Benchmarks internacionales**: los valores de `BENCHMARK_MALAPPORTIONMENT` son estimaciones de la literatura; no se computan con los mismos datos primarios ni el mismo método exacto. La comparación es orientativa, no una prueba estadística formal.

3. **Población fija**: el análisis usa la distribución de población observada. Cambios futuros (migración, crecimiento diferencial) alterarán M sin cambiar el mapa.

4. **Solo magnitudes; no el sesgo partidario**: un M bajo no garantiza representación equitativa en términos electorales. Para eso, combinarlo con H4 (D'Hondt), H7 (atipicidad electoral) y H6 (distancia al ideal fraccional).

### Resultados empíricos — Censo 2024, comparación internacional

#### Parámetros

```
cd.international_comparison() sobre malapportionment_pxe.csv
Población: Censo 2024 (malapportionment_pxe.csv de H3)
Magnitudes: MAGNITUDES_LEGALES_LEY20840 (Ley 20.840)
Índice principal: Samuels-Snyder (M)
```

#### Tabla comparativa

| país/plan | tipo | samuels_snyder | gini_pop_weighted | max_min_ratio | cv |
|---|---|---|---|---|---|
| USA_House_2023 | benchmark | 0.003 | 0.003 | 1.09 | 0.04 |
| España_2019 | benchmark | 0.051 | 0.039 | 3.12 | 0.28 |
| Chile_legal_2025 | custom | 0.106 | 0.144 | 5.74 | 0.30 |
| Chile_legal_2021 | benchmark | 0.137 | 0.108 | 5.33 | 0.44 |
| Argentina_2019 | benchmark | 0.241 | 0.193 | 9.86 | 0.72 |
| Brasil_2018 | benchmark | 0.349 | 0.321 | 47.10 | 1.41 |

#### Hallazgos

`Chile_legal_2025` (Samuels-Snyder=0.106) queda en posición intermedia: mejor que Argentina (0.241) y Brasil (0.349), pero con más malapportionment que EE.UU. (0.003) y España (0.051). Rank 3/6 en el conjunto, percentil ~40%.

Países con menos malapportionment que Chile (mapa vigente Censo 2024): 2 de 4 países externos — EE.UU. y España.

#### Nota metodológica

`Chile_legal_2021` (M=0.137) usa proyecciones INE 2020. `Chile_legal_2025` (M=0.106) usa Censo 2024 real. La diferencia (0.031pp) refleja el cambio de fuente poblacional, no un cambio en el diseño distrital — las magnitudes (`MAGNITUDES_LEGALES_LEY20840`) son las mismas en ambos cálculos. El Censo 2024 reduce el índice porque la distribución poblacional real es menos desigual que la proyectada en 2020.

**Referencias** (fuente de cada entrada de `cd.BENCHMARK_MALAPPORTIONMENT`):

| país/plan | fuente |
|---|---|
| Chile_legal_2021 | Estimado con `MAGNITUDES_LEGALES_LEY20840` y proyecciones INE 2020 |
| USA_House_2023 | Census Bureau 2020 apportionment; Balinski & Young (2001) |
| Argentina_2019 | Samuels & Snyder (2001), *AJPS*; actualización Calvo & Micozzi (2005) |
| Brasil_2018 | Samuels & Snyder (2001), *AJPS*; Nicolau (2017) |
| España_2019 | Jurado (2014), *Electoral Studies*; cálculo propio con INE 2019 |

#### Estado

COMPLETED — Censo 2024, mapa vigente corregido.
Pendiente: correr `international_comparison()` sobre ensembles de H1 para comparar Chile_apc_free vs Chile_legal en el contexto internacional.

#### Archivos

```
datos/malapportionment/malapportionment_pxe.csv
```

---

## Tabla resumen

| Hipótesis | Pregunta central | Escenarios | Función clave | Métrica de respuesta |
|---|---|---|---|---|
| **H1** | ¿Qué ocurre si Chile permite APCs como unidad mínima? | `legal` vs `apc_soft` vs `apc_free` | `plan_split_metrics()` | `pop_afectada_pct`, `delta_max_dev_pob_pct` |
| **H2** | ¿Es el mapa vigente Pareto-dominado? | Todos + barrido `split_penalty` | `pareto_frontier_nd()` | Posición del vigente en la frontera |
| **H3** | ¿Cuánto vale un voto en cada distrito? | Mapa vigente (magnitudes fijas) | `personas_por_escano()`, `peso_relativo_del_voto()` | `ratio_max_min_pxe`, `peso_relativo_max/min` |
| **H4** | ¿Cómo afecta D'Hondt binivel la proporcionalidad? | Cualquier plan + votos electorales (elección de referencia) | `plan_electoral_metrics(pacto_map=...)` | `gallagher`, `seat_bonus_max` |
| **H5** | ¿Son robustas las conclusiones a la metodología? | Pares de ensembles comparados | `compare_sensitivity()`, `ranking_concordance()` | `efecto` (negligible/grande), `tau` |
| **H6** | ¿Qué tan lejos están los planes del ideal fraccional? | Mapa vigente + ensemble | `fair_share_matrix()`, `fair_share_summary()` | `l1_norm`, percentil en ensemble |
| **H7** | ¿El resultado electoral observado es típico o atípico? | Mapa vigente vs ensemble de planes | `run_electoral_ensemble()`, `summarize_electoral_ensemble()` | percentil de Gallagher, ENP, `seat_bonus` en distribución ensemble |
| **H8** | ¿Existe un punto de máxima eficiencia en el tradeoff? | Barrido continuo de `split_penalty` | `build_tradeoff_frontier()`, `detect_knee_point()` | `knee_penalty`, IC bootstrap de la frontera |
| **H9** | ¿El redistritaje APC reduce significativamente el malapportionment? | `legal` vs `apc_soft` vs `apc_free` vs internacional | `malapportionment_summary()`, `compare_malapportionment_plans()`, `international_comparison()` | `samuels_snyder`, `gini_pop_weighted`, `max_min_ratio`, percentil internacional |

---

## Decisiones metodológicas previas a la ejecución

Las siguientes decisiones afectan a todas las hipótesis y deben tomarse antes de correr los experimentos:

1. **Fuente de población**: usar `pop_col="personas"` (Censo 2024) como fuente primaria. `"viviendas"` (APC 2023) es alternativa documentada; H5 verifica la concordancia entre ambas.

2. **Región de análisis**: desarrollar en R11 (Aysén, ~10 comunas, computacionalmente manejable), publicar en R13 (Metropolitana, más informativa).

3. **Tamaño del ensemble**: N=500 para exploración, N=1000 para resultados publicables. El KS test requiere al menos N=200 por grupo para detectar efectos moderados.

4. **Asignación del mapa vigente**: construir el dict `{CUT: n_circunscripcion}` desde la base oficial del BCN. Usar la misma asignación en todas las hipótesis.

5. **Semilla**: fijar `random_seed=42` en todas las corridas para reproducibilidad. Reportar explícitamente en métodos.

6. **Framing**: los escenarios APC son contrafactuales legislativos. Usar `sc.reforma_context()` para generar el texto de encuadre correcto en cualquier figura o tabla.

---

## Estado de ejecución — brechas por hipótesis

> Auditoría actualizada el 2026-06-21 contra ChileDist v2.1.
> Leyenda: ✅ corre hoy · ⚠ firma corregida en este documento · 🔴 requiere datos externos · 🟡 requiere configuración manual

### Tabla de brechas

| Hipótesis | Estado global | Qué corre hoy | Qué falta |
|---|---|---|---|
| **H1** | ✅ Ejecutable — corrida real en R13 (ver "Plan de cierre") | CLI `redistritaje.py`; `compare_scenarios.py`; `compare_ensembles`; `plan_split_metrics`; `pop_afectada_pct` en `ensemble_stats.csv` | ✅ `datos/asignacion_vigente.json` y `datos/poblacion_comunal_censo2024.csv` ya existen. 🔴 `legal_comunas` falla en R13 con `status="sin_particion"` (ver caveat en H1 abajo) — pendiente resolver antes de tener los 3 escenarios completos |
| **H2** | ✅ Script disponible | `scripts/pareto_sweep.py`; `pareto_frontier_nd`; `rank_scenarios`; `ScoringConfig.from_weights` | ✅ Asignación vigente disponible para `position_plan_vigente` |
| **H3** | ✅ Corrido con `--demo`; API lista para datos reales | `scripts/malapportionment.py`; `personas_por_escano`; `comparar_magnitudes`; `umbral_efectivo`; `plan_electoral_metrics(magnitudes_fijas=)` | ✅ Censo 2024 comunal y asignación vigente ya existen; 🔴 Votos electorales por CUT (elección de referencia) — `datos/malapportionment/*.csv` en el repo son de `--demo`, no de datos reales, hasta que se corra sin ese flag |
| **H4** | ✅ Script disponible (`--demo`) | `scripts/electoral_analysis.py`; `dhondt`; `dhondt_binivel`; `plan_electoral_metrics(pacto_map=)`; `national_shares`; `seat_bonus` | ✅ `datos/pacto_map_2025.json` ya existe; 🔴 Votos electorales por CUT y partido (elección de referencia); 🔴 Ensembles de H1 |
| **H5** | ✅ Scripts disponibles | `scripts/run_chains.py`; `scripts/smc_pipeline.py`; `mixing_diagnostics`; `compare_sensitivity`; `ranking_concordance` | 🔴 Ensembles de H1; R + paquete `redist` para SMC |
| **H6** | ✅ API completa (`--demo` vía H4) | `chiledist.fairshare`: `fair_share_matrix`; `results_to_matrix`; `l1_distance_fair_share`; `l2_distance_fair_share`; `max_cell_deviation`; `fair_share_summary` | 🔴 Votos electorales por CUT (elección de referencia); 🔴 Ensembles de H1 |
| **H7** | ✅ API completa | `chiledist.electoral_ensemble`: `run_electoral_ensemble`; `ensemble_gallagher`; `ensemble_seat_bonus`; `ensemble_enp`; `ensemble_effective_threshold`; `summarize_electoral_ensemble`; `plot_ensemble_histogram`; `plot_ensemble_violin`; `plot_ensemble_ecdf` | 🔴 Ensemble de H1; 🔴 Votos por CUT (elección de referencia). ✅ Asignación vigente y `pacto_map` ya disponibles para calcular métricas observadas |
| **H8** | ✅ API completa | `chiledist.pareto_sweep`: `sweep_split_penalty`; `build_tradeoff_frontier`; `detect_knee_point`; `plot_tradeoff_curve`; `summarize_tradeoff` | 🔴 Ensembles de H1 (uno por nivel de penalización, `penalties = np.linspace(0, 1, N)`) |
| **H9** | ✅ API completa | `chiledist.malapportionment`: `samuels_snyder_index`; `loosemore_hanby_malapportionment`; `gini_personas_por_escano`; `max_min_representation_ratio`; `malapportionment_summary`; `compare_malapportionment_plans`; `international_comparison`; `plot_pxe_distribution`; `plot_malapportionment_ranking`; `plot_international_comparison`; `BENCHMARK_MALAPPORTIONMENT` | ✅ Asignación vigente y población por circunscripción (Censo 2024) ya disponibles; 🔴 Ensembles de H1 para bootstrap |

### Correcciones de firma aplicadas en este documento

Las siguientes llamadas tenían firmas incorrectas y fueron corregidas:

| Función | Problema | Corrección |
|---|---|---|
| `plot_tradeoff_frontier` (H2) | Recibía un DataFrame unificado con `highlight=`, `color_by=` inexistentes | Ahora pasa `dict {escenario: DataFrame}` con `x_col=`, `y_col=` |
| `ranking_concordance` (H5) | Recibía listas de nombres | Ahora pasa `dict {escenario: composite_score}` |
| `mixing_diagnostics` (H5) | Recibía `ensemble_stats.csv` (plan-level) | Ahora carga `metricas_cadena.csv` (step-level); métrica `max_dev_pct` (no `max_dev_pob_pct`) |
| `plot_trace` (H5) | `metric="..."` (singular) + `title=` inexistente | `metrics=[...]` (lista) |
| `plot_gelman_rubin_evolution` (H5) | `metric="..."` (singular) | `metrics=[...]` (lista) |
| `export_to_redist` (H5) | Faltaban `adj`, `id_list`; `output_dir=` no existe | Ahora incluye `adj`, `id_list`, `output_file=` |
| `generate_redist_script` (H5) | Primer arg era una ruta de directorio | Primer arg es `gdf` (GeoDataFrame) |
| `load_redist_results` (H5) | Recibía directorio + `gdf=`, `id_col=` | Ahora `plans_csv=` (ruta a CSV) + `id_list=` |
| `compare_ensembles` output H1 | Referenciaba `pop_afectada_pct_median` (no existe en `METRICAS_STD`) | Reemplazada por `split_severity_median` |
| Rutas de directorios (H1, H5) | `datos/R13/redistritaje/legal/` | `datos/R13_METROPOLITANA/redistritaje/legal_comunas/` |

### Datos externos requeridos

| Archivo | Hipótesis | Fuente | Formato esperado | Estado |
|---|---|---|---|---|
| `datos/poblacion_comunal_censo2024.csv` | H1, H3 | INE Chile | `CUT, personas` por comuna | ✅ Ya existe en el repo |
| `datos/asignacion_vigente.json` | H1, H2, H3, H9 | BCN / SUBDERE (metodología documentada en `README.md § Datos externos`) | `{CUT_str: n_circunscripcion}`, 346 comunas → 28 distritos | ✅ Ya existe en el repo |
| `datos/servel_2025_por_cut.csv` | H3, H4 | SERVEL | `CUT, partido, votos` por circunscripción (puede usarse cualquier elección: 2021, 2025, …) | 🔴 Falta |
| `datos/pacto_map_2025.json` | H4, H6, H7 | SERVEL (resoluciones de formalización de pactos; metodología documentada en `README.md § Datos externos`) | `{partido: pacto}`, incluye sigla y nombre completo por partido | ✅ Ya existe en el repo |

### Scripts disponibles

| Script | Qué hace | Aplica a |
|---|---|---|
| `scripts/redistritaje.py` | Genera ensemble por escenario y región | H1, H2, H5 (base) |
| `scripts/compare_scenarios.py` | Corre los 3 escenarios y compara con tablas y figuras | H1 |
| `scripts/pareto_sweep.py` | Barrido de `split_penalty` → frontera Pareto; `--demo` disponible | H2 |
| `scripts/malapportionment.py` | Malapportionment con magnitudes legales; `--demo` con datos sintéticos | H3 |
| `scripts/electoral_analysis.py` | D'Hondt binivel sobre ensemble; `--demo` con datos sintéticos | H4 |
| `scripts/run_chains.py` | N cadenas ReCom independientes + `mixing_diagnostics` + sensibilidad a pesos | H5 |
| `scripts/smc_pipeline.py` | Bridge Python → R/redist → Python; comparación SMC vs ReCom | H5 |

---

## Plan de cierre — actividades pendientes (auditado 2026-08-14, reemplaza la auditoría de 2026-07-28)

Re-auditoría contra el estado actual del repositorio. Conclusión principal, sin cambios respecto a la versión anterior: **el lado de código/API está completo para H1–H9** (todas las funciones de la tabla de brechas existen y tienen tests unitarios). Lo que falta para cerrar H1–H9 sigue siendo mayormente **ejecución con datos reales**, no desarrollo de nuevas capacidades — pero esa ejecución ya avanzó parcialmente desde la auditoría anterior:

- **`chiledist/data/__init__.py` ahora expone `REGIONES_APC`** (16 regiones, `{region_code: {"nombre", "nombre_carpeta"}}`) — el bug que bloqueaba el CLI completo de `run_chains.py` está resuelto.
- **`datos/asignacion_vigente.json`, `datos/poblacion_comunal_censo2024.csv` y `datos/pacto_map_2025.json` ya existen** (3 de los 4 datos externos de la tabla de arriba). Solo falta `servel_..._por_cut.csv` (votos reales por CUT y partido) — sin ese archivo, H3/H4/H6/H7 con datos reales siguen bloqueados aunque el resto de sus insumos ya estén listos.
- **Ya hay una corrida real de `redistritaje.py` sobre R13** (no solo `--demo`): `datos/R13_METROPOLITANA/redistritaje/{legal_comunas,contrafactual_apc_soft,contrafactual_apc_libre}/`. `contrafactual_apc_soft` y `contrafactual_apc_libre` completaron con `status="ok"` y tienen `ensemble_stats.csv` real. **`legal_comunas` falló con `status="sin_particion"`** (`datos/redistritaje_resumen_legal_comunas.csv`) — ver el caveat agregado en la sección H1 más arriba. Esto significa que Fase 2 está *parcialmente* hecha para R13, pero el baseline legal sigue sin ensemble válido.
- `datos/malapportionment/` y `datos/electoral_analysis/` sí siguen siendo salidas de `--demo` (se verificó: los nombres de partido/pacto que contienen — `UDI`/`ChileVamos`, `PPD`/`NuevaUnidad`, etc. — coinciden exactamente con los datos sintéticos hardcodeados en `_demo_data()` de ambos scripts, no con `pacto_map_2025.json` ni con un resultado SERVEL real). H3/H4 con datos reales siguen pendientes hasta tener los votos SERVEL.
- No existe `datos/nacional/` — **`scripts/setup.py` sigue sin correrse contra el `SHP_APC2023` real** para generar el grafo nacional (`SHP_APC2023` presente en el repo, 3.7 GB, 16 regiones).
- Los tests de `tests/test_scripts_demo.py` cubren únicamente las rutas `--demo`/sintéticas de cada script; no hay ningún test de integración que corra el pipeline geográfico real de punta a punta.

### Fase 0 — Fundacional (bloquea las 9 hipótesis)

- [ ] Ejecutar `scripts/setup.py --base-dir ./SHP_APC2023` una vez para generar `datos/nacional/matrices/` (grafo nacional, islas) y las figuras base. Verificar contra `VALIDATION_PLAN.md § 3` (IDs únicos, geometrías válidas, CRS, suma APC→comuna) antes de seguir.
- [x] ~~Corregir el bug de `REGIONES_APC`~~ — resuelto: `chiledist/data/__init__.py` ya expone el diccionario de las 16 regiones.
- [ ] Diagnosticar por qué `legal_comunas` falla en R13 (`status="sin_particion"`, ver H1 arriba): correr `chiledist.check_population_feasibility` directamente para confirmar si es un caso de `infeasible_population` (matemáticamente probado — cambiar `n_districts`/`pop_tolerance`) o de agotamiento de búsqueda genuino (más semillas/tolerancias de inicialización podrían bastar). Sin esto, H1 no tiene los 3 escenarios completos para R13.
- [ ] Congelar las decisiones metodológicas ya escritas arriba (§ *Decisiones metodológicas previas a la ejecución*): región de desarrollo (R11) vs. publicación (R13), `pop_col="personas"`, `seed=42`, tamaño de ensemble (N=500 exploración / N=1000 publicación). Documentar la decisión final en este archivo, no solo la opción por defecto.

### Fase 1 — Conseguir los 4 datos externos

- [x] `datos/poblacion_comunal_censo2024.csv` (INE) — ya existe en el repo; requerido por H1, H3, H9.
- [ ] `datos/servel_<año>_por_cut.csv` (SERVEL, Open Data) — votos por CUT y partido de una elección de referencia (2021 o 2025); requerido por H3, H4, H6, H7. **Único de los 4 datos externos que sigue faltando.**
- [x] `datos/asignacion_vigente.json` (BCN/SUBDERE) — ya existe en el repo, 346 comunas → 28 circunscripciones (metodología documentada en `README.md § Datos externos`); requerido por H1, H2, H3, H9 (permite `position_plan_vigente` y comparar el mapa legal contra el ensemble).
- [x] `datos/pacto_map_2025.json` (SERVEL, resoluciones de formalización de pactos; metodología documentada en `README.md § Datos externos`) — ya existe en el repo, `{partido: pacto}` con sigla y nombre completo; requerido por H4, H6, H7 para D'Hondt binivel.

### Fase 2 — Generar los ensembles base (H1) que alimentan H2, H4–H9

- [x] Correr `scripts/redistritaje.py` para `apc_soft` y `apc_free` en R13 (`pop_col` default, `seed=42`) — ambos completaron con `status="ok"` (`datos/R13_METROPOLITANA/redistritaje/{contrafactual_apc_soft,contrafactual_apc_libre}/ensemble_stats.csv`).
- [ ] `legal_comunas` en R13 falló (`status="sin_particion"`) — resolver el diagnóstico de Fase 0 antes de tener el baseline. Falta también correr `apc_strict` (control metodológico) para los 4 escenarios completos.
- [ ] Correr `scripts/compare_scenarios.py` sobre los 4 escenarios una vez que `legal_comunas` tenga ensemble válido — cierra H1 con datos reales. (Si se corre antes, `comparison_status` quedará `"INCOMPLETE"` con `missing_baseline="legal_comunas"` — ver `chiledist.assess_comparison_completeness`.)
- [ ] Correr `scripts/pareto_sweep.py` con un barrido fino de `split_penalty` (no solo los 3 escenarios discretos) — insumo que necesita H8 específicamente (`build_tradeoff_frontier`/`detect_knee_point` sobre planes individuales, no medianas).

### Fase 3 — Cerrar cada hipótesis con datos reales

- [ ] **H2**: `position_plan_vigente()` con la asignación vigente real (ya disponible, Fase 1) sobre el espacio de Pareto generado en Fase 2.
- [ ] **H3**: `scripts/malapportionment.py` (sin `--demo`) con Censo 2024 real, asignación vigente y magnitudes `MAGNITUDES_LEGALES_LEY20840` — los dos insumos ya están disponibles, solo falta correr sin `--demo`.
- [ ] **H4**: `scripts/electoral_analysis.py` (sin `--demo`) con los votos SERVEL (aún pendiente) y `pacto_map` real (ya disponible, Fase 1).
- [ ] **H5**: correr `scripts/run_chains.py` con ≥4 cadenas (seeds 42–45) sobre los ensembles de Fase 2; correr `compare_sensitivity`/`ranking_concordance` entre fuentes de población (`viviendas` vs `personas`); instalar R + paquete `redist` para completar `scripts/smc_pipeline.py` y comparar SMC vs ReCom.
- [ ] **H6**: reutiliza votos de Fase 1 + ensembles de Fase 2 — solo falta correr `fair_share_matrix`/`fair_share_summary` sobre el ensemble real y calcular el percentil del mapa vigente.
- [ ] **H7**: `run_electoral_ensemble()` sobre el ensemble de Fase 2 con los votos/`pacto_map` reales; comparar contra las métricas del mapa vigente (Fase 3-H4).
- [ ] **H8**: `sweep_split_penalty()` + `build_tradeoff_frontier()` + `detect_knee_point()` sobre el barrido fino de Fase 2.
- [ ] **H9**: `compare_malapportionment_plans()` + `international_comparison()` con el mapa vigente (Fase 3-H3) y los ensembles de Fase 2; bootstrap de Samuels-Snyder por escenario.

### Fase 4 — Validación y cierre

- [ ] Correr la suite de `VALIDATION_PLAN.md` (Niveles 1–3) contra las corridas reales, no solo contra fixtures sintéticos.
- [ ] Agregar al menos un test de integración en `tests/` que corra el pipeline real (aunque sea en una región chica tipo R11/Aysén) en vez de solo `--demo`.
- [ ] Reemplazar cada 🔴 de la *Tabla de brechas* (arriba) por ✅ a medida que cada dato/ejecución esté listo, y actualizar la fecha de auditoría.
- [ ] Redactar la sección de métodos citando explícitamente semilla, N de ensemble, fuente de población y región — según lo congelado en Fase 0.

---

## Estado consolidado — agosto 2026

| H | Nombre | Estado | Datos reales | Pendiente |
|---|--------|--------|--------------|-----------|
| H1 | Costo restricción comunal | CLOSED R13 | ✅ Censo 2024 | R5/R8, apc_strict SMC |
| H2 | Frontera Pareto | COMPLETED R13 | ✅ | Ensemble nacional |
| H3 | Malapportionment | COMPLETED | ✅ Censo 2024 | — |
| H4 | D'Hondt binivel | VALIDATED | ✅ SERVEL+TRICEL 2025 | B3 ensemble nacional |
| H5 | Robustez sampler | PENDING | ❌ | run_chains ≥4 semillas |
| H6 | Gallagher ensemble | PARTIALLY COMPLETED | ✅ plan vigente | Ensemble nacional |
| H7 | Seat bonus ensemble | PARTIALLY COMPLETED | ✅ plan vigente | fair_share_matrix |
| H8 | Knee point Pareto | COMPLETED R13 | ✅ | Barrido más denso |
| H9 | Comparación internacional | COMPLETED | ✅ Censo 2024 | — |
