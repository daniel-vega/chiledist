# Reporte de validación: D'Hondt binivel vs proclamaciones oficiales TRICEL 2025

Estado de `scripts/validar_tricel.py` — compara los escaños que
`chiledist.engines.allocation.dhondt.dhondt_binivel_cl()` calcula a
partir de los votos SERVEL contra los que el Tribunal Calificador de
Elecciones proclamó oficialmente para Diputados 2025 (16 nov. 2025),
sobre los 28 distritos reales.

**Estado actual: `EXACT_REPRODUCTION` — con `dhondt_binivel_cl()`, la
variante chilena con tope de candidatos disponibles por partido, NO
con `dhondt_binivel()` genérica (preservada sin cambios, sigue dando
`PARTIAL`, 25/28).** Este documento explica el camino completo hasta
acá, por qué existen dos funciones separadas, y la verificación de que
esto no altera H4 (96/96 vs SERVEL).

## 0. Estado canónico (fuente de verdad)

**96/96, 25/28 y 28/28 son tres cifras de tres validaciones distintas — nunca combinar en una sola, y siempre indicar con cuál función D'Hondt se obtuvo cada una.**

```json
{
  "SERVEL_INTERNAL_CONSISTENCY": {"result": "96/96", "status": "PASS", "source": "validar_dhondt.py vs SERVEL 2025", "dhondt_function": "run_electoral_plan_binivel() / dhondt_binivel() a nivel pacto — sin cambios"},
  "TRICEL_OFFICIAL_REPRODUCTION": {"result": "28/28 distritos", "status": "EXACT_REPRODUCTION", "detail": "155/155 escaños, 185/185 asignaciones de lista, 155/155 candidatos", "source": "validar_tricel.py vs TRICEL 2025 (--votes-source servel_final, --dhondt-variant cl, ambos default desde agosto 2026)", "dhondt_function": "dhondt_binivel_cl() — variante con tope de candidatos disponibles, NO dhondt_binivel() genérica", "generic_variant_result": {"result": "25/28 distritos", "status": "PARTIAL", "dhondt_function": "dhondt_binivel() sin tope, vía --dhondt-variant generic — preservada tal cual para comparación"}},
  "EXACT_REPRODUCTION": true
}
```

| Validación | Resultado | Estado | Función D'Hondt | Contra qué | Script |
|---|---|---|---|---|---|
| `SERVEL_INTERNAL_CONSISTENCY` | 96/96 combinaciones (distrito, pacto) | PASS | `dhondt_binivel()` (Nivel 1, sin cambios) | Resultado oficial **SERVEL** 2025 (no TRICEL) | `scripts/validar_dhondt.py` |
| `TRICEL_OFFICIAL_REPRODUCTION` | **28/28 distritos** | **EXACT_REPRODUCTION** | `dhondt_binivel_cl()` (tope de candidatos) | Proclamaciones oficiales **TRICEL** 2025 | `scripts/validar_tricel.py` (default) |
| `TRICEL_OFFICIAL_REPRODUCTION` (comparación) | 25/28 distritos | PARTIAL | `dhondt_binivel()` (sin tope, genérica) | Proclamaciones oficiales **TRICEL** 2025 | `scripts/validar_tricel.py --dhondt-variant generic` |

Cualquier documento que cite "validado 96/96" debe decir explícitamente **vs SERVEL 2025**, no vs TRICEL — ver §2-3 más abajo. Cualquier documento que cite "28/28" o "`EXACT_REPRODUCTION`" debe decir explícitamente que aplica a **`dhondt_binivel_cl()`** (la variante chilena con tope de candidatos), no a `dhondt_binivel()` genérica (que sigue en 25/28, `PARTIAL`, sin cambios — ver §9 para por qué son dos funciones separadas).

**Verificado, no solo declarado: H4 (`SERVEL_INTERNAL_CONSISTENCY`, 96/96) no cambia con `dhondt_binivel_cl()`** — ver §10 para la comparación empírica completa.

---

## 1. Output completo de la última corrida

Corrida con los defaults actuales: `--votes-source servel_final --dhondt-variant cl` (agosto 2026). El comando exacto está en §6.

