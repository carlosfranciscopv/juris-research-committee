"""04: parsing texto Solr → MD-twins normalizados con frontmatter para triage."""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
import yaml
from common import (RESEARCH_DEFAULT, dump_json, ensure_research_layout,
                     load_json, log_line, today_report, slugify_tesis)

# Heurísticas de extracción
RE_CONSIDERANDO = re.compile(
    r"(?:^|\n)\s*(?:CONSIDERANDO|Considerando)\s+(?:N°\s*)?"
    r"(?:VIG[ÉE]SIMO|D[ÉE]CIMO|N?ON?[OÉÉ]G[ÉE]SIMO|"
    r"Primer|Segundo|Tercer|Cuarto|Quinto|Sexto|S[ée]ptimo|Octavo|Noveno|"
    r"D[ée]cimo|Und[ée]cimo|Duod[ée]cimo|"
    r"\d+°?)\s*[°.:]?\s*",
    re.IGNORECASE | re.MULTILINE)

RE_NUM_CONSIDERANDO = re.compile(
    r"(?:^|\n)\s*(\d+)[°ºªo\.\)]\s+", re.MULTILINE)

RE_NORMA = re.compile(
    r"(?:art[íi]culo|art\.?)\s*(\d+(?:\s*bis|\s*ter|\s*quater)?)"
    r"\s+(?:del?\s+)?"
    r"(C[óo]digo\s+(?:Civil|de\s+Comercio|del\s+Trabajo|Procesal\s+Penal|"
    r"de\s+Procedimiento\s+Civil|Org[áa]nico\s+de\s+Tribunales|Tributario|"
    r"Penal)|"
    r"Ley\s+N?°?\s*[\d\.]+|"
    r"Constituci[óo]n|"
    r"DL\s+\d+|DFL\s+\d+)",
    re.IGNORECASE)

RE_RESOLUTIVA = re.compile(
    r"(?:por\s+est[oa]s?\s+(?:considerandos?|consideraciones)|"
    r"se\s+(?:acoge|rechaza|confirma|revoca|casa|invalid[a])|"
    r"acoge|rechaza|confirma|revoca|casa)",
    re.IGNORECASE)


RE_HEADING_CONSIDERANDO = re.compile(
    r"(?:^|\n)\s*##+\s*Considerando\s+(\d+)\s*[°ºªo]?\s*",
    re.IGNORECASE)


def extract_considerandos(texto: str) -> list[dict]:
    """Extrae considerandos numerados con su texto.
    Combina dos formatos: '## Considerando N' (MD-twin existente) y
    'Nº' al inicio de línea (texto Solr crudo)."""
    if not texto:
        return []
    splits_md = list(RE_HEADING_CONSIDERANDO.finditer(texto))
    splits_raw = list(RE_NUM_CONSIDERANDO.finditer(texto))
    splits = splits_md if len(splits_md) >= 3 else splits_raw
    out = []
    for i, m in enumerate(splits):
        n = int(m.group(1))
        start = m.end()
        end = splits[i+1].start() if i+1 < len(splits) else len(texto)
        ctext = texto[start:end].strip()
        if 30 < len(ctext) < 10000:
            out.append({"numero": n, "texto": ctext,
                          "pos_relativa": start / max(len(texto), 1)})
    return out


def extract_normas_centrales(texto: str) -> list[str]:
    """Detecta normas centrales (≥2 menciones cuerpo+articulo)."""
    if not texto:
        return []
    counter: dict = {}
    for m in RE_NORMA.finditer(texto):
        art = m.group(1).strip()
        cuerpo = m.group(2).strip()
        # Normaliza cuerpo a abreviatura
        cuerpo_norm = cuerpo
        if "Civil" in cuerpo:
            cuerpo_norm = "CC"
        elif "Comercio" in cuerpo:
            cuerpo_norm = "CCom"
        elif "Trabajo" in cuerpo:
            cuerpo_norm = "CT"
        elif "Procedimiento Civil" in cuerpo:
            cuerpo_norm = "CPC"
        elif "Procesal Penal" in cuerpo:
            cuerpo_norm = "CPP"
        elif "Org" in cuerpo:
            cuerpo_norm = "COT"
        elif "Tribut" in cuerpo:
            cuerpo_norm = "CTrib"
        elif "Constitu" in cuerpo:
            cuerpo_norm = "Constitución"
        key = f"{cuerpo_norm} art {art}"
        counter[key] = counter.get(key, 0) + 1
    return [k for k, c in counter.items() if c >= 2]


def detectar_resolutivos(considerandos: list[dict], texto_completo: str) -> list[int]:
    """Considerandos resolutivos: en último 40% Y proximidad a fórmulas."""
    if not considerandos or not texto_completo:
        return []
    resolutivos = []
    for c in considerandos:
        # Último 40%
        en_zona = c["pos_relativa"] >= 0.6
        # Proximidad a verbo resolutivo (en su propio texto o ±200 chars)
        tiene_verbo = bool(RE_RESOLUTIVA.search(c["texto"]))
        if en_zona or tiene_verbo:
            resolutivos.append(c["numero"])
    return resolutivos


