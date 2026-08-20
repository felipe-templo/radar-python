import logging
import random
import re
from decimal import Decimal

from playwright.sync_api import Page

from radar.config import Settings
from radar.models import RawOfferCard
from radar.parsing import parse_price
from radar.selectors import ShopeeOffersPageSelectors as SEL

logger = logging.getLogger(__name__)

MAX_SCROLL_ITERATIONS = 20

# Calibrado em 2026-08-19 contra o aria-label real dos cards (ver selectors.py).
# "null" e um token fixo observado antes de "promocao" em todos os cards
# testados (o campo de preco original parece sempre vazio/quebrado no
# template de acessibilidade da Shopee) - "menos"/"atual"/"R$" sao os
# unicos pontos fixos usados como ancora, o resto e tratado como opaco
# (\S+) pra nao depender de acentuacao/redacao exata.
CARD_LABEL_PATTERN = re.compile(
    r"menos\s+(?P<discount>\d+)%\s+\S+\s+atual\s+R\$\s*(?P<price>[\d.,]+)",
    re.IGNORECASE,
)
NAME_TRIM_PATTERN = re.compile(r"\s+(null\s+)?\S+\Z", re.IGNORECASE)


def _dismiss_cookie_banner(page: Page) -> None:
    try:
        banner = page.locator(SEL.COOKIE_BANNER_ACCEPT)
        if banner.count() > 0:
            banner.first.click(timeout=3000)
    except Exception:
        pass


def _load_cards(page: Page, target_count: int) -> None:
    # previous_count comeca em -1 (nao 0): a Shopee ainda nao terminou de
    # hidratar os cards no momento do domcontentloaded, entao a 1a leitura
    # real costuma ser 0 - com sentinel 0 o loop bateria count==previous_count
    # de cara e sairia sem nunca dar tempo/scroll pra carregar os cards.
    previous_count = -1
    for _ in range(MAX_SCROLL_ITERATIONS):
        cards = page.locator(SEL.OFFER_CARD)
        count = cards.count()
        if count >= target_count or count == previous_count:
            break
        previous_count = count
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(int(random.uniform(800, 1500)))


def _parse_card_label(label: str) -> tuple[str, int, Decimal] | None:
    match = CARD_LABEL_PATTERN.search(label)
    if not match:
        return None
    price = parse_price(match.group("price"))
    if price is None:
        return None
    name = label[: match.start()].strip()
    name = NAME_TRIM_PATTERN.sub("", name).strip()
    if not name:
        return None
    return name, int(match.group("discount")), price


def list_offers(page: Page, settings: Settings) -> list[RawOfferCard]:
    page.goto(settings.shopee_offers_url, wait_until="domcontentloaded")
    # O banner/cabecalho da pagina renderiza rapido, mas o grid de produtos
    # e carregado por uma chamada assincrona separada com latencia bem
    # variavel entre execucoes reais (observado de ~1s a mais de 15s, sem
    # padrao claro - nao e bloqueio: URL/titulo continuam normais, so o
    # grid demora) - sem esperar o primeiro card aparecer, _load_cards ve
    # 0 cards e desiste cedo demais (calibrado em 2026-08-19 contra o site
    # real). Timeout generoso (30s) por causa dessa variabilidade.
    try:
        page.wait_for_selector(SEL.OFFER_CARD, timeout=30000, state="attached")
    except Exception:
        logger.warning("Nenhum card Shopee apareceu em 30s - pagina pode estar bloqueada/vazia/lenta")
    _dismiss_cookie_banner(page)
    _load_cards(page, settings.max_products_per_cycle)

    cards = page.locator(SEL.OFFER_CARD)
    count = cards.count()
    offers: list[RawOfferCard] = []

    for i in range(count):
        card = cards.nth(i)
        try:
            label = card.get_attribute("aria-label", timeout=2000)
            product_url = card.get_attribute("href", timeout=2000)
            if not label or not product_url:
                continue
            if product_url.startswith("/"):
                product_url = f"https://shopee.com.br{product_url}"

            parsed = _parse_card_label(label)
            if parsed is None:
                continue
            name, discount_percent, discount_price = parsed

            offers.append(
                RawOfferCard(
                    name=name,
                    product_url=product_url,
                    image_url=None,
                    original_price=None,
                    discount_price=discount_price,
                    discount_percent=discount_percent,
                )
            )
        except Exception:
            logger.debug("Falha ao extrair card Shopee %d, pulando", i, exc_info=True)
            continue

    return offers
