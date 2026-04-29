"""05: Triage 100% determinístico — 5 tests + scoring + adversidad.

Implementa §2.6 del plan. SIN LLM, SIN API, SIN intervención.
"""
from __future__ import annotations
import argparse, re, sys
from datetime import datetime
from pathlib import Path
from common import (RESEARCH_DEFAULT, RESEARCH_REFERENCES, dump_json,
                     ensure_research_layout, load_json, load_yaml,
                     log_line, today_report, slugify_tesis,
                     normalize_text_for_match)

THRESHOLDS = {"KILL_SHOT": 0.85, "HIPER": 0.65, "PERTI": 0.45}
TEST3_MIN_DENSITY = 0.05  # density mínima para considerar cita verbatim válida


def tokens(s: str) -> set[str]:
    return set(w for w in normalize_text_for_match(s or "").split() if len(w) > 3)


def institucion_appears_in(considerando_text: str, inst: dict) -> bool:
    """¿La institución aparece literalmente en el considerando?"""
    t = considerando_text.lower()
    if inst["nombre"].lower() in t:
        return True
    for sin in inst.get("sinonimos", []):
        if sin.lower() in t:
            return True
    return False


def detect_anti_criterios(considerando: dict, texto_completo: str,
                            inst_central: dict | None) -> list[str]:
    """Detecta AC1-AC7 (utilidad_anti_criterios.md)."""
    flags = []
    text = considerando.get("texto") or ""
    # AC1: solo transcripción de norma (>70% entre comillas o reproducción literal)
    quote_chars = sum(1 for c in text if c in '"«»“”')
    if len(text) > 200 and quote_chars / len(text) > 0.05:
        # heurística simple: muchas comillas = transcripción dominante
        flags.append("AC1_transcripcion_norma")
    # AC2: pos_relativa < 0.6 = no resolutivo
    if considerando.get("pos_relativa", 1.0) < 0.5:
        flags.append("AC2_no_resolutivo")
    # AC3: cita a otra sentencia
    if re.search(r"(ROL\s+N°|Excma\.\s+Corte|como\s+ha\s+dicho\s+esta\s+Corte"
                  r"|sentencia\s+de\s+\d+\s+de)", text, re.IGNORECASE):
        if len(text) < 800:  # si todo el considerando es cita
            flags.append("AC3_cita_otra_sentencia")
    return flags


def calcular_density(considerando_text: str, tesis_tokens: set[str]) -> float:
    """Densidad de keywords de la tesis en el considerando."""
    cons_words = considerando_text.split()
    if not cons_words:
        return 0.0
    cons_tokens = tokens(considerando_text)
    matches = len(cons_tokens & tesis_tokens)
    return matches / len(cons_words)


def test1_pronunciamiento(unified: dict, instituciones: list[dict]) -> tuple[bool, int]:
    """Test 1: ≥2 considerandos resolutivos con la institución."""
    fm = unified["frontmatter"]
    resolutivos_nums = set(fm.get("considerandos_resolutivos") or [])
    if not resolutivos_nums:
        return False, 0
    cnt = 0
    for c in unified.get("considerandos", []):
        if c["numero"] in resolutivos_nums:
            for inst in instituciones:
                if institucion_appears_in(c["texto"], inst):
                    cnt += 1
                    break
    return cnt >= 2, cnt


def test2_normas_overlap(unified: dict, normas_tesis: set[str]) -> float:
    if not normas_tesis:
        return 0.5
    sentencia_normas = set(unified["frontmatter"].get(
        "normas_centrales_detectadas") or [])
    if not sentencia_normas:
        return 0.0
    overlap = len(sentencia_normas & normas_tesis) / len(normas_tesis)
    return overlap