def normalize_one(candidate: dict, source: str, paths: dict, log) -> dict | None:
    """Produce MD-twin normalizado y entry unificada."""
    rol = candidate.get("rol")
    if not rol:
        return None

    # Get texto
    texto = ""
    solr_doc = None
    if source == "solr" and candidate.get("solr_path"):
        try:
            solr_doc = load_json(Path(candidate["solr_path"]), {})
        except Exception:
            return None
        texto = solr_doc.get("texto_sentencia") or solr_doc.get("texto_sentencia_anon") or ""
    elif source == "local":
        # Para locales, leer el MD existente
        md_rel = candidate.get("archivo_md")
        if md_rel:
            from common import JURIS_CONSTRUCCION_DEFAULT
            md_path = JURIS_CONSTRUCCION_DEFAULT / md_rel
            try:
                texto = md_path.read_text(encoding="utf-8")
            except Exception:
                pass

    if not texto or len(texto) < 500:
        log(f"  skip {rol}: texto vacío o muy corto ({len(texto)} chars)")
        return None

    considerandos = extract_considerandos(texto)
    normas = extract_normas_centrales(texto)
    resolutivos = detectar_resolutivos(considerandos, texto)

    # Frontmatter
    fm = {
        "rol": rol,
        "tribunal": candidate.get("tribunal"),
        "año": candidate.get("año"),
        "caratulado": candidate.get("caratulado"),
        "source": source,
        "n_considerandos": len(considerandos),
        "n_resolutivos": len(resolutivos),
        "considerandos_resolutivos": resolutivos,
        "normas_centrales_detectadas": normas,
        "texto_chars": len(texto),
    }
    if solr_doc:
        fm["sala"] = solr_doc.get("gls_sala_sup_s")
        fm["fecha"] = (solr_doc.get("fec_sentencia_sup_dt") or "")[:10]
        fm["redactor"] = solr_doc.get("gls_redactor_s")
        fm["resultado_recurso"] = solr_doc.get("resultado_recurso_sup_s")
        fm["tipo_recurso"] = solr_doc.get("gls_tip_recurso_sup_s")
        fm["url_acceso"] = solr_doc.get("url_acceso_sentencia")
    elif source == "local":
        fm["fecha"] = candidate.get("fecha")
        fm["archivo_pdf_master"] = candidate.get("archivo_pdf")

    # MD twin
    rol_safe = rol.replace("/", "-")
    md_path = paths["candidates"] / f"{rol_safe}.md"
    md_content = ["---", yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip(), "---", ""]
    md_content.append(f"# {fm.get('caratulado') or rol}")
    md_content.append("")
    md_content.append("## Considerandos resolutivos detectados (heurística)")
    md_content.append("")
    for c in considerandos:
        if c["numero"] in resolutivos:
            md_content.append(f"### Considerando {c['numero']}°")
            md_content.append("")
            md_content.append(c["texto"])
            md_content.append("")
    md_content.append("## Texto íntegro")
    md_content.append("")
    md_content.append(texto)
    md_path.write_text("\n".join(md_content), encoding="utf-8")

    return {
        "rol": rol, "tribunal": candidate.get("tribunal"),
        "año": candidate.get("año"), "source": source,
        "md_path": str(md_path),
        "frontmatter": fm,
        "considerandos": considerandos,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tesis", required=True)
    ap.add_argument("--root", type=Path, default=RESEARCH_DEFAULT)
    args = ap.parse_args()

    paths = ensure_research_layout(args.root)
    report = today_report(paths["reports"], "NORMALIZE")
    log = lambda m: log_line(report, m)
    slug = slugify_tesis(args.tesis)

    log(f"=== 04 normalize === slug={slug}")
    local = load_json(paths["work"] / f"candidates_local_{slug}.json", {})
    solr = load_json(paths["work"] / f"candidates_solr_{slug}.json", {})

    candidates_local = local.get("candidates") or []
    candidates_solr = solr.get("candidates") or []
    log(f"candidatos locales: {len(candidates_local)}, solr: {len(candidates_solr)}")

    unified = []
    seen_rols = set()
    # Solr first (más fresco)
    for c in candidates_solr:
        if c["rol"] in seen_rols:
            continue
        seen_rols.add(c["rol"])
        u = normalize_one(c, "solr", paths, log)
        if u:
            unified.append(u)
    for c in candidates_local:
        if c["rol"] in seen_rols:
            continue
        seen_rols.add(c["rol"])
        u = normalize_one(c, "local", paths, log)
        if u:
            unified.append(u)

    log(f"normalizados: {len(unified)}")
    dump_json(paths["work"] / f"candidates_unified_{slug}.json",
               {"candidates": unified})
    log("=== 04 OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