```
======================================================================
  Validación TRICEL: D'Hondt binivel chiledist vs proclamaciones oficiales
======================================================================
  Cargando candidatos SERVEL desde datos/servel_2025_candidatos.csv ...
  1378 candidatos, 28 distritos.
  Importando proclamaciones TRICEL desde /home/dvega/Distritaje/DATA/TRICEL_2025 ...
  Cargando 'comunal' (16 archivo(s))...
  → 345 registros.
  ⚠ comunas sin CUT mapeado: ['ANTARTICA']
  28 distritos leídos, 155 candidatos cruzados con SERVEL, 0 sin cruce.
  Importando escrutinio final SERVEL (v2) desde /home/dvega/Distritaje/DATA/SERVEL_2025 ...
    workbook: /home/dvega/Distritaje/DATA/SERVEL_2025/2025_11_Diputados_Datos_Eleccion/2025_11_Diputados_Datos_Eleccion_v2.xlsx
  1096 registros (distrito, candidato) de votación TRICEL.
  Importando conteo de candidatos por partido desde /home/dvega/Distritaje/DATA/TRICEL_2025 ...
  488 filas (distrito, partido, n_candidatos).

Election: Diputados 2025
Districts validated: 28/28
Seats validated: 155/155
List allocations: 185/185
Candidate proclamations: 155/155
Ties requiring legal resolution: 0
Votes with SERVEL fallback: 296/1096
Source hashes:
  SERVEL: 1c3fd5dab12d8716c6854ba3da14a7d3bcc13038c18b388fae2c33239226d2f0
  TRICEL: 359c13cee96490b5ed6dba559694d7f27d7ed6083395af24bf8ced555ffffc91
Status: EXACT_REPRODUCTION
```

**28/28. Cero discrepancias.** `Votes with SERVEL fallback` (296/1096) es el mismo que con `--votes-source servel_final` solo (§ historial previo) — el tope de candidatos no cambia qué candidatos matchean por nombre contra `votes_tricel`, solo cambia cómo se reparten los escaños intra-pacto entre partidos una vez calculados los votos.

### 1.1 Comparación: `--dhondt-variant generic` (para contraste, no el default)

```
Districts validated: 25/28
Seats validated: 149/155
Candidate proclamations: 149/155
Status: PARTIAL
Distritos no validados (3): D3 (2 discrepancias), D5 (3 discrepancias), D19 (1 discrepancia)
```

Idéntico al resultado documentado en la revisión anterior de este reporte (antes de que existiera `dhondt_binivel_cl()`) — confirma que `dhondt_binivel()` genérica no fue tocada.

---

## 2. Historial de progreso

| Etapa | Districts validated | Ties | Causa de la mejora |
|---|---|---|---|
| Baseline (solo votos SERVEL preliminares, sin `votes_tricel`) | 10/28 | 0 | — punto de partida, tras corregir el `KeyError` de `_read_electos_sheet()` (ver §4) |
| `votes_tricel` recién conectado a `validate_election()` | **0/28** | **123** | Candidatos sin match TRICEL↔SERVEL por nombre quedaban en `votes=0` → empates espurios (0==0) dentro del mismo partido |
| Fallback a votos SERVEL agregado (`_apply_votes_source`) | 0/28 (sin cambio) | 123 (sin cambio) | El fallback en sí funcionaba correctamente (verificado en aislado), pero operaba sobre datos ya corruptos aguas arriba — no se movió nada |
| `_cargar_candidates_servel()` agrega por candidato | **20/28** | **0** | Causa real de los "empates": `servel_2025_candidatos.csv` trae una fila por (candidato × CUT) — hasta 26 filas por candidato — y se pasaban sin sumar; el ranking intra-partido comparaba fragmentos de votos por comuna, no el total real |
| `candidate_id % 100` → `% 1000` en `import_proclamations()` | **24/28** | 0 | 12 candidatos electos con `num_tricel` de 3 dígitos (≥100, distritos con 100+ candidatos registrados) nunca cruzaban con SERVEL — `candidates_matched` 143→155, `candidates_unmatched` 12→0 |
| `import_final_scrutiny()` (SERVEL "v2"/escrutinio final) como `--votes-source` default, en vez de `import_votes()` (TRICEL mesa a mesa) | **25/28** | 0 | Resuelve Distrito 8 por completo (12→0 discrepancias). La causa NO era cobertura SERVEL insuficiente como se documentaba antes (ver §3) — era un bug de `import_votes()` que tomaba una fila de totales fantasma para Distrito 8, dejando `votes_final=0` para sus 52 candidatos |
| `dhondt_binivel_cl()` (tope de candidatos disponibles por partido, Nivel 2) como `--dhondt-variant` default, en vez de `dhondt_binivel()` sin tope | **28/28 — `EXACT_REPRODUCTION`** | 0 | Resuelve Distrito 3, 5 y 19 por completo (6→0 discrepancias). Causa raíz: un partido con un solo candidato inscrito "ganaba" escaños que no tenía a quién asignar. Ver §3, §9 |