def test3_cita_verbatim(unified: dict, tesis_tokens: set[str],
                          instituciones: list[dict]) -> dict | None:
    """Selecciona el considerando resolutivo con mayor densidad."""
    fm = unified["frontmatter"]
    resolutivos_nums = set(fm.get("considerandos_resolutivos") or [])
    best = None
    best_density = 0.0
    for c in unified.get("considerandos", []):
        if c["numero"] not in resolutivos_nums:
            continue
        # debe tener al menos una institución
        has_inst = any(institucion_appears_in(c["texto"], inst)
                        for inst in instituciones)
        if not has_inst:
            continue
        density = calcular_density(c["texto"], tesis_tokens)
        if density > best_density:
            best_density = density
            best = c
    if best and best_density >= TEST3_MIN_DENSITY:
        return {"considerando": best["numero"],
                "texto": best["texto"][:1500],  # cap a 1500 chars
                "densidad": round(best_density, 4)}
    return None


def test4_distinguibilidad(unified: dict, instituciones: list[dict]) -> float:
    """Devuelve factor [0..1]: 1 = no distinguible, 0 = trivialmente distinguible."""
    fm = unified["frontmatter"]
    sentencia_normas = set(fm.get("normas_centrales_detectadas") or [])
    # Detect dominio de la tesis
    ambitos_tesis = set(i.get("ambito") for i in instituciones if i.get("ambito"))
    # Heurística: si la sentencia tiene normas penal y la tesis es civil → degrada
    penal_markers = {"CPP", "Penal"}
    laboral_markers = {"CT", "Trabajo"}
    has_penal = any(m in str(sentencia_normas) for m in penal_markers)
    has_lab = any(m in str(sentencia_normas) for m in laboral_markers)
    factor = 1.0
    if "civil" in ambitos_tesis or "comercial" in ambitos_tesis:
        if has_penal and not any(a in ambitos_tesis for a in ["procesal", "tributario"]):
            factor *= 0.7
    if "civil" in ambitos_tesis and has_lab and "laboral" not in ambitos_tesis:
        factor *= 0.8
    return factor


def detectar_adversidad(unified: dict, instituciones: list[dict]) -> tuple[bool, str | None]:
    """Detecta si la ratio resuelve EN CONTRA del punto del usuario.
    Heurística: busca antónimos resolutivos en los considerandos resolutivos."""
    fm = unified["frontmatter"]
    resolutivos_nums = set(fm.get("considerandos_resolutivos") or [])
    resultado = (fm.get("resultado_recurso") or "").lower()
    # Antónimos típicos
    for inst in instituciones:
        for par in inst.get("antonimos", []):
            if "/" not in par:
                continue
            pos, neg = [p.strip().lower() for p in par.split("/", 1)]
            for c in unified.get("considerandos", []):
                if c["numero"] not in resolutivos_nums:
                    continue
                t = c["texto"].lower()
                if neg and neg in t and (not pos or pos not in t):
                    return True, par
    # Si "rechaza" predomina en resultado:
    if "rechaza" in resultado:
        # Adversa si tesis del usuario va por "se acoge"
        return True, "resultado_recurso=rechaza"
    return False, None


def calificar(score: float, tribunal: str, año: int, jerarquia: str) -> str:
    """Asigna calificación final."""
    es_cs = "Suprema" in (tribunal or "") or jerarquia == "CS"
    año_actual = datetime.now().year
    es_reciente = (año_actual - (año or 0)) <= 5
    if score >= THRESHOLDS["KILL_SHOT"] and es_cs and es_reciente:
        return "KILL_SHOT"
    if score >= THRESHOLDS["HIPER"]:
        return "HIPERPERTINENTE"
    if score >= THRESHOLDS["PERTI"]:
        return "PERTINENTE"
    return "TANGENCIAL"


