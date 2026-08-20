"""Script isolado para calibrar/validar o scraping Shopee contra o DOM real.

Uso:
  1. Abra o Chrome com debug port (ver README.md), logado na Shopee e no
     portal de afiliados (affiliate.shopee.com.br).
  2. Rode: python scripts/inspect_shopee_offers.py
     -> lista as ofertas relampago encontradas (usa a mesma
     list_offers() do app, ver scraper/shopee_offers_page.py).
  3. Pra testar a resolucao de link de afiliado de um item especifico,
     passe o item_id como argumento (o numero apos o ultimo ponto na URL
     do produto, ex.: shopee.com.br/produto-i.123.456 -> item_id=456):
     python scripts/inspect_shopee_offers.py <item_id>
  4. Se algo quebrar (0 ofertas, botao "Obter link" nao encontrado),
     ajustar src/radar/selectors.py (ShopeeOffersPageSelectors /
     ShopeeAffiliatePortalSelectors) e o parsing em
     scraper/shopee_offers_page.py conforme o DOM real encontrado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.browser import connect_to_chrome
from radar.config import load_settings
from radar.exceptions import AffiliateLinkNotFoundError
from radar.scraper.shopee_affiliate import get_affiliate_link
from radar.scraper.shopee_offers_page import list_offers


def inspect_offers_page(context, settings) -> None:
    page = context.new_page()
    try:
        offers = list_offers(page, settings)
        print(f"{len(offers)} ofertas encontradas em {settings.shopee_offers_url}")
        for offer in offers[:10]:
            print(f"- {offer.discount_percent}% | R$ {offer.discount_price} | {offer.name[:60]}")
            print(f"  {offer.product_url}")
    finally:
        page.close()


def inspect_affiliate_link(context, item_id: str) -> None:
    fake_product_url = f"https://shopee.com.br/produto-i.0.{item_id}"
    try:
        link = get_affiliate_link(context, fake_product_url)
        print(f"Link de afiliado obtido: {link}")
    except AffiliateLinkNotFoundError as exc:
        print(f"FALHOU: {exc}")


def main() -> None:
    settings = load_settings()
    pw, browser, context = connect_to_chrome(settings.chrome_debug_url)
    try:
        inspect_offers_page(context, settings)
        if len(sys.argv) > 1:
            inspect_affiliate_link(context, sys.argv[1])
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
