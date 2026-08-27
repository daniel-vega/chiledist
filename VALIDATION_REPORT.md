# Reporte de validación: D'Hondt binivel vs proclamaciones oficiales TRICEL 2025

Estado de `scripts/validar_tricel.py` — compara los escaños que
`chiledist.engines.allocation.dhondt.dhondt_binivel()` calcula a partir
de los votos SERVEL contra los que el Tribunal Calificador de
Elecciones proclamó oficialmente para Diputados 2025 (16 nov. 2025),
sobre los 28 distritos reales.

**Estado actual: `PARTIAL`, no `EXACT_REPRODUCTION`.** Este documento
explica por qué, qué se corrigió para llegar hasta acá, y qué falta.

## 0. Estado canónico (fuente de verdad)

**96/96 y 25/28 son dos validaciones distintas contra fuentes distintas — nunca combinar en una sola cifra.**

```json
{
  "SERVEL_INTERNAL_CONSISTENCY": {"result": "96/96", "status": "PASS", "source": "validar_dhondt.py vs SERVEL 2025"},
  "TRICEL_OFFICIAL_REPRODUCTION": {"result": "25/28 distritos", "status": "PARTIAL", "detail": "149/155 escaños, 185/185 asignaciones de lista, 149/155 candidatos", "source": "validar_tricel.py vs TRICEL 2025 (--votes-source servel_final, default desde agosto 2026)", "unresolved": ["D3", "D5", "D19"], "unresolved_root_cause": "dhondt_binivel() no aplica tope de candidatos por partido en el reparto intra-pacto — ver §3"},
  "EXACT_REPRODUCTION": false
}
```

| Validación | Resultado | Estado | Contra qué | Script |
|---|---|---|---|---|
| `SERVEL_INTERNAL_CONSISTENCY` | 96/96 combinaciones (distrito, pacto) | PASS | Resultado oficial **SERVEL** 2025 (no TRICEL) | `scripts/validar_dhondt.py` |
| `TRICEL_OFFICIAL_REPRODUCTION` | 25/28 distritos (149/155 escaños, 185/185 asignaciones de lista, 149/155 candidatos) | PARTIAL | Proclamaciones oficiales **TRICEL** 2025 | `scripts/validar_tricel.py` |

Cualquier documento que cite "validado 96/96" debe decir explícitamente **vs SERVEL 2025**, no vs TRICEL — ver §2-3 más abajo para el detalle de por qué estas dos cifras no son intercambiables.

**Mientras el estado no sea `EXACT_REPRODUCTION`, ningún documento del repositorio debe describir esto como "reproducción independiente exacta de la elección 2025" ni equivalente** — es una reproducción parcial (25/28), con causa raíz identificada y verificada para los 3 distritos restantes (ver §3), pero no corregida todavía.

---

## 1. Output completo de la última corrida

Corrida con el nuevo default `--votes-source servel_final` (agosto 2026, ver §2 fila nueva y §4). El comando exacto está en §6.

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

Election: Diputados 2025
Districts validated: 25/28
Seats validated: 149/155
List allocations: 185/185
Candidate proclamations: 149/155
Ties requiring legal resolution: 0
Votes with SERVEL fallback: 296/1096
Source hashes:
  SERVEL: 1c3fd5dab12d8716c6854ba3da14a7d3bcc13038c18b388fae2c33239226d2f0
  TRICEL: 359c13cee96490b5ed6dba559694d7f27d7ed6083395af24bf8ced555ffffc91
Status: PARTIAL

Distritos no validados (3):
  D3: 2 discrepancias (candidate_mismatch)
    Proclamados pero no calculados: JAIME ARAYA GUERRERO, MARCELA HERNANDO PEREZ
  D5: 3 discrepancias (candidate_mismatch)
    Proclamados pero no calculados: CAROLINA TELLO ROJAS, NATHALIE CASTILLO ROJAS, BERNARDO SALINAS MAYA
  D19: 1 discrepancias (candidate_mismatch)
    Proclamados pero no calculados: FRANCISCO CRISOSTOMO LLANOS

