"""Script isolado para calibrar/validar o scraping Amazon contra o DOM real.

Uso:
  1. Abra o Chrome com debug port (ver README.md), logado na Amazon e com
     a conta Amazon Associates (afiliados) ativa nessa mesma sessao (a
     barra SiteStripe so aparece nas paginas de produto quando logado
     como afiliado).
  2. Rode: python scripts/inspect_amazon_offers.py
     -> lista as ofertas do dia encontradas (usa a mesma list_offers() do
     app, ver scraper/amazon_offers_page.py).
  3. Pra testar a resolucao de link de afiliado de um produto especifico,
     passe o ASIN como argumento (10 caracteres apos "/dp/" na URL do
     produto, ex.: amazon.com.br/produto/dp/B08N5WRWNW -> ASIN=B08N5WRWNW):
     python scripts/inspect_amazon_offers.py <ASIN>
  4. Se algo quebrar (0 ofertas, botao "Obter link" nao encontrado),
     ajustar src/radar/selectors.py (AmazonOffersPageSelectors /
     AmazonSiteStripeSelectors) e o parsing em
     scraper/amazon_offers_page.py / scraper/amazon_affiliate.py conforme
     o DOM real encontrado - esta implementacao ainda NAO foi calibrada
     contra o site real (ver SPEC.md secao 6c).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.browser import connect_to_chrome
from radar.config import load_settings
from radar.exceptions import AffiliateLinkNotFoundError
from radar.scraper.amazon_affiliate import get_affiliate_link
from radar.scraper.amazon_offers_page import list_offers


def inspect_offers_page(context, settings) -> None:
    page = context.new_page()
    try:
        offers = list_offers(page, settings)
        print(f"{len(offers)} ofertas encontradas em {settings.amazon_offers_url}")
        for offer in offers[:10]:
            print(f"- {offer.discount_percent}% | R$ {offer.discount_price} | {offer.name[:60]}")
            print(f"  {offer.product_url}")
    finally:
        page.close()


def inspect_affiliate_link(context, asin: str) -> None:
    fake_product_url = f"https://www.amazon.com.br/produto/dp/{asin}"
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
