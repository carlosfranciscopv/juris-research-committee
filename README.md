# juris-research-committee

Skill de Claude Code que actúa como un **comité de jurisconsultos automatizado** para investigación jurisprudencial chilena. Dado un punto jurídico a acreditar, busca en `juris.pjud.cl` (Corte Suprema + Cortes de Apelaciones), filtra rigurosamente por verdadera utilidad (pronunciamiento expreso + cita verbatim recuperable + aplicabilidad + no descartabilidad trivial), y produce un dossier ejecutivo `.docx` con autoridades jerarquizadas en KILL-SHOT / HIPERPERTINENTES / PERTINENTES.

## Arquitectura

7 fases secuenciales con contratos I/O validados:

| # | Script | Función |
|---|---|---|
| 00 | `00_preflight.py` | Sesión pjud + deps + corpus + tesis válida |
| 01 | `01_expand_query.py` | Tesis → variantes Solr (sinónimos, normas, doctrinas) |
| 02 | `02_search_local.py` | BM25 sobre corpus master pre-indexado |
| 03 | `03_search_solr.py` | Solr live POST a juris.pjud.cl si cobertura local insuficiente |
| 04 | `04_normalize.py` | Parsing texto → MD-twins normalizados con frontmatter |
| 05 | `05_triage.py` | **Triage 100% determinístico**: 5 tests + scoring + adversidad |
| 06 | `06_dossier.py` | DOSSIER.docx + INDEX.md + carpeta organizada |

## Restricciones

- **Sin API LLM**: triage es 100% determinístico (regex + scoring + taxonomía YAML)
- **Sin intervención manual**: pipeline corre end-to-end sin pausas
- **Sin costo**: cero llamadas a APIs pagadas

## Uso

```bash
python pipeline.py --tesis "<punto a acreditar>" [--depth quick|standard|exhaustive]
```

Ejemplos:
- `--tesis "responsabilidad solidaria del mandante por incumplimiento del contratista"`
- `--tesis "naturaleza jurídica del contrato de leasing financiero" --depth quick`

## Output

Carpeta `RESEARCH/<slug>_<timestamp>/` con:
- `DOSSIER.docx` — memo ejecutivo con KILL-SHOT, hiperpertinentes, pertinentes, adversa, descartes
- `INDEX.md` — tabla priorizada navegable
- `MD/` — MD-twins de sentencias incluidas con frontmatter enriquecido
- `triage_log.json` — todas las clasificaciones con justificación
- `manifest.json` — metadata del run

## Calificaciones

| Nivel | Criterio |
|---|---|
| **KILL-SHOT** | CS reciente, unánime, ratio central, sin distinguishing posible |
| **HIPERPERTINENTE** | Resuelve directamente el punto, cita verbatim válida |
| **PERTINENTE** | Razonamiento aplicable (obiter potente, analogía, voto disidente) |
| **TANGENCIAL** | Menciona el tema sin pronunciarse → descartada |
| **NO_RELEVANTE** | No aplica → descartada |

Reglas duras: sin cita verbatim no entra al dossier. Adversa entra marcada con sugerencia de manejo.

## Dependencias

```bash
pip install requests beautifulsoup4 pyyaml tenacity python-docx rank-bm25 reportlab markitdown pypdf playwright
```

## Reuso de extractor-jurisprudencia-construccion

Importa `common.py` y heurísticas regex del extractor sin duplicar código. Usa el corpus pre-indexado (1921 sentencias en `JURISPRUDENCIA_CONSTRUCCIÓN/.rag/chunks.jsonl`) como base para búsqueda híbrida (RAG local primero, Solr live fallback).

## Autor

Carlos Pérez Valdivia — [carlosfranciscopv](https://github.com/carlosfranciscopv)