La lección estructural: **la mejora de 0/28 a 20/28 no vino de tocar
la lógica de votos TRICEL ni el fallback** (ambos ya estaban correctos
en ese punto) — vino de un bug completamente distinto y más simple
(agregación de filas) que estaba corrompiendo el input antes de que
`validate_election()` viera los datos. Confirmar cada fix con un test
aislado (no solo con la corrida completa) fue lo que permitió
distinguir "el fallback funciona" de "el resultado global mejora".

---

## 3. Causas documentadas — actualizado agosto 2026 (reemplaza el diagnóstico anterior)

**El diagnóstico anterior de esta sección era incorrecto y fue reemplazado tras verificación directa contra los datos.** La cifra "38.8% de cobertura SERVEL" para Distrito 8 (777.192 de 2.002.540) estaba comparada contra un total TRICEL **erróneo**: la hoja MESA A MESA de `TRICEL_2025/Distrito-08.xlsx` tiene dos filas que matchean el criterio de detección de "fila de totales" (`_MESA_GEO_COLS` en NaN) — la correcta (`Nulos=147.826, Blancos=74.939, Total votos=1.001.270`) y una fantasma (`Nulos/Blancos=NaN, Total votos=2.002.540` — exactamente el doble, con las 52 columnas de candidato en cero). `import_votes()` toma `.iloc[-1]` (la última fila que matchea), que para Distrito 8 es la fantasma — ver bug documentado en §4. El total real de votos válidos en Distrito 8 es **778.505** (verificado exacto contra `TRICEL_2025/Distrito-08.xlsx`, hoja CANDIDATOS, columna TOTALES) — el archivo SERVEL preliminar ya capturaba el **99.83%** de eso (777.192), no 38.8%.

Con el total correcto, se recalculó la cobertura de `servel_2025_candidatos.csv` contra los totales certificados de TRICEL (hoja CANDIDATOS) en los 28 distritos: **todos entre 85.8% y 131.8%** (varios sobre 100%, ninguno cerca de 38.8% o incluso 77-78%) — el patrón "cobertura baja explica las discrepancias" nunca fue el mecanismo real, ni siquiera para los otros 3 distritos que sí quedaron sin resolver.

### Distrito 8 — resuelto

Causa real: el bug de fila-de-totales-fantasma de `import_votes()` (arriba) dejaba `votes_final=0` para los 52 candidatos de Distrito 8 cuando se usaba TRICEL mesa a mesa como `votes_tricel`. Al cambiar a `import_final_scrutiny()` (SERVEL "v2"/escrutinio final, ver §4) — que no depende de esa detección de fila y da 100.0% de cobertura verificada — Distrito 8 pasa de 12 discrepancias a 0.

### Distrito 3, 5, 19 — resuelto: causa raíz era la falta de tope de candidatos en `dhondt_binivel()`

**No es un problema de datos.** Se verificó que los 6 candidatos con discrepancia tienen, con la fuente SERVEL v2, el voto **exacto** que certifica TRICEL (`votes_tricel` de la hoja CANDIDATOS) — coincidencia perfecta en los 6 casos (ej. Jaime Araya Guerrero: 13.687 en ambas fuentes). El problema está en el algoritmo de reparto intra-pacto (Nivel 2 de `dhondt_binivel()`).

