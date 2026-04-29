"""Re-exporta utilities del extractor-jurisprudencia-construccion + paths propios.

Importa con importlib para evitar shadow del common.py local."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Path al sibling skill (extractor)
EXTRACTOR_SKILL = (Path(__file__).resolve().parent.parent.parent
                    / "extractor-jurisprudencia-construccion")
EXTRACTOR_COMMON = EXTRACTOR_SKILL / "scripts" / "common.py"

# Carga el módulo extractor.common con nombre único
_spec = importlib.util.spec_from_file_location("extractor_common", EXTRACTOR_COMMON)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["extractor_common"] = _mod
_spec.loader.exec_module(_mod)

# Re-exporta nombres
JURIS_PJUD_BASE = _mod.JURIS_PJUD_BASE
USER_AGENT = _mod.USER_AGENT
JURIS_CONSTRUCCION_DEFAULT = _mod.JURIS_CONSTRUCCION_DEFAULT
EXTRACTOR_REFERENCES = _mod.REFERENCES_DIR
build_filename = _mod.build_filename
canonical_ciudad_apelaciones = _mod.canonical_ciudad_apelaciones
canonical_tipo_recurso = _mod.canonical_tipo_recurso
dump_json = _mod.dump_json
ensure_layout = _mod.ensure_layout
is_corte_suprema = _mod.is_corte_suprema
load_json = _mod.load_json
load_yaml = _mod.load_yaml
log_line = _mod.log_line
normalize_rol = _mod.normalize_rol
normalize_text_for_match = _mod.normalize_text_for_match
render_sentencia_pdf = _mod.render_sentencia_pdf
slugify_partes = _mod.slugify_partes
target_dir_for = _mod.target_dir_for
today_report = _mod.today_report

# Defaults propios de la research skill
RESEARCH_DEFAULT = Path(
    r"C:\Users\carlos.perezvaldivia\OneDrive - Dentons"
    r"\AAAAAAAAAAA\1_MATERIAL-JURÍDICO\JURISPRUDENCIA_RESEARCH"
)
JURIS_STORAGE_DEFAULT = Path(
    r"C:\Users\carlos.perezvaldivia\.claude\skills\_DEPRECATED"
    r"\controversias-construccion-chile-detector_2026-04-28\_AUTH"
    r"\juris_storage.json"
)
CORPUS_MASTER_RAG = JURIS_CONSTRUCCION_DEFAULT / ".rag" / "chunks.jsonl"
CORPUS_MASTER_INDEX = JURIS_CONSTRUCCION_DEFAULT / "MANIFEST.JSON"

# Refs propias de research skill
RESEARCH_REFERENCES = Path(__file__).resolve().parent.parent / "references"


def slugify_tesis(tesis: str, max_len: int = 60) -> str:
    """Convierte tesis a slug ASCII upper para nombrar carpetas."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", tesis).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").upper()
    return s[:max_len].rstrip("-")


def ensure_research_layout(research_root: Path) -> dict:
    """Crea carpetas necesarias para una corrida de research."""
    layout = {
        "root": research_root,
        "work": research_root / "_WORK",
        "reports": research_root / "_REPORTS",
        "research": research_root / "RESEARCH",
        "candidates": research_root / "_WORK" / "CANDIDATES",
    }
    for p in layout.values():
        p.mkdir(parents=True, exist_ok=True)
    return layout
