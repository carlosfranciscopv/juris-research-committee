"""03: Solr live POST a juris.pjud.cl. Solo si cobertura local insuficiente
o --solr-always."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from common import (JURIS_PJUD_BASE, JURIS_STORAGE_DEFAULT, RESEARCH_DEFAULT,
                     USER_AGENT, dump_json, ensure_research_layout, load_json,
                     log_line, normalize_rol, today_report, slugify_tesis)

DEPTH_CAP = {"quick": 30, "standard": 80, "exhaustive": 200}
PAGE_SIZE = 50


def get_csrf_and_session(storage_path: Path):
    import requests
    data = json.loads(storage_path.read_text(encoding="utf-8"))
    cookies = {c["name"]: c["value"] for c in data.get("cookies", [])
                if "pjud" in c.get("domain", "")}
    s = requests.Session()
    for k, v in cookies.items():
        s.cookies.set(k, v, domain="juris.pjud.cl")
    r = s.get(f"{JURIS_PJUD_BASE}/busqueda?Corte_Suprema",
               headers={"User-Agent": USER_AGENT}, timeout=30)
    import re
    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', r.text)
    if not m:
        return s, None
    return s, m.group(1)


def buscar_solr(session, csrf: str, id_buscador: int, term: str,
                 offset: int, page_size: int) -> dict:
    filtros = {"rol": "", "era": "", "fec_desde": "", "fec_hasta": "",
                "tipo_norma": "", "num_norma": "", "num_art": "", "num_inciso": "",
                "todas": "", "algunas": "", "excluir": "", "literal": "",
                "proximidad": "", "distancia": "", "analisis_s": "11",
                "submaterias": "", "facetas_seleccionadas": [],
                "filtros_omnibox": [{"categoria": "TEXTO", "valores": [f'"{term}"']}],
                "ids_comunas_seleccionadas_mapa": []}
    files = {"_token": (None, csrf), "id_buscador": (None, str(id_buscador)),
              "filtros": (None, json.dumps(filtros, ensure_ascii=False)),
              "numero_filas_paginacion": (None, str(page_size)),
              "offset_paginacion": (None, str(offset)),
              "orden": (None, "recientes"), "personalizacion": (None, "false")}
    headers = {"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json", "Origin": JURIS_PJUD_BASE,
                "Referer": f"{JURIS_PJUD_BASE}/busqueda?Corte_Suprema"}
    for attempt in range(3):
        try:
            r = session.post(f"{JURIS_PJUD_BASE}/busqueda/buscar_sentencias",
                              files=files, headers=headers, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def filter_doc(d: dict, id_buscador: int, year_from: int, year_to: int,
                seen_keys: set) -> dict | None:
    rol_raw = (d.get("rol_era_sup_s") or d.get("rol_era_corte_s")
                or d.get("rol_era_ape_s") or d.get("rol_era_juz_s")
                or d.get("rol_s"))
    rol = normalize_rol(rol_raw)
    if not rol:
        return None
    año = None
    for k in ("fec_sentencia_sup_dt", "fec_sentencia_corte_dt"):
        v = d.get(k)
        if v:
            try:
                año = int(str(v)[:4]); break
            except Exception:
                pass
    if año is None:
        try:
            año = int(rol.split("-")[1])
        except Exception:
            return None
    if not (year_from <= año <= year_to):
        return None
    libro = (d.get("gls_libro_sup_s") or "").upper()
    if "AUTO ACORDADO" in libro:
        return None
    tribunal = "Corte Suprema" if id_buscador == 528 else (d.get("gls_corte_s") or "?")
    key = f"rol:{rol}|{tribunal}|{año}"
    if key in seen_keys:
        return None
    seen_keys.add(key)
    return {"rol": rol, "año": año, "tribunal": tribunal, "key": key,
            "id_solr": d.get("id"), "doc": d}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tesis", required=True)
    ap.add_argument("--depth", default="standard",
                     choices=["quick", "standard", "exhaustive"])
    ap.add_argument("--root", type=Path, default=RESEARCH_DEFAULT)
    ap.add_argument("--juris-storage", type=Path, default=JURIS_STORAGE_DEFAULT)
    ap.add_argument("--solr-always", action="store_true")
    ap.add_argument("--year-from", type=int, default=2015)
    ap.add_argument("--year-to", type=int, default=2026)
    args = ap.parse_args()

    paths = ensure_research_layout(args.root)
    report = today_report(paths["reports"], "SEARCH_SOLR")
    log = lambda m: log_line(report, m)
    slug = slugify_tesis(args.tesis)

    log(f"=== 03 search_solr === slug={slug}")

    plan = load_json(paths["work"] / f"query_plan_{slug}.json", {})
    local = load_json(paths["work"] / f"candidates_local_{slug}.json", {})
    coverage = local.get("coverage_status", "ok")

    if coverage == "ok" and not args.solr_always:
        log(f"local coverage OK ({len(local.get('candidates', []))}). Skip Solr.")
        dump_json(paths["work"] / f"candidates_solr_{slug}.json",
                   {"candidates": [], "skipped": True})
        return 0

    log(f"coverage={coverage}, solr_always={args.solr_always} → Solr live")

    session, csrf = get_csrf_and_session(args.juris_storage)
    if not csrf:
        log("FALLA CSRF — sesión expirada")
        return 4
    log(f"CSRF OK ({csrf[:20]}...)")

    seen_keys = set()
    # Pre-poblar seen con candidates_local (para no duplicar)
    for c in local.get("candidates", []):
        if c.get("rol") and c.get("tribunal") and c.get("año"):
            seen_keys.add(f"rol:{c['rol']}|{c['tribunal']}|{c['año']}")

    cap = DEPTH_CAP[args.depth]
    candidates = []
    cache_dir = paths["work"] / f"CACHE_{slug}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    variantes = plan.get("variantes", [])[:10]
    log(f"variantes a consultar: {len(variantes)}")
    docs_returned = 0

    for v in variantes:
        if len(candidates) >= cap:
            log(f"cap alcanzado ({cap})")
            break
        for id_buscador, label in [(528, "CS"), (168, "CA")]:
            if len(candidates) >= cap:
                break
            try:
                data = buscar_solr(session, csrf, id_buscador,
                                    v["query"], 0, PAGE_SIZE)
            except Exception as e:
                log(f"  ERR {label} '{v['query'][:40]}': {e}")
                continue
            resp = data.get("response") or {}
            num_found = resp.get("numFound", 0)
            docs = resp.get("docs") or []
            docs_returned += len(docs)
            saved = 0
            for d in docs:
                if len(candidates) >= cap:
                    break
                f = filter_doc(d, id_buscador, args.year_from,
                                args.year_to, seen_keys)
                if not f:
                    continue
                # save solr.json
                rol_safe = f["rol"].replace("/", "-")
                solr_path = cache_dir / f"{rol_safe}.solr.json"
                try:
                    dump_json(solr_path, d)
                    candidates.append({
                        "rol": f["rol"], "tribunal": f["tribunal"],
                        "año": f["año"], "id_solr": f["id_solr"],
                        "source_query": v["query"], "id_buscador": id_buscador,
                        "solr_path": str(solr_path),
                        "caratulado": d.get("caratulado_s") or d.get("caratulado_anon_s"),
                        "url_acceso": d.get("url_acceso_sentencia"),
                    })
                    saved += 1
                except Exception as e:
                    log(f"  FAIL save {f['rol']}: {e}")
            log(f"  [{label}] '{v['query'][:50]}': numFound={num_found}, saved={saved}")
            time.sleep(0.5)
        time.sleep(0.3)

    log(f"docs Solr returned: {docs_returned} | candidates saved: {len(candidates)}")
    dump_json(paths["work"] / f"candidates_solr_{slug}.json",
               {"candidates": candidates, "stats": {"docs_returned": docs_returned}})
    log("=== 03 OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
