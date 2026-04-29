"""02: BM25 sobre corpus master existente."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from common import (CORPUS_MASTER_RAG, RESEARCH_DEFAULT, dump_json,
                     ensure_research_layout, load_json, log_line, today_report,
                     slugify_tesis, normalize_text_for_match)

DEPTH_TOPK = {"quick": 20, "standard": 50, "exhaustive": 100}
MIN_SCORE = 0.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tesis", required=True)
    ap.add_argument("--depth", default="standard",
                     choices=["quick", "standard", "exhaustive"])
    ap.add_argument("--root", type=Path, default=RESEARCH_DEFAULT)
    args = ap.parse_args()

    paths = ensure_research_layout(args.root)
    report = today_report(paths["reports"], "SEARCH_LOCAL")
    log = lambda m: log_line(report, m)
    slug = slugify_tesis(args.tesis)
    plan = load_json(paths["work"] / f"query_plan_{slug}.json", {})

    log(f"=== 02 search_local === slug={slug}")

    if not CORPUS_MASTER_RAG.exists():
        log("WARN corpus master no existe — skip local search")
        dump_json(paths["work"] / f"candidates_local_{slug}.json",
                   {"candidates": [], "coverage_status": "no_corpus"})
        return 0

    # Load chunks
    log(f"loading chunks from {CORPUS_MASTER_RAG}")
    chunks = []
    with CORPUS_MASTER_RAG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    log(f"  total chunks: {len(chunks)}")

    if not chunks:
        log("FALLA chunks vacíos")
        dump_json(paths["work"] / f"candidates_local_{slug}.json",
                   {"candidates": [], "coverage_status": "empty_corpus"})
        return 0

    # BM25
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        log("FALLA rank-bm25 no instalado")
        return 2

    # Tokenize chunks
    def tok(text: str) -> list[str]:
        return [w for w in normalize_text_for_match(text or "").split()
                if len(w) > 2]

    log("tokenizing chunks...")
    tokenized = [tok(c.get("text", "")) for c in chunks]
    log("building BM25 index...")
    bm25 = BM25Okapi(tokenized)

    # Score each variant
    topk = DEPTH_TOPK[args.depth]
    doc_scores: dict = {}  # doc_id → {score, evidences}
    for v in plan.get("variantes", []):
        q_tokens = tok(v["query"])
        if not q_tokens:
            continue
        scores = bm25.get_scores(q_tokens)
        # top K
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:topk]
        for idx, score in ranked:
            if score < MIN_SCORE:
                continue
            ch = chunks[idx]
            doc_id = ch.get("doc_id") or ch.get("metadata", {}).get("rol")
            if not doc_id:
                continue
            entry = doc_scores.setdefault(doc_id, {
                "doc_id": doc_id,
                "rol": ch.get("metadata", {}).get("rol"),
                "tribunal": ch.get("metadata", {}).get("tribunal"),
                "año": ch.get("metadata", {}).get("año"),
                "caratulado": ch.get("metadata", {}).get("caratulado_oficial"),
                "fecha": ch.get("metadata", {}).get("fecha_sentencia"),
                "archivo_md": ch.get("metadata", {}).get("archivo_md"),
                "archivo_pdf": ch.get("metadata", {}).get("archivo_pdf"),
                "score_max": 0.0, "score_sum": 0.0,
                "evidence_chunks": [],
            })
            entry["score_max"] = max(entry["score_max"], float(score))
            entry["score_sum"] += float(score)
            if len(entry["evidence_chunks"]) < 3:
                entry["evidence_chunks"].append({
                    "chunk_id": ch.get("chunk_id"),
                    "score": round(float(score), 2),
                    "matched_query": v["query"][:80],
                    "text_preview": (ch.get("text", "") or "")[:300],
                })

    # Aggregate score: max + 0.3 * sum
    candidates = []
    for d in doc_scores.values():
        d["score_aggregate"] = d["score_max"] + 0.3 * d["score_sum"]
        candidates.append(d)
    candidates.sort(key=lambda x: x["score_aggregate"], reverse=True)
    candidates = candidates[: topk * 2]  # cap final

    coverage = "ok" if len(candidates) >= 5 else "insufficient"
    log(f"local candidates: {len(candidates)} | coverage: {coverage}")
    for c in candidates[:5]:
        log(f"  [{c['score_aggregate']:.1f}] {c['rol']} ({c['tribunal']}) — "
            f"{(c.get('caratulado') or '')[:60]}")

    out = {
        "tesis": args.tesis, "slug": slug,
        "candidates": candidates,
        "coverage_status": coverage,
    }
    dump_json(paths["work"] / f"candidates_local_{slug}.json", out)
    log(f"=== 02 OK === ({len(candidates)} candidatos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