`dhondt_binivel()` documenta explícitamente esta limitación en su propio docstring: *"El sistema real asigna los escaños del pacto a sus candidatos más votados individualmente (no a partidos)... el D'Hondt interno entre partidos es la aproximación estándar"* — pero a esa aproximación le falta un tope: **un partido no puede ganar más escaños que candidatos registró**, y la implementación actual no lo aplica. Ejemplo concreto (Distrito 3, pacto UNIDAD POR CHILE, 3 escaños): el Partido Liberal, con un solo candidato inscrito (Sebastián Videla Castillo, 74.910 votos), domina el D'Hondt de partidos y "gana" los 3 escaños del pacto en el cálculo actual — pero en la realidad solo puede ocupar 1 (no hay una segunda persona en su lista para ocupar los otros 2), y esos 2 escaños pasan a los siguientes partidos con candidato disponible: PPD (Jaime Araya, 13.687 votos) y Radical (Marcela Hernando, 11.973 votos) — exactamente los 2 candidatos que TRICEL proclama y que `dhondt_binivel()` no calcula.

**Verificación exhaustiva**: se reprodujo un D'Hondt con tope de candidatos disponibles (`min(D'Hondt, n_candidatos_del_partido)`, redistribuyendo el resto por el mismo orden de cociente) contra los **7 pactos** con escaños en disputa entre partidos de Distrito 3, 5 y 19 (leídos directamente de la hoja DETERMINACION de cada `TRICEL_2025/Distrito-XX.xlsx`, el cálculo D'Hondt oficial de TRICEL, no usada hasta ahora por este código). **Los 7 pactos coinciden exactamente** con el resultado oficial:

| Distrito | Pacto | Escaños | Predicho (D'Hondt con tope) | TRICEL real | Coincide |
|---|---|---|---|---|---|
| 3 | UNIDAD POR CHILE | 3 | Liberal=1, PPD=1, PC=0, Radical=1, PDC=0, FA=0 | idéntico | ✅ |
| 5 | UNIDAD POR CHILE | 4 | FA=1, PS=1, PC=2, PPD=0, Radical=0, PDC=0 | idéntico | ✅ |
| 5 | Partido de la Gente | 1 | PdG=1 | idéntico | ✅ |
| 5 | Chile Grande y Unido | 1 | UDI=1 | idéntico | ✅ |
| 5 | Cambio por Chile | 1 | Nacional Libertario=1 | idéntico | ✅ |
| 19 | UNIDAD POR CHILE | 2 | PDC=1, PS=1 | idéntico | ✅ |
| 19 | Chile Grande y Unido | 2 | UDI=1, RN=1 | idéntico | ✅ |
| 19 | Cambio por Chile | 1 | Social Cristiano=1 | idéntico | ✅ |

Esta era la causa raíz completa y verificada — confirmada, no solo una hipótesis: implementada como `dhondt_binivel_cl()` (función separada, `dhondt_binivel()` preservada sin cambios — ver §9), corriendo `scripts/validar_tricel.py` con el tope de candidatos por partido, **los 3 distritos pasan a 0 discrepancias — 28/28, `EXACT_REPRODUCTION`** (ver §1).

### Otros hallazgos sin resolver, documentados honestamente

- **`servel_2025_candidatos.csv` produce 1.378 "candidatos" agrupados, no los 1.096 reales** (mismo total que el roster completo de TRICEL). No se diagnosticó la causa exacta en esta sesión — es un problema de calidad de datos residual en el archivo o en `_cargar_candidates_servel()`, distinto y no resuelto por el fix del bug #4 (agregación por CUT) ya documentado abajo. No se investigó más a fondo por alcance/tiempo; queda como deuda técnica.

---

## 4. Bugs corregidos durante el proceso

| # | Bug | Commit | Alcance |
|---|---|---|---|
| 1 | `asignacion_vigente.json`: 8 CUT de la Región Metropolitana mal asignados a distrito | `b72aff0` | **Anterior a esta sesión** — corregido por el usuario antes de que empezara el trabajo de TRICEL/validation documentado acá. Se menciona por completitud del historial, no lo hice yo en las tareas de esta sesión. |
| 2 | `_read_electos_sheet()`: rename por nombre exacto solo capturaba la etiqueta `"TOTALES"` de la columna de votos en la hoja ELECTOS; 17 de 28 distritos reales usan `"VOTOS"` o `"VOCALES"` (Distrito-10, error tipográfico del archivo oficial) → `KeyError` | `7c66ce4` | `chiledist/domain/data/tricel/__init__.py` |
| 3 | `_list_tricel_files()`/detección de fila de totales en MESA A MESA: exigía NaN en 15 columnas de identificación de mesa; en Distrito-15/16 las columnas de mesa (`Tipo de mesa`/`Mesa`/`Fusionadas`/`Local`/`Dirección del local`) no están en NaN en esa fila → 0 filas matcheadas → `ValueError` | `3436f98` | `chiledist/domain/data/tricel/__init__.py` — acotado a las columnas geográficas (`_MESA_GEO_COLS`), más `_safe_int()` para Nulos/Blancos NaN en Distrito-08 |
| 4 | `_cargar_candidates_servel()` (script): no agregaba las filas por (candidato × CUT) del CSV — 13,410 filas sin sumar en vez de 1,096 candidatos únicos, corrompiendo el ranking intra-partido | `7b7e61c` | `scripts/validar_tricel.py` |
| 5 | `import_proclamations()`: cruce `num_tricel == candidate_id % 100` fallaba en silencio para `num_tricel` de 3 dígitos (candidatos numerados ≥100 dentro de su distrito) — el sufijo real de `candidate_id` es de 3 dígitos, no 2 | `1aea69e` | `chiledist/domain/data/tricel/__init__.py` |
| 6 | `import_votes()`: en Distrito 8, dos filas de MESA A MESA matchean el criterio de "fila de totales" (NaN en `_MESA_GEO_COLS`) — la real (`Total votos=1.001.270`, Nulos/Blancos poblados) y una fantasma (`Total votos=2.002.540`, exactamente el doble, Nulos/Blancos=NaN, las 52 columnas de candidato en cero). `.iloc[-1]` toma la fantasma, dejando `votes_final=0` para todo Distrito 8 | **no corregido** — documentado, bypaseado por el nuevo default `--votes-source servel_final` (ver fila nueva en §2) | `chiledist/domain/data/tricel/__init__.py::import_votes()` — único distrito de 28 con esta anomalía (verificado) |

**Hallazgo — no es un bug de código, pero causaba diagnósticos erróneos**: la cifra "38.8% de cobertura SERVEL" para Distrito 8 documentada en versiones anteriores de este reporte estaba calculada contra el total fantasma del bug #6 (2.002.540), no contra el total real (1.001.270). Con el total correcto, la cobertura real de `servel_2025_candidatos.csv` en Distrito 8 era 99.83%, no 38.8% — ver §3 para el detalle completo y por qué esto invalida el diagnóstico de "cobertura SERVEL insuficiente" para los 4 distritos que documentaban versiones anteriores de este archivo.

**Hallazgo — causa raíz real de Distrito 3/5/19, resuelto vía función separada**: `chiledist.engines.allocation.dhondt.dhondt_binivel()` no aplica un tope de candidatos disponibles por partido en el reparto intra-pacto (Nivel 2) — ver §3 para la verificación completa (7/7 pactos reproducidos exactamente) y §9 para `dhondt_binivel_cl()`, la función nueva que lo corrige sin modificar `dhondt_binivel()`.

Además, `_apply_votes_source()` (`chiledist/validation/__init__.py`,
commit `939ef9e`) agregó un fallback a votos SERVEL para candidatos sin
match TRICEL — necesario y correcto, pero **no** fue la causa de
ninguna de las mejoras de cobertura documentadas en §2 (ver esa
sección: el salto real vino del bug #4).

---

## 5. Camino hacia `EXACT_REPRODUCTION` — completado

**Distrito 8** se cerró usando una fuente SERVEL de escrutinio final ("v2", `import_final_scrutiny()`) en vez de TRICEL mesa a mesa — evita el bug #6 y da cobertura ~100% verificada en los 28 distritos (§2, §3).

**Distrito 3, 5 y 19** se cerraron implementando `dhondt_binivel_cl()` (§9): D'Hondt con tope de candidatos disponibles por partido en el Nivel 2, en vez de D'Hondt directo entre partidos — un partido no puede acumular más escaños que candidatos tiene disponibles; el excedente se redistribuye a los siguientes cocientes más altos entre partidos con candidato disponible. Verificado exacto contra los 7 pactos en disputa de D3/D5/D19 (§3) y contra la corrida completa (§1): **28/28**.

Con `--votes-source servel_final --dhondt-variant cl` (ambos default): **`EXACT_REPRODUCTION`**. Con cualquiera de los dos en su valor anterior (`tricel` o `generic`): `PARTIAL` — ver §1 para ambas corridas de comparación.

---

## 6. Comando de reproducción

```bash
export CHILEDIST_DATA_DIR=/home/dvega/Distritaje/DATA

