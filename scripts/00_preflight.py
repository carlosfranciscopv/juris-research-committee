"""Pre-flight: validaciones duras antes de empezar el research.

Aborta con exit code accionable si algo falta:
  2: dep faltante
  3: storage_state inválido
  4: sesión Solr no captura CSRF
  5: corpus master inaccesible
  6: tesis inválida (vacía o sin instituciones detectables)
  7: disco insuficiente
  8: yaml de instituciones corrupto
"""
from __future__ import annotations

import argparse
import importlib
import re
import shutil
import sys
from pathlib import Path

import requests

from common import (
    CORPUS_MASTER_RAG,
    CORPUS_MASTER_INDEX,
    JURIS_PJUD_BASE,
    JURIS_STORAGE_DEFAULT,
    RESEARCH_DEFAULT,
    RESEARCH_REFERENCES,
    USER_AGENT,
    ensure_research_layout,
    load_yaml,
    log_line,
    today_report,
)

REQUIRED_DEPS = ["requests", "bs4", "yaml", "tenacity",
                 "docx", "rank_bm25", "reportlab"]
MIN_DISK_GB = 1


def check_session_csrf(storage_path: Path, log) -> bool:
    """Verifica que la sesión pjud capture el CSRF token."""
    try:
        import json
        data = json.loads(storage_path.read_text(encoding="utf-8"))
        cookies = {c["name"]: c["value"]
                    for c in data.get("cookies", [])
                    if "pjud" in c.get("domain", "")}
        if not cookies:
            log("FALLA: storage_state sin cookies pjud")
            return False
        session = requests.Session()
        for k, v in cookies.items():
            session.cookies.set(k, v, domain="juris.pjud.cl")
        r = session.get(f"{JURIS_PJUD_BASE}/busqueda?Corte_Suprema",
                         headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', r.text)
        if m:
            log(f"OK CSRF: {m.group(1)[:20]}... (len={len(m.group(1))})")
            return True
        log("FALLA: meta csrf-token no encontrado en HTML "
            "(probablemente sesión expirada)")
        return False
    except Exception as e:  # noqa: BLE001
        log(f"FALLA verificación sesión: {e}")
        return False


def check_tesis_validity(tesis: str, doctrina_yaml: dict, log) -> bool:
    """Verifica que la tesis no esté vacía y tenga al menos 1 institución."""
    if not tesis or len(tesis.strip()) < 10:
        log("FALLA tesis: vacía o demasiado corta (<10 chars)")
        return False
    tesis_norm = tesis.lower()
    instituciones = doctrina_yaml.get("instituciones", {})
    matches = []
    for nombre, datos in instituciones.items():
        if nombre.lower() in tesis_norm:
            matches.append(nombre)
            continue
        for sin in (datos.get("sinonimos") or []):
            if sin.lower() in tesis_norm:
                matches.append(nombre)
                break
    matches = list(set(matches))
    if not matches:
        log(f"WARN tesis: ninguna institución del yaml detectada en la tesis. "
            f"La calidad del research puede ser baja.")
        log("Sugerencia: reformular incluyendo la institución específica "
            "(ej: 'responsabilidad solidaria', 'vicios redhibitorios', "
            "'caducidad', etc.).")
        return False
    log(f"OK tesis válida. Instituciones detectadas: {', '.join(matches)}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=RESEARCH_DEFAULT)
    ap.add_argument("--juris-storage", type=Path, default=JURIS_STORAGE_DEFAULT)
    ap.add_argument("--tesis", required=True)
    ap.add_argument("--skip-session-check", action="store_true")
    args = ap.parse_args()

    paths = ensure_research_layout(args.root)
    report = today_report(paths["reports"], "PREFLIGHT")
    log = lambda m: log_line(report, m)  # noqa: E731

    log("=== 00 PREFLIGHT juris-research-committee ===")
    log(f"tesis: {args.tesis[:120]}")
    log(f"root: {args.root}")

    # 1) Deps
    missing = []
    for m in REQUIRED_DEPS:
        try:
            importlib.import_module(m)
        except ImportError:
            missing.append(m)
    if missing:
        log(f"FALLA deps: faltan {', '.join(missing)}")
        log(f"Instalar: pip install {' '.join(missing).replace('docx', 'python-docx').replace('rank_bm25', 'rank-bm25')}")
        return 2
    log(f"OK deps: {', '.join(REQUIRED_DEPS)}")

    # 2) storage_state
    if not args.juris_storage.exists():
        log(f"FALLA storage_state inexistente: {args.juris_storage}")
        return 3
    size = args.juris_storage.stat().st_size
    if size < 2000:
        log(f"FALLA storage_state pequeño ({size} bytes < 2000)")
        return 3
    log(f"OK storage_state: {size} bytes")

    # 3) Sesión Solr (rápida — sólo CSRF, no busca docs)
    if not args.skip_session_check:
        if not check_session_csrf(args.juris_storage, log):
            log("Re-ejecutar: python ../controversias-construccion-chile-detector"
                "/scripts/auth_login.py")
            return 4
    else:
        log("SKIP verificación sesión (--skip-session-check)")

    # 4) Corpus master accesible
    if not CORPUS_MASTER_RAG.exists():
        log(f"FALLA corpus master no encontrado: {CORPUS_MASTER_RAG}")
        log("Correr extractor-jurisprudencia-construccion primero.")
        return 5
    if not CORPUS_MASTER_INDEX.exists():
        log(f"FALLA MANIFEST master no encontrado: {CORPUS_MASTER_INDEX}")
        return 5
    rag_size = CORPUS_MASTER_RAG.stat().st_size
    log(f"OK corpus master: {rag_size/1024:.0f} KB")

    # 5) References yaml + md
    yaml_path = RESEARCH_REFERENCES / "normas_doctrina_map.yaml"
    if not yaml_path.exists():
        log(f"FALLA reference faltante: {yaml_path}")
        return 8
    try:
        doctrina = load_yaml(yaml_path)
        n_inst = len((doctrina or {}).get("instituciones", {}))
        log(f"OK normas_doctrina_map.yaml: {n_inst} instituciones")
    except Exception as e:  # noqa: BLE001
        log(f"FALLA yaml inválido: {e}")
        return 8

    # 6) Tesis válida
    if not check_tesis_validity(args.tesis, doctrina, log):
        return 6

    # 7) Disco
    try:
        usage = shutil.disk_usage(args.root.anchor)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < MIN_DISK_GB:
            log(f"FALLA disco: {free_gb:.1f} GB < {MIN_DISK_GB} GB")
            return 7
        log(f"OK disco: {free_gb:.1f} GB libres")
    except Exception as e:  # noqa: BLE001
        log(f"WARN disco: {e}")

    # 8) Layout
    log("Layout:")
    for k, v in paths.items():
        log(f"  {k}: {v}")

    log("=== PREFLIGHT OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