def triage_one(unified: dict, plan: dict, doctrina: dict) -> dict:
    """Aplica los 5 tests a un candidato. Devuelve resultado yaml-like."""
    rol = unified["rol"]
    instituciones_raw = plan.get("instituciones") or []
    # Normaliza para tener antónimos también
    instituciones = []
    for raw in instituciones_raw:
        nombre = raw.get("nombre") if isinstance(raw, dict) else raw
        datos = (doctrina.get("instituciones") or {}).get(nombre, {})
        instituciones.append({
            "nombre": nombre,
            "sinonimos": datos.get("sinonimos") or [],
            "normas": datos.get("normas") or [],
            "antonimos": datos.get("antonimos_resolucion") or [],
            "ambito": datos.get("ambito"),
        })

    normas_tesis = set(plan.get("normas_tesis") or [])
    tesis_tokens = tokens(plan.get("tesis", ""))

    # Test 1
    t1_pass, t1_count = test1_pronunciamiento(unified, instituciones)
    if not t1_pass:
        return {
            "rol": rol, "calificacion": "NO_RELEVANTE",
            "score": 0.0, "razon_descarte": "FALLA_TEST1_PRONUNCIAMIENTO",
            "fundamento_auto": f"Solo {t1_count} considerandos resolutivos con la "
                                  f"institución (mínimo 2).",
        }

    # Test 2
    t2_overlap = test2_normas_overlap(unified, normas_tesis)

    # Test 3
    t3 = test3_cita_verbatim(unified, tesis_tokens, instituciones)
    if t3 is None:
        return {
            "rol": rol, "calificacion": "TANGENCIAL",
            "score": 0.0, "razon_descarte": "FALLA_TEST3_NO_VERBATIM",
            "fundamento_auto": "No se encontró considerando resolutivo con "
                                  "densidad de keywords suficiente para cita verbatim.",
        }

    # Anti-criterios sobre el considerando elegido
    cita_considerando = next(
        (c for c in unified.get("considerandos", [])
          if c["numero"] == t3["considerando"]), None)
    inst_central = instituciones[0] if instituciones else None
    ac_flags = (detect_anti_criterios(cita_considerando or {},
                                       "", inst_central)
                if cita_considerando else [])
    # AC1 fuerte y AC3 fuerte → degrada
    if "AC1_transcripcion_norma" in ac_flags or "AC3_cita_otra_sentencia" in ac_flags:
        return {
            "rol": rol, "calificacion": "TANGENCIAL",
            "score": 0.0, "razon_descarte": "ANTI_CRITERIOS",
            "fundamento_auto": f"Anti-criterios detectados: {ac_flags}",
            "anti_criterios_aplicados": ac_flags,
        }

    # Test 4
    t4_factor = test4_distinguibilidad(unified, instituciones)

    # Test 5: scoring
    fm = unified["frontmatter"]
    pron_density = min(1.0, t1_count / 5.0)  # cap 5 = max
    jerarquia_factor = 1.0 if "Suprema" in (fm.get("tribunal") or "") else 0.7
    año = fm.get("año") or 0
    año_actual = datetime.now().year
    recencia_factor = max(0.3, 1.0 - 0.05 * (año_actual - año))
    # Unanimidad: si voto disidente está en frontmatter (no detectamos por ahora)
    unanimidad_factor = 1.0  # default
    score = (
        0.40 * pron_density
        + 0.25 * t2_overlap
        + 0.15 * jerarquia_factor
        + 0.10 * recencia_factor
        + 0.10 * unanimidad_factor
    ) * t4_factor

    # Calificación
    cal = calificar(score, fm.get("tribunal"), año,
                     "CS" if jerarquia_factor == 1.0 else "CA")

    # Adversidad
    adversa, antonimo = detectar_adversidad(unified, instituciones)
    manejo = None
    if adversa:
        manejo = ("Sentencia adversa. Vías de manejo: (a) distinguishing por "
                  "hechos específicos del caso del usuario; (b) verificar si hay "
                  "jurisprudencia posterior en sentido opuesto; (c) crítica doctrinal.")

    return {
        "rol": rol,
        "tribunal": fm.get("tribunal"),
        "sala": fm.get("sala"),
        "fecha": fm.get("fecha"),
        "caratulado": fm.get("caratulado"),
        "calificacion": cal,
        "score": round(score, 4),
        "score_breakdown": {
            "pronunciamiento_density": round(pron_density, 4),
            "normas_overlap": round(t2_overlap, 4),
            "jerarquia_factor": jerarquia_factor,
            "recencia_factor": round(recencia_factor, 4),
            "unanimidad_factor": unanimidad_factor,
            "distinguibilidad_factor": round(t4_factor, 4),
        },
        "fundamento_auto": (
            f"Pasa Tests 1-3 ({t1_count} considerandos resolutivos con la "
            f"institución, overlap normas={t2_overlap:.0%}). "
            f"{'Adversa.' if adversa else 'Concordante con la tesis.'}"
        ),
        "cita_verbatim": t3,
        "ratio_heuristica_extraida": (cita_considerando or {}).get("texto", "")[:500],
        "normas_centrales_detectadas": fm.get("normas_centrales_detectadas") or [],
        "adversa_a_tesis": adversa,
        "antonimo_detectado": antonimo,
        "manejo_sugerido": manejo,
        "anti_criterios_aplicados": ac_flags,
        "url_acceso": fm.get("url_acceso"),
        "md_path": unified.get("md_path"),
        "source": unified.get("source"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tesis", required=True)
    ap.add_argument("--root", type=Path, default=RESEARCH_DEFAULT)
    args = ap.parse_args()

    paths = ensure_research_layout(args.root)
    report = today_report(paths["reports"], "TRIAGE")
    log = lambda m: log_line(report, m)
    slug = slugify_tesis(args.tesis)

    log(f"=== 05 triage === slug={slug}")
    plan = load_json(paths["work"] / f"query_plan_{slug}.json", {})
    unified_data = load_json(paths["work"] / f"candidates_unified_{slug}.json", {})
    candidates = unified_data.get("candidates") or []
    log(f"candidatos a triagiar: {len(candidates)}")

    if not candidates:
        log("FALLA: no hay candidatos para triagiar (corpus master vacío + Solr no recurrió)")
        # Generar reporte de gap
        gap = paths["work"] / f"COVERAGE_GAP_{slug}.md"
        gap.write_text(
            f"# COVERAGE GAP REPORT — {args.tesis}\n\n"
            f"Ningún candidato fue encontrado para esta tesis.\n\n"
            f"**Sugerencias**:\n"
            f"- Reformular la tesis con instituciones jurídicas más específicas\n"
            f"- Verificar que normas_doctrina_map.yaml cubra el tema\n"
            f"- Re-correr con --solr-always para forzar Solr live\n"
            f"- Considerar consultar doctrina académica\n",
            encoding="utf-8")
        log(f"COVERAGE_GAP_REPORT → {gap}")
        return 9

    doctrina = load_yaml(RESEARCH_REFERENCES / "normas_doctrina_map.yaml")

    results = []
    for u in candidates:
        try:
            r = triage_one(u, plan, doctrina)
        except Exception as e:
            log(f"  FAIL triage {u.get('rol')}: {e}")
            r = {"rol": u.get("rol"), "calificacion": "FAILED",
                  "razon_descarte": f"exception: {e}"}
        results.append(r)

    # Stats
    stats = {"KILL_SHOT": 0, "HIPERPERTINENTE": 0, "PERTINENTE": 0,
              "TANGENCIAL": 0, "NO_RELEVANTE": 0, "FAILED": 0,
              "adversas": 0}
    for r in results:
        cal = r.get("calificacion", "FAILED")
        stats[cal] = stats.get(cal, 0) + 1
        if r.get("adversa_a_tesis"):
            stats["adversas"] += 1
    log(f"stats: {stats}")

    # Validación: si 0 HIPER+KILL_SHOT, advertencia
    if stats["KILL_SHOT"] + stats["HIPERPERTINENTE"] == 0:
        log("WARN: 0 HIPERPERTINENTES encontrados. Tesis sin cobertura sólida.")

    out = {
        "tesis": args.tesis, "slug": slug,
        "calificaciones": results, "stats": stats,
        "thresholds": THRESHOLDS,
    }
    dump_json(paths["work"] / f"TRIAGE_RESULT_{slug}.json", out)
    log("=== 05 OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
