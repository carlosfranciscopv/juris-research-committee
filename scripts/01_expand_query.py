"""01: tesis → variantes Solr ricas (sinónimos + normas + tipos recurso)."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
from common import (RESEARCH_DEFAULT, RESEARCH_REFERENCES, dump_json,
                     ensure_research_layout, load_yaml, log_line, today_report,
                     slugify_tesis)

DEPTH_VARIANTS = {"quick": 5, "standard": 10, "exhaustive": 18}


def detect_instituciones(tesis: str, doctrina: dict) -> list[dict]:
    """Detecta instituciones del yaml en la tesis."""
    tesis_low = tesis.lower()
    found = []
    for nombre, datos in (doctrina.get("instituciones") or {}).items():
        keywords = [nombre] + (datos.get("sinonimos") or [])
        for kw in keywords:
            if kw.lower() in tesis_low:
                found.append({
                    "nombre": nombre,
                    "match_keyword": kw,
                    "sinonimos": datos.get("sinonimos") or [],
                    "normas": datos.get("normas") or [],
                    "antonimos": datos.get("antonimos_resolucion") or [],
                    "ambito": datos.get("ambito"),
                    "tipo_recurso_tipico": datos.get("tipo_recurso_tipico") or [],
                })
                break
    # dedup por nombre
    seen = set()
    unique = []
    for f in found:
        if f["nombre"] not in seen:
            unique.append(f)
            seen.add(f["nombre"])
    return unique


def generate_variants(instituciones: list[dict], tesis: str,
                       max_variants: int) -> list[dict]:
    """Genera variantes Solr priorizadas."""
    variants = []
    # P0: la tesis literal (si tiene 3-8 palabras significativas)
    palabras = [w for w in tesis.split() if len(w) > 3]
    if 3 <= len(palabras) <= 8:
        variants.append({"query": " ".join(palabras),
                          "peso": 1.0, "tipo": "literal"})
    # P1: una variante por institución (sinónimo principal)
    for inst in instituciones:
        variants.append({"query": inst["nombre"], "peso": 0.95,
                          "tipo": "institucion", "instituciones": [inst["nombre"]]})
        # primer sinónimo si distinto
        for sin in inst["sinonimos"][:2]:
            if sin.lower() != inst["nombre"].lower():
                variants.append({"query": sin, "peso": 0.85,
                                  "tipo": "sinonimo",
                                  "instituciones": [inst["nombre"]]})
    # P2: combinación institución + segunda institución (si hay 2+)
    if len(instituciones) >= 2:
        for i in range(min(2, len(instituciones)-1)):
            q = f"{instituciones[i]['nombre']} {instituciones[i+1]['nombre']}"
            variants.append({"query": q, "peso": 0.75, "tipo": "combinacion",
                              "instituciones": [instituciones[i]['nombre'],
                                                 instituciones[i+1]['nombre']]})
    # P3: query por norma central (cuerpo + artículo)
    for inst in instituciones:
        for norma in inst["normas"][:2]:
            # extrae art número
            import re
            m = re.search(r"art\s*(\d+)", norma, re.IGNORECASE)
            if m:
                art_n = m.group(1)
                cuerpo = norma.split(" art")[0].strip()
                variants.append({
                    "query": f"\"artículo {art_n}\" {cuerpo}",
                    "peso": 0.7, "tipo": "norma",
                    "norma": norma, "instituciones": [inst["nombre"]]
                })
    # dedup por query
    seen = set()
    unique = []
    for v in variants:
        k = v["query"].lower().strip()
        if k not in seen:
            unique.append(v)
            seen.add(k)
    # cap por max
    return unique[:max_variants]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tesis", required=True)
    ap.add_argument("--depth", default="standard",
                     choices=["quick", "standard", "exhaustive"])
    ap.add_argument("--root", type=Path, default=RESEARCH_DEFAULT)
    args = ap.parse_args()

    paths = ensure_research_layout(args.root)
    report = today_report(paths["reports"], "EXPAND_QUERY")
    log = lambda m: log_line(report, m)

    log(f"=== 01 expand_query === depth={args.depth}")
    log(f"tesis: {args.tesis}")

    doctrina = load_yaml(RESEARCH_REFERENCES / "normas_doctrina_map.yaml")
    instituciones = detect_instituciones(args.tesis, doctrina)
    log(f"instituciones detectadas: {len(instituciones)}")
    for inst in instituciones:
        log(f"  - {inst['nombre']} ({inst['ambito']}) → {len(inst['normas'])} normas")

    if not instituciones:
        log("FALLA: ninguna institución detectada en la tesis. "
            "Reformular incluyendo institución específica.")
        return 6

    n_max = DEPTH_VARIANTS[args.depth]
    variants = generate_variants(instituciones, args.tesis, n_max)
    log(f"variantes Solr generadas: {len(variants)}")
    for v in variants:
        log(f"  [{v['peso']:.2f}|{v['tipo']}] {v['query'][:80]}")

    # Normas únicas detectadas (para fase 02 + 05)
    normas_tesis = set()
    for inst in instituciones:
        for n in inst["normas"]:
            normas_tesis.add(n)

    slug = slugify_tesis(args.tesis)
    plan = {
        "tesis": args.tesis,
        "slug": slug,
        "depth": args.depth,
        "instituciones": instituciones,
        "variantes": variants,
        "normas_tesis": sorted(normas_tesis),
    }
    out = paths["work"] / f"query_plan_{slug}.json"
    dump_json(out, plan)
    log(f"query_plan → {out}")
    log("=== 01 OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
