# Anti-criterios de utilidad - estado de implementación en 05_triage.py

Cuando una sentencia DEBE descartarse aunque parezca relevante. La columna
"Estado en código" declara qué detecta hoy realmente `05_triage.py`: no todos
los anti-criterios tienen detector implementado.

| ID | Trampa | Detección documentada | Estado en código |
|---|---|---|---|
| AC1 | Keyword aparece solo en transcripción de la norma | Considerando contiene "artículo X dispone que" + texto literal de la norma; no hay razonamiento posterior. Detector: el considerando con la institución tiene >70% de su texto entre comillas o reproducción literal. | **Implementado y degrada** (`detect_anti_criterios`, heurística de densidad de comillas; flag `AC1_transcripcion_norma` fuerza TANGENCIAL). |
| AC2 | Aparece en exposición de los hechos, no en considerandos resolutivos | El considerando con la institución NO está en el último 40% del texto (`pos_relativa < 0.6`), NI tiene proximidad (±3 considerandos) a fórmulas resolutivas. | **Detectado, no degrada** (flag `AC2_no_resolutivo` se computa con umbral 0.6 pero no fuerza descarte; el filtro efectivo lo hace `test1_pronunciamiento`, que solo acepta considerandos resolutivos). |
| AC3 | Aparece en cita a otra sentencia | Considerando con la institución contiene "ROL N°", "Excma. Corte resolvió", "como ha dicho esta Corte" inmediatamente antes. | **Implementado y degrada** (flag `AC3_cita_otra_sentencia` fuerza TANGENCIAL cuando el considerando es corto y dominado por la cita). |
| AC4 | Ratio se basa en cuestión procesal, no sustantiva | El considerando resolutivo cita normas predominantemente procesales (CPC, COT) y la tesis es sustantiva (CC, Ley específica). | **Cubierto parcialmente** por `test4_distinguibilidad` (degrada factor por mismatch de ámbito penal/laboral vs civil-comercial; NO clasifica procesal vs sustantivo). |
| AC5 | Sentencia revertida posteriormente | Detector: la sentencia tiene `resultado_recurso_sup_s` = "Casa" o "Acoge" cuando la sentencia es de inferior tribunal - la mantenida es la posterior CS, no esta. | **No implementado** (requiere seguimiento de cadena de instancias). |
| AC6 | Caratulado contiene la palabra pero el caso resuelve otra cuestión | overlap ratio_heuristica vs tesis < 0.3 (semántica), incluso con keyword en caratulado. | **No implementado** (requiere medida semántica de overlap). |
| AC7 | Hechos materialmente distintos | El caratulado/hechos contiene términos de un dominio ortogonal (penal/familia/laboral) cuando la tesis es civil/comercial. | **Cubierto parcialmente** por `test4_distinguibilidad` (heurística por normas detectadas: marcadores CPP/Penal y CT/Trabajo degradan factor; familia no cubierto). |

## Aplicación

`05_triage.py` (`detect_anti_criterios`) detecta hoy AC1-AC3 sobre el
considerando elegido para la cita verbatim; de esos, solo AC1 y AC3 degradan a
TANGENCIAL (con `razon_descarte: ANTI_CRITERIOS` y los flags aplicados en
`anti_criterios_aplicados`). AC2 se computa pero no degrada por sí solo. AC4 y
AC7 quedan cubiertos parcialmente por `test4_distinguibilidad` (factor
multiplicativo sobre el score, no descarte binario). AC5 y AC6 NO tienen
detector: si el caso lo exige, deben verificarse manualmente sobre el dossier.
