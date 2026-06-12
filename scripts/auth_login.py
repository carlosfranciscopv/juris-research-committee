"""Login interactivo en juris.pjud.cl y persistencia de sesión.

Uso:
  python scripts/auth_login.py

Abre Chromium en modo visible (headed). El usuario hace login manualmente
(ClaveÚnica o credenciales juris-PJUD). Cuando completa el login, presiona
Enter en la consola y el script guarda cookies + localStorage en
`_AUTH/juris_storage.json` (carpeta propia de esta skill, ignorada por git).

Después, 00_preflight.py y 03_search_solr.py reusan esa sesión vía
JURIS_STORAGE_DEFAULT (o `--juris-storage <ruta>`).

Sesión típica dura ~30-60 min en juris.pjud.cl. Cuando preflight detecte
expiración (exit 4), hay que re-correr este script.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from common import USER_AGENT

AUTH_DIR = Path(__file__).resolve().parent.parent / "_AUTH"
STORAGE_PATH = AUTH_DIR / "juris_storage.json"

LOGIN_URL = "https://juris.pjud.cl/busqueda/bienvenida"
TARGET_URL_AFTER = "https://juris.pjud.cl/busqueda?Corte_Suprema"


def main() -> int:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  LOGIN INTERACTIVO juris.pjud.cl (juris-research-committee)")
    print("=" * 70)
    print()
    print("Se abrirá una ventana de Chromium. Pasos:")
    print("  1) Haz login (ClaveÚnica o usuario/clave juris-PJUD)")
    print("  2) Cuando estés DENTRO del buscador, vuelve a esta consola")
    print("  3) Presiona Enter para guardar la sesión y cerrar el navegador")
    print()
    print(f"Sesión se guardará en: {STORAGE_PATH}")
    print("=" * 70)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            locale="es-CL",
            viewport={"width": 1366, "height": 900},
            no_viewport=False,
        )
        page = ctx.new_page()
        try:
            page.goto(LOGIN_URL, timeout=45000)
        except Exception as e:  # noqa: BLE001
            print(f"  warning al cargar {LOGIN_URL}: {e}")
            print("  continúa de todas formas - completa login y presiona Enter.")

        try:
            input("  -> Termina el login en la ventana, luego presiona ENTER aquí... ")
        except KeyboardInterrupt:
            print("\n  cancelado por usuario")
            browser.close()
            return 1

        try:
            page.goto(TARGET_URL_AFTER, timeout=20000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            title = page.title()
            url_actual = page.url
            print(f"  url actual: {url_actual}")
            print(f"  title: {title}")
        except Exception as e:  # noqa: BLE001
            print(f"  warning al verificar buscador: {e}")

        try:
            ctx.storage_state(path=str(STORAGE_PATH))
            print(f"  storage_state guardado: {STORAGE_PATH}")
            data_size = STORAGE_PATH.stat().st_size
            print(f"  tamaño: {data_size} bytes")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR guardando storage_state: {e}")
            browser.close()
            return 2

        browser.close()

    print()
    print("Listo. Para correr el pipeline autenticado:")
    print('  python pipeline.py --tesis "<punto a acreditar>"')
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