python scripts/validar_tricel.py \
    --data-dir "$CHILEDIST_DATA_DIR" \
    --servel-candidates datos/servel_2025_candidatos.csv \
    --pacto-map datos/pacto_map_2025.json \
    --assignment datos/asignacion_vigente.json
    # --base-dir por defecto: ./SHP_APC2023 (correr desde la raíz de chiledist/)
    # --votes-source por defecto: servel_final (agosto 2026) — pasar
    #   --votes-source tricel para reproducir el comportamiento previo a
    #   ese cambio (24/28, ver bug #6 arriba)
    # --dhondt-variant por defecto: cl (agosto 2026) — pasar
    #   --dhondt-variant generic para reproducir dhondt_binivel() sin tope
    #   (25/28, ver §1.1 y §9)
    # Con ambos defaults: 28/28, EXACT_REPRODUCTION.
```

Requiere (no distribuido en el repo, ver `.env.example`):
`$CHILEDIST_DATA_DIR/SERVEL_2025/PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx`,
`$CHILEDIST_DATA_DIR/SERVEL_2025/2025_11_Diputados_Datos_Eleccion/*_v2.xlsx`
(escrutinio final, usado por el default `--votes-source servel_final`),
`$CHILEDIST_DATA_DIR/TRICEL_2025/Distrito-*.xlsx`, y `SHP_APC2023_R*/`
en el directorio pasado a `--base-dir`.

---

## 7. SHA256 de las fuentes usadas (última corrida)

| Fuente | SHA256 |
|---|---|
| SERVEL candidatos (`datos/servel_2025_candidatos.csv`) | `1c3fd5dab12d8716c6854ba3da14a7d3bcc13038c18b388fae2c33239226d2f0` |
| SERVEL escrutinio final v2 (`2025_11_Diputados_Datos_Eleccion_v2.xlsx`) | `13aacd1a387e9c559e49aec720637d9e01120f3a3251b14b15a5c1d912738043` |
| TRICEL (hash combinado de los 28 `Distrito-XX.xlsx`, ver `_combined_hash()` en `scripts/validar_tricel.py`) | `359c13cee96490b5ed6dba559694d7f27d7ed6083395af24bf8ced555ffffc91` |

---

## 8. Nota sobre el archivo mesa a mesa SERVEL (`.txt`, no usado)

`SERVEL_2025/2025_11_Diputados_Datos_Eleccion/2025_11_Diputados_Votacion_v2.txt`
(1.908.695 líneas, formato mesa a mesa) fue verificado como **el mismo
escrutinio** que el `.xlsx` usado por `import_final_scrutiny()` — totales
nacionales y por distrito idénticos byte a byte (13.403.182 votos, mismo
desglose por los 28 distritos) — no es un corte temporal distinto. Se usó
el `.xlsx` (agregado por comuna, ~14.000 filas) por ser 27× más liviano
sin perder información a nivel de candidato/distrito; el `.txt` solo
aportaría granularidad de mesa, que ningún loader actual de chiledist
consume a ese nivel.

---

## 9. `dhondt_binivel()` vs `dhondt_binivel_cl()` — por qué son dos funciones separadas

`chiledist.engines.allocation.dhondt.dhondt_binivel()` **no fue modificada**. La corrección de §3/§5 vive en una función nueva, `dhondt_binivel_cl()`, más el primitivo genérico `dhondt_con_tope()` (D'Hondt con tope de escaños por partido, reutilizable fuera del caso binivel). Motivos:

1. **`dhondt_binivel()` opera solo sobre votos agregados por partido, sin candidatos** — es la abstracción correcta para escenarios de redistritaje sintético (ensembles de este proyecto) donde no existe una lista de candidatos real que consultar, y para comparación metodológica internacional. `dhondt_binivel_cl()` requiere y usa `candidatos_por_partido` — solo tiene sentido cuando ese dato existe, típicamente al validar contra una elección real ya corrida.
2. **Ningún test ni resultado publicado que dependa de `dhondt_binivel()` cambia** — verificado, no asumido: la suite completa (631 tests, antes 603 + 28 nuevos de `tests/test_dhondt_binivel_cl.py`) pasa sin modificar ningún test existente, y H4/`SERVEL_INTERNAL_CONSISTENCY` (96/96) da el mismo resultado con ambas funciones (ver §10).

### ¿Es esto una particularidad de la Ley 18.700, o del D'Hondt binivel en general?

Investigado con evidencia, no asumido. Se intentó obtener el texto literal del art. 121 de la Ley 18.700 (DFL 2, 2017, texto refundido) vía búsqueda web — **sin éxito concluyente**: la Biblioteca del Congreso Nacional (bcn.cl) no renderiza contenido para fetch automatizado en este entorno (páginas dinámicas basadas en JavaScript), y las copias de la ley disponibles por otras vías (Georgetown PDBA, Tribunal Electoral, te.gob.mx) resultaron ser versiones **anteriores a la reforma de 2015** que introdujo D'Hondt (el sistema binominal previo no lo usaba), o PDFs truncados antes de llegar al artículo 121.

La evidencia disponible más fuerte no es un texto legal citado, sino el **cálculo D'Hondt oficial de TRICEL** (hoja DETERMINACION de cada `TRICEL_2025/Distrito-XX.xlsx`, el cálculo del organismo mismo aplicado a la elección real, no una interpretación de terceros) — reproducido exactamente (7/7 pactos, §3). Servel.cl (`servel.cl/metodo-dhondt/`) confirma que "resultan electas las candidaturas con mayores votaciones personales dentro de esa lista, hasta completar los escaños obtenidos", consistente con que los escaños se agotan cuando se agotan los candidatos.

**Conclusión honesta**: no se encontró evidencia de que esto sea una regla exclusiva de Chile. El razonamiento general la respalda: un partido no puede elegir más personas que las que postuló — esto es una necesidad lógica de cualquier sistema D'Hondt binivel aplicado sobre listas de candidatos reales (Países Bajos, Bélgica, España, etc. tienen el mismo problema de "lista agotada" en sus propios sistemas proporcionales), no una peculiaridad chilena. Simplemente se manifiesta pocas veces porque la mayoría de los partidos postulan más candidatos que los escaños que razonablemente podrían ganar — en Chile, con pactos de 5-6 partidos y distritos de 2-8 escaños, es más frecuente que un partido registre un único candidato. `dhondt_binivel()` nunca estuvo "mal" como método abstracto de votos-por-partido; está incompleto solo cuando se le pide reproducir una elección real con listas de candidatos conocidas y limitadas.

### Nuevas funciones y su ubicación

| Función | Ubicación | Qué hace |
|---|---|---|
| `dhondt_con_tope()` | `chiledist.engines.allocation.dhondt` | D'Hondt genérico con tope de escaños por partido — primitivo reutilizable |
| `dhondt_binivel_cl()` | `chiledist.engines.allocation.dhondt` | D'Hondt binivel con tope de candidatos por partido en Nivel 2 |
| `chiledist.domain.data.tricel.import_candidate_counts()` | `chiledist.domain.data.tricel` | Fuente de `candidatos_por_partido` — cuenta candidatos por partido y distrito desde la hoja CANDIDATOS de TRICEL. **No** derivar este conteo de `servel_2025_candidatos.csv`/`import_candidates()` (SERVEL): esa fuente sobrecuenta candidatos (1.378 filas vs 1.096 reales, §3) y puede anular el tope en silencio para un partido específico. |

`run_electoral_plan_binivel()` y `validate_election()` ganaron un parámetro opcional (`candidatos_por_partido`) para elegir la variante — explícito, default `None` preserva el comportamiento anterior exactamente (ver diff de código). `scripts/validar_tricel.py` expone `--dhondt-variant {cl,generic}` (default `cl`, agosto 2026).

---

## 10. Verificación de regresión: ¿H4 cambia con `dhondt_binivel_cl()`?

**No.** Verificado empíricamente sobre los mismos datos SERVEL 2025 reales que usa H4 (`servel_2025_candidatos.csv`, `--modo candidatos`), comparando `run_electoral_plan_binivel()` con y sin `candidatos_por_partido` (conteo real desde `import_candidate_counts()`):

**Nivel pacto** (lo que mide `scripts/validar_dhondt.py`, `SERVEL_INTERNAL_CONSISTENCY`, 96/96): **96/96 filas (distrito, pacto), 0 diferencias** entre `dhondt_binivel()` y `dhondt_binivel_cl()`.

**Nivel partido** (más granular, dentro de cada pacto — lo que `validar_dhondt.py` no mide): **8 de 438 filas (distrito, partido) difieren**, y caen exactamente en Distrito 3, 5 y 19 — los mismos 3 distritos identificados en §3, ninguno en los otros 25:

| Distrito | Partido | Δ escaños (generic − cl) |
|---|---|---|
| 3 | Partido Liberal de Chile | +2 |
| 3 | Partido por la Democracia | −1 |
| 3 | Partido Radical de Chile | −1 |
| 5 | Frente Amplio | −1 |
| 5 | Partido Comunista de Chile | −2 |
| 5 | Partido Socialista de Chile | +3 |
| 19 | Partido Democrata Cristiano | +1 |
| 19 | Partido Socialista de Chile | −1 |

Total de escaños nacional: 155 en ambos casos.

**Por qué esto es matemáticamente esperado, no una coincidencia**: el Nivel 1 (D'Hondt entre pactos, que determina cuántos escaños gana cada pacto — lo único que `validar_dhondt.py`/H4 compara) es **idéntico** entre `dhondt_binivel()` y `dhondt_binivel_cl()`; el tope de candidatos solo actúa en el Nivel 2 (reparto entre partidos dentro de un pacto ya ganador), que `validar_dhondt.py` nunca desagrega. Consistente con que el problema afectó exactamente 3 de 28 distritos: son los únicos donde, dentro de un pacto con escaños en disputa, el partido con más votos tenía menos candidatos inscritos que escaños le habría dado el D'Hondt sin tope.

**Conclusión**: `SERVEL_INTERNAL_CONSISTENCY` (96/96, H4) no necesita re-evaluarse — el resultado agregado por pacto que reporta es idéntico con ambas funciones. Ningún resultado de H4 documentado en `SCIENTIFIC_HYPOTHESES.md` cambia.

### `run_electoral_ensemble()` — no se migró, y no debería por defecto

`chiledist.inference.electoral_ensemble.core.run_electoral_ensemble()` aplica D'Hondt sobre **planes de redistritaje sintéticos** (asignaciones unidad→distrito generadas por ReCom) — distritos hipotéticos que nunca existieron en una boleta real. No hay "candidatos inscritos" que consultar para un distrito que el ensemble inventó, así que `candidatos_por_partido` no es aplicable conceptualmente ahí, no solo por falta de dato disponible. **No se propone migrar el default de `run_electoral_ensemble()` a `dhondt_binivel_cl()`** — seguiría requiriendo `dhondt_binivel()` (votos-only) para tener sentido. Si en el futuro se necesitara modelar candidatos dentro de un ensemble, sería un diseño nuevo (ej. muestrear cuántos candidatos por partido postularían bajo cada plan hipotético), no una migración directa de parámetro.
