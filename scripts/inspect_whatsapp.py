"""Script isolado para calibrar seletores manualmente contra o DOM real do WhatsApp Web.

Uso:
  1. Abra o Chrome com debug port (ver README.md), va em web.whatsapp.com,
     faca login e abra um grupo com o painel de participantes visivel.
  2. Rode: python scripts/inspect_whatsapp.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.browser import connect_to_chrome
from radar.config import load_settings


def main() -> None:
    settings = load_settings()
    pw, browser, context = connect_to_chrome(settings.chrome_debug_url)
    try:
        pages = [p for p in context.pages if "web.whatsapp.com" in p.url]
        if not pages:
            print("Nenhuma aba com web.whatsapp.com aberta.")
            return
        page = pages[0]
        print(f"Titulo da pagina: {page.title()}")
        print(f"URL: {page.url}")

        # Painel lateral direito costuma ter role="complementary" ou data-testid especifico
        candidates = [
            '[data-testid="group-info-drawer"]',
            '[data-testid="drawer-right"]',
            'div[role="complementary"]',
            '[aria-label*="articipant" i]',
            '[aria-label*="embro" i]',
        ]
        for sel in candidates:
            count = page.locator(sel).count()
            print(f"Seletor '{sel}': {count} elemento(s)")

        # Lista de participantes - tenta achar linhas clicaveis dentro de listas
        list_candidates = [
            'div[role="listitem"]',
            '[data-testid="cell-frame-container"]',
        ]
        for sel in list_candidates:
            count = page.locator(sel).count()
            print(f"Lista '{sel}': {count} item(ns)")
            if count > 0:
                first = page.locator(sel).first
                print("  --- HTML do primeiro item (truncado) ---")
                html = first.evaluate("el => el.outerHTML")
                print("  " + html[:1500].replace("\n", " "))
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
