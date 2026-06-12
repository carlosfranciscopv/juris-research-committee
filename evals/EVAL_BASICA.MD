# EVAL BÁSICA - juris-research-committee

Dos casos verificables para validar una corrida del pipeline. Ejecutar desde
la raíz de la skill. Requiere sesión pjud vigente para el caso (a) si el
corpus local resulta insuficiente (si la cobertura local basta, la fase Solr
no se ejecuta).

## Caso (a) - positivo: tesis con cobertura en el corpus

Comando:

```
python pipeline.py --tesis "responsabilidad solidaria del mandante por incumplimiento del contratista" --depth quick
```

Resultado esperado (todos verificables):

1. Exit code 0 (pipeline completo, "Pipeline completo OK").
2. Existe una carpeta nueva `RESEARCH/<slug>_<timestamp>/` bajo
   `JURISPRUDENCIA_RESEARCH/RESEARCH/`, donde `<slug>` comienza con
   `RESPONSABILIDAD-SOLIDARIA-DEL-MANDANTE`.
3. Dentro de esa carpeta existen: `DOSSIER.DOCX`, `INDEX.MD`,
   `TRIAGE_LOG.JSON`, `MANIFEST.JSON`, y las carpetas `MD/` y `PDFS/`.
4. `TRIAGE_LOG.JSON` contiene el objeto `stats` y al menos 1 entrada de
   `calificaciones` con calificación distinta de `FAILED`.
5. `DOSSIER.DOCX` abre en Word con cuerpo y encabezados Garamond 12,
   página Legal y numeración de páginas al pie.

## Caso (b) - negativo: tesis sin institución del yaml

Comando:

```
python pipeline.py --tesis "asuntos varios generales sin institucion" --depth quick
```

Resultado esperado:

1. El pipeline aborta en `00_preflight.py` con exit code 6
   (tesis inválida: ninguna institución de `normas_doctrina_map.yaml`
   detectada).
2. NO se genera ninguna carpeta nueva en `RESEARCH/` (sin dossier vacío).
3. El reporte `_REPORTS/PREFLIGHT_<fecha>.MD` registra la falla con la
   sugerencia de reformular la tesis con la institución específica.
