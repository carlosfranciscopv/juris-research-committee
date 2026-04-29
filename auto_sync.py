"""Auto-sync hook: stage + commit + push tras modificaciones.

Invocado por hook PostToolUse de Claude Code (Edit|Write|MultiEdit).
Solo actúa si la ruta modificada vive dentro de juris-research-committee/.
Idempotente: si no hay cambios, no commitea nada.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_DIR_NAME = REPO_ROOT.name


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0  # nothing to do

    tool = payload.get("tool_name") or ""
    if tool not in ("Edit", "Write", "MultiEdit"):
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if SKILL_DIR_NAME not in file_path:
        return 0  # cambio fuera de la skill — ignorar

    try:
        # ¿Hay cambios staged + unstaged dentro del repo?
        status = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=15)
        if status.returncode != 0 or not status.stdout.strip():
            return 0  # sin cambios

        subprocess.run(["git", "-C", str(REPO_ROOT), "add", "-A"],
                        capture_output=True, timeout=15)
        # Mensaje de commit con archivo y tool
        rel = Path(file_path).name
        msg = f"auto-sync: {tool} on {rel}"
        commit = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit", "-m", msg,
             "--no-verify", "--no-gpg-sign"],
            capture_output=True, text=True, timeout=20)
        if commit.returncode != 0:
            return 0  # nada que commitear o conflict
        # Push silencioso (background OK)
        subprocess.Popen(
            ["git", "-C", str(REPO_ROOT), "push", "-q"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # nunca bloquear Claude Code por fallo de sync
    return 0


if __name__ == "__main__":
    sys.exit(main())
