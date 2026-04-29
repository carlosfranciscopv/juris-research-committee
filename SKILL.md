---
name: juris-research-committee
description: Comité de jurisconsultos automatizado que busca jurisprudencia chilena (Corte Suprema + Cortes de Apelaciones) sobre un punto jurídico específico, descarga las sentencias, las filtra rigurosamente por verdadera utilidad (pronunciamiento expreso + cita verbatim recuperable + aplicabilidad + no descartabilidad trivial), y produce un dossier ejecutivo .docx con KILL-SHOT/HIPERPERTINENTES/PERTINENTES jerarquizadas + apéndice de descartes con razón. Activar con "busca jurisprudencia sobre", "fundamenta con sentencias", "comité jurisconsultos sobre", "investigación jurisprudencial sobre", "qué dijo la Corte sobre", "jurisprudencia para fundar", "research jurisprudencial", "juris-research-committee". Usa primero el corpus pre-indexado (1921 sentencias construcción), si insuficiente va a juris.pjud.cl live. NO requiere API LLM — triage 100% determinístico. NO usar para descargar bulk sin tesis específica (→ extractor-jurisprudencia-construccion).
---

# Skill: juris-research-committee

## Qué hace

Dado un **punto jurídico a acreditar** (cualquier materia del derecho chileno), produce un dossier de jurisprudencia útil para fundamentar ese punto en un escrito o asesoría.

## Cómo invocarla

```
python pipeline.py --tesis "<punto a acreditar>" [--depth quick|standard|exhaustive] [--output <carpeta>]
```

Ejemplos:
- `--tesis "responsabilidad solidaria del mandante por incumplimiento del contratista en obras adicionales no autorizadas"`
- `--tesis "naturaleza jurídica del contrato de leasing financiero" --depth quick`
- `--tesis "procedencia del recurso de protección frente a la pérdida sobreviniente del legítimo contradictor" --depth exhaustive`

## Qué produce

Carpeta `RESEARCH/<slug-tesis>_<timestamp>/` con:
- **DOSSIER.docx** — memo ejecutivo: KILL-SHOT, HIPERPERTINENTES, PERTINENTES, adversa (si la hay), descartes con razón, bibliografía
- **INDEX.md** — tabla priorizada navegable
- **PDFS/** — PDFs profesionales de cada sentencia
- **MD/** — MD-twins con frontmatter enriquecido
- **triage_log.json** — todas las clasificaciones con justificación
- **manifest.json** — metadata del run

## Arquitectura

7 fases secuenciales con contratos I/O validados:

1. **00_preflight** — sesión pjud + deps + corpus master + tesis válida
2. **01_expand_query** — tesis → variantes Solr (sinónimos, normas, doctrinas)
3. **02_search_local** — BM25 sobre corpus existente (1921 sentencias)
4. **03_search_solr** — POST live a juris.pjud.cl si cobertura local insuficiente
5. **04_normalize** — parsing texto → MD-twins normalizados con frontmatter
6. **05_triage** — 5 tests determinísticos: pronunciamiento expreso → match normas → cita verbatim → distinguibilidad → scoring final
7. **06_dossier** — python-docx + estructura carpeta destino + validación verbatim end-to-end

## Calificación de utilidad

| Nivel | Criterio |
|---|---|
| **KILL-SHOT** | CS reciente, unánime, ratio central, cita verbatim potente, sin distinguishing |
| **HIPERPERTINENTE** | Resuelve directamente el punto, cita verbatim válida |
| **PERTINENTE** | Razonamiento aplicable (obiter potente, analogía, voto disidente) |
| **TANGENCIAL** | Menciona el tema sin pronunciarse → descartada |
| **NO_RELEVANTE** | No aplica → descartada |

Reglas duras: sin cita verbatim no entra al dossier. Adversa entra marcada con sugerencia de manejo. Una sola por ratio idéntica (la más fuerte gana).

## Restricciones

- **NO requiere API LLM** — triage es 100% determinístico (regex + scoring + taxonomía yaml).
- **NO requiere intervención manual** — modo `--manual-review` es opcional.
- **NO falla silenciosamente** — si no hay cobertura, aborta con `COVERAGE_GAP_REPORT.md` antes de generar dossier vacío.

## Reuso de extractor-jurisprudencia-construccion

Importa `common.py`, `01_harvest.py:buscar`, `02_extract.py` heurísticas. Sin cambios destructivos a la skill original.
