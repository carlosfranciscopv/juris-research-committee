# Anti-criterios de utilidad — codificados en 05_triage.py

Cuando una sentencia DEBE descartarse aunque parezca relevante. Cada anti-criterio
tiene un detector regex/heurístico en el script.

| ID | Trampa | Detección automática |
|---|---|---|
| AC1 | Keyword aparece solo en transcripción de la norma | Considerando contiene "artículo X dispone que" + texto literal de la norma; no hay razonamiento posterior. Detector: el considerando con la institución tiene >70% de su texto entre comillas o reproducción literal. |
| AC2 | Aparece en exposición de los hechos, no en considerandos resolutivos | El considerando con la institución NO está en el último 40% del texto, NI tiene proximidad (±3 considerandos) a fórmulas resolutivas. |
| AC3 | Aparece en cita a otra sentencia | Considerando con la institución contiene "ROL N°", "Excma. Corte resolvió", "como ha dicho esta Corte" inmediatamente antes. |
| AC4 | Ratio se basa en cuestión procesal, no sustantiva | El considerando resolutivo cita normas predominantemente procesales (CPC, COT) y la tesis es sustantiva (CC, Ley específica). |
| AC5 | Sentencia revertida posteriormente | Detector: la sentencia tiene `resultado_recurso_sup_s` = "Casa" o "Acoge" cuando la sentencia es de inferior tribunal — la mantenida es la posterior CS, no esta. |
| AC6 | Caratulado contiene la palabra pero el caso resuelve otra cuestión | overlap ratio_heuristica vs tesis < 0.3 (semántica), incluso con keyword en caratulado. |
| AC7 | Hechos materialmente distintos | El caratulado/hechos contiene términos de un dominio ortogonal (penal/familia/laboral) cuando la tesis es civil/comercial. |

## Aplicación

`05_triage.py` evalúa los AC1-AC7 secuencialmente. Si cualquiera matchea, la sentencia
queda como TANGENCIAL (con `razon_descarte: AC<N>`) y NO entra al dossier principal.
