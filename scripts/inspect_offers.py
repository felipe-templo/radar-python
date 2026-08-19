"""Script isolado para calibrar seletores manualmente contra o DOM real.

Uso:
  1. Abra o Chrome com debug port (ver README.md).
  2. Rode: python scripts/inspect_offers.py
  3. Confirme titulo da pagina, conte cards encontrados, ajuste
     src/radar/selectors.py conforme necessario.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.browser import connect_to_chrome
from radar.config import load_settings
from radar.selectors import OffersPageSelectors as SEL


def main() -> None:
    settings = load_settings()
    pw, browser, context = connect_to_chrome(settings.chrome_debug_url)
    try:
        page = context.new_page()
        page.goto(settings.offers_url, wait_until="domcontentloaded")
        print(f"Titulo da pagina: {page.title()}")

        cards = page.locator(SEL.OFFER_CARD)
        print(f"Cards encontrados com OFFER_CARD='{SEL.OFFER_CARD}': {cards.count()}")

        if cards.count() > 0:
            first = cards.first
            print("--- Primeiro card (debug) ---")
            print("Titulo:", first.locator(SEL.OFFER_TITLE).first.inner_text() if first.locator(SEL.OFFER_TITLE).count() else "NAO ENCONTRADO")
            print("Link:", first.locator(SEL.OFFER_LINK).first.get_attribute("href") if first.locator(SEL.OFFER_LINK).count() else "NAO ENCONTRADO")
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
