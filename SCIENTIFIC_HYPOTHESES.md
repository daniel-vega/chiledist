# Hipótesis Científicas — ChileDist

> **Versión:** 2.0  
> **Fecha:** 2026-06-21  
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
| Asignación plan vigente | BCN / SERVEL | Dict `{CUT: n_circunscripcion}` — construir manualmente |
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

# Control metodológico (APCs, comunas preservadas)
python scripts/redistritaje.py --base-dir . --regiones 13 \
    --scenario-file scenarios/apc_strict.yml
```

Salida: `datos/R13_*/redistritaje/<escenario>/ensemble_stats.csv`

#### Paso 2 — Cargar y comparar ensembles

```python
import chiledist as cd
import pandas as pd

# Rutas reales generadas por redistritaje.py:
#   datos/<REGION_NOMBRE>/redistritaje/<scenario.name>/ensemble_stats.csv
BASE = "datos/R13_METROPOLITANA/redistritaje"
ensembles = {
    "legal":    pd.read_csv(f"{BASE}/legal_comunas/ensemble_stats.csv"),
    "apc_soft": pd.read_csv(f"{BASE}/contrafactual_apc_soft/ensemble_stats.csv"),
    "apc_free": pd.read_csv(f"{BASE}/contrafactual_apc_libre/ensemble_stats.csv"),
}

# Columnas en ensemble_stats.csv (METRICAS_STD):
#   max_dev_pob_pct, pp_promedio, cut_edges, n_comunas_partidas,
#   split_severity, pop_afectada_pct  ← fracción de pob. en comunas divididas
tabla = cd.compare_ensembles(ensembles, baseline="legal_comunas")
print(tabla[["escenario",
             "max_dev_pob_pct_median",
             "n_comunas_partidas_median",
             "split_severity_median",
             "pop_afectada_pct_median",
             "delta_max_dev_pob_pct_median",
             "delta_n_comunas_partidas_median"]])
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
# Cargar asignación vigente (CUT → circunscripción)
assignment_vigente = {
    "13101": 10, "13102": 10, "13110": 12, ...  # BCN asignación 2015
}

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
# (requiere assignment_vigente: {CUT: n_circunscripcion}, construir desde BCN)
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
import chiledist as cd
import pandas as pd

# Población por circunscripción (Censo 2024, construir desde datos comunales)
pop_comunal = pd.read_csv("datos/poblacion_comunal_censo2024.csv",
                           index_col="CUT")["personas"]
asignacion_vigente = {cut: distrito for cut, distrito in ...}   # BCN

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
| Pactos electorales (elección de referencia) | SERVEL (metadata) | Dict `{partido: pacto}` — construir manualmente |
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

## Tabla resumen

| Hipótesis | Pregunta central | Escenarios | Función clave | Métrica de respuesta |
|---|---|---|---|---|
| **H1** | ¿Qué ocurre si Chile permite APCs como unidad mínima? | `legal` vs `apc_soft` vs `apc_free` | `plan_split_metrics()` | `pop_afectada_pct`, `delta_max_dev_pob_pct` |
| **H2** | ¿Es el mapa vigente Pareto-dominado? | Todos + barrido `split_penalty` | `pareto_frontier_nd()` | Posición del vigente en la frontera |
| **H3** | ¿Cuánto vale un voto en cada distrito? | Mapa vigente (magnitudes fijas) | `personas_por_escano()`, `peso_relativo_del_voto()` | `ratio_max_min_pxe`, `peso_relativo_max/min` |
| **H4** | ¿Cómo afecta D'Hondt binivel la proporcionalidad? | Cualquier plan + votos electorales (elección de referencia) | `plan_electoral_metrics(pacto_map=...)` | `gallagher`, `seat_bonus_max` |
| **H5** | ¿Son robustas las conclusiones a la metodología? | Pares de ensembles comparados | `compare_sensitivity()`, `ranking_concordance()` | `efecto` (negligible/grande), `tau` |

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
| **H1** | ✅ Ejecutable | CLI `redistritaje.py`; `compare_scenarios.py`; `compare_ensembles`; `plan_split_metrics`; `pop_afectada_pct` en `ensemble_stats.csv` | 🔴 Asignación vigente `{CUT: circunscripcion}` (BCN); 🔴 Censo 2024 comunal para `pop_col="personas"` |
| **H2** | ✅ Script disponible | `scripts/pareto_sweep.py`; `pareto_frontier_nd`; `rank_scenarios`; `ScoringConfig.from_weights` | 🔴 Asignación vigente para `position_plan_vigente` |
| **H3** | ✅ Script disponible (`--demo`) | `scripts/malapportionment.py`; `personas_por_escano`; `comparar_magnitudes`; `umbral_efectivo`; `plan_electoral_metrics(magnitudes_fijas=)` | 🔴 Censo 2024 por circunscripción; 🔴 Asignación vigente; 🔴 Votos electorales por CUT (elección de referencia) |
| **H4** | ✅ Script disponible (`--demo`) | `scripts/electoral_analysis.py`; `dhondt`; `dhondt_binivel`; `plan_electoral_metrics(pacto_map=)`; `national_shares`; `seat_bonus` | 🔴 Votos electorales por CUT y partido (elección de referencia); 🔴 `pacto_map` (elección de referencia); 🔴 Ensembles de H1 |
| **H5** | ✅ Scripts disponibles | `scripts/run_chains.py`; `scripts/smc_pipeline.py`; `mixing_diagnostics`; `compare_sensitivity`; `ranking_concordance` | 🔴 Ensembles de H1; R + paquete `redist` para SMC |

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

### Datos externos requeridos (no existen en el repo)

| Archivo | Hipótesis | Fuente | Formato esperado |
|---|---|---|---|
| `datos/poblacion_comunal_censo2024.csv` | H1, H3 | INE Chile | `CUT, personas` por comuna |
| `datos/servel_2025_por_cut.csv` | H3, H4 | SERVEL | `CUT, partido, votos` por circunscripción (puede usarse cualquier elección: 2021, 2025, …) |
| `datos/asignacion_vigente.json` | H1, H2, H3 | BCN / SERVEL | `{CUT_str: n_circunscripcion}` |
| `datos/pacto_map_2025.json` | H4 | SERVEL (metadata) | `{partido: pacto}` (adaptar a la elección de referencia) |

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
