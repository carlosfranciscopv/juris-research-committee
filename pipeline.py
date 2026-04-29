"""Orquestador del pipeline juris-research-committee.

Corre 00 → 06 secuencial con fail-fast.

Uso:
  python pipeline.py --tesis "<punto a acreditar>" [opciones]

Ejemplos:
  python pipeline.py --tesis "responsabilidad solidaria del mandante por incumplimiento del contratista en obras adicionales no autorizadas"
  python pipeline.py --tesis "naturaleza jurídica del contrato de leasing financiero" --depth quick
  python pipeline.py --tesis "..." --depth exhaustive --solr-always
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"

STEPS = [
    ("00_preflight.py", ["--tesis", "{tesis}"]),
    ("01_expand_query.py", ["--tesis", "{tesis}", "--depth", "{depth}"]),
    ("02_search_local.py", ["--tesis", "{tesis}", "--depth", "{depth}"]),
    ("03_search_solr.py", ["--tesis", "{tesis}", "--depth", "{depth}",
                           "{solr_always_flag}"]),
    ("04_normalize.py", ["--tesis", "{tesis}"]),
    ("05_triage.py", ["--tesis", "{tesis}"]),
    ("06_dossier.py", ["--tesis", "{tesis}"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tesis", required=True,
                     help="Punto jurídico a acreditar")
    ap.add_argument("--depth", default="standard",
                     choices=["quick", "standard", "exhaustive"])
    ap.add_argument("--solr-always", action="store_true",
                     help="Forzar búsqueda Solr live aunque corpus local cubra")
    ap.add_argument("--manual-review", action="store_true",
                     help="(Opcional) detenerse después de 05 para revisar TRIAGE_RESULT manualmente")
    ap.add_argument("--force-restart", action="store_true",
                     help="Borrar checkpoints _WORK y empezar de cero")
    ap.add_argument("--from-step", type=int, default=0,
                     help="Reanudar desde el step indicado (0-6)")
    args = ap.parse_args()

    print(f"\n=== juris-research-committee ===")
    print(f"tesis: {args.tesis}")
    print(f"depth: {args.depth}")
    print()

    solr_flag = "--solr-always" if args.solr_always else ""

    for i, (script, args_template) in enumerate(STEPS):
        if i < args.from_step:
            print(f">>> SKIP step {i}: {script}")
            continue
        print(f"\n>>> [{i}] {script}")
        # Resolve placeholders
        resolved = []
        for a in args_template:
            a = a.replace("{tesis}", args.tesis)
            a = a.replace("{depth}", args.depth)
            a = a.replace("{solr_always_flag}", solr_flag)
            if a:
                resolved.append(a)
        cmd = [sys.executable, str(SCRIPTS_DIR / script), *resolved]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"\nFAIL en {script} (exit {r.returncode}). Pipeline aborted.")
            return r.returncode

        # Manual review hook después de fase 05
        if args.manual_review and script == "05_triage.py":
            print("\n--manual-review: pausa después de 05_triage.")
            print("Revisa TRIAGE_RESULT_*.json y luego re-ejecuta:")
            print(f"  python pipeline.py --tesis '{args.tesis}' --from-step 6")
            return 0

    print("\n=== Pipeline completo OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