Para investigar discrepancias: usar --verbose para ver detalle completo
```

`Votes with SERVEL fallback` subió levemente (283→296 de 1096) respecto a la corrida con `--votes-source tricel` — el cruce por nombre normalizado contra el archivo SERVEL v2 no matchea el 100% de `candidates_servel` (78.5%, ver §3), así que más candidatos quedan con su voto preliminar original. Pese a eso, el resultado a nivel distrito mejoró (24→25) porque el candidato con match SÍ tiene ahora el voto exacto de TRICEL, incluidos los que antes fallaban en Distrito 8 por el bug documentado en §3/§4.

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

### Distrito 3, 5, 19 — causa raíz real: `dhondt_binivel()` no tiene tope de candidatos por partido

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

Esta es la causa raíz completa y verificada — no una hipótesis. El fix (candidate-count cap en el Nivel 2 de `dhondt_binivel()`) no está implementado en esta sesión: es un cambio a la función D'Hondt central usada en todo el pipeline (H4, `electoral_analysis.py`, `run_electoral_ensemble`, etc.), no específico de esta validación, y requiere pasar el número de candidatos disponibles por partido — un dato que hoy no todos los llamadores de `dhondt_binivel()` tienen disponible. Ver §5.

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

**Hallazgo — causa raíz real de Distrito 3/5/19, no corregido**: `chiledist.engines.allocation.dhondt.dhondt_binivel()` no aplica un tope de candidatos disponibles por partido en el reparto intra-pacto (Nivel 2) — ver §3 para la verificación completa (7/7 pactos reproducidos exactamente con el modelo corregido) y §5 para la vía de cierre.

Además, `_apply_votes_source()` (`chiledist/validation/__init__.py`,
commit `939ef9e`) agregó un fallback a votos SERVEL para candidatos sin
match TRICEL — necesario y correcto, pero **no** fue la causa de
ninguna de las mejoras de cobertura documentadas en §2 (ver esa
sección: el salto real vino del bug #4).

---

## 5. Camino hacia `EXACT_REPRODUCTION`

**Distrito 8 ya se cerró** (§2, §3) usando una fuente SERVEL de escrutinio final ("v2", `import_final_scrutiny()`) en vez de TRICEL mesa a mesa — evita el bug #6 y da cobertura ~100% verificada en los 28 distritos.

**Para Distrito 3, 5 y 19, la única vía identificada es corregir `dhondt_binivel()`** (§3) — no es un problema de fuente de datos, así que ninguna mejora de cobertura adicional lo resolvería:

1. **Agregar un tope de candidatos por partido al Nivel 2 de `dhondt_binivel()`**: en vez de D'Hondt directo entre partidos, aplicar D'Hondt donde cada partido no puede acumular más escaños que candidatos tiene disponibles, redistribuyendo el excedente a los siguientes cocientes más altos entre partidos con candidato disponible (algoritmo verificado exacto contra los 7 pactos en disputa de D3/D5/D19, ver §3). Requiere:
   - Cambiar la firma de `dhondt_binivel()` (o agregar un parámetro opcional) para recibir `candidatos_por_partido: dict[str, int]`.
   - Que todos los llamadores (`validate_election()`, `run_electoral_plan_binivel()`, `run_electoral_ensemble()`, scripts H4) puedan proveer ese conteo — hoy no todos tienen esa información fácilmente disponible (los ensembles de redistritaje, en particular, no modelan candidatos individuales, solo partidos).
   - Decidir el comportamiento por defecto cuando no se provee el conteo (¿sin tope, como hoy — cambio no disruptivo — o error explícito?).
2. **Alternativa parcial, ya explorada y descartada como insuficiente**: usar TRICEL mesa a mesa (`import_votes()`) como fuente primaria en vez de SERVEL — no aplica aquí, porque el problema de D3/D5/D19 nunca fue de datos (los votos ya coinciden exactamente con TRICEL vía SERVEL v2); esta vía solo habría sido relevante si la Fase 1 no hubiera cerrado Distrito 8, o si quedaran discrepancias de vote-source en otros distritos (no es el caso).

No implementado en esta sesión — ver justificación de alcance en §3.

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
    #   --votes-source tricel para reproducir el comportamiento anterior
    #   (24/28, ver bug #6 arriba)
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
