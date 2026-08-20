import logging
import random

from playwright.sync_api import Page

from radar.config import Settings
from radar.models import RawOfferCard
from radar.parsing import compute_discount_percent, extract_amazon_asin, parse_discount, parse_price
from radar.selectors import AmazonOffersPageSelectors as SEL

logger = logging.getLogger(__name__)

MAX_SCROLL_ITERATIONS = 20


def _dismiss_cookie_banner(page: Page) -> None:
    try:
        banner = page.locator(SEL.COOKIE_BANNER_ACCEPT)
        if banner.count() > 0:
            banner.first.click(timeout=3000)
    except Exception:
        pass


def _load_cards(page: Page, target_count: int) -> None:
    # Grid da Amazon e virtualizado (so um punhado de cards fica no DOM
    # por vez, o resto e montado/desmontado conforme rola) - mesmo motivo
    # do sentinel -1 usado na Shopee: a 1a leitura real pode ser 0 antes
    # do grid hidratar.
    previous_count = -1
    for _ in range(MAX_SCROLL_ITERATIONS):
        cards = page.locator(SEL.OFFER_CARD)
        count = cards.count()
        if count >= target_count or count == previous_count:
            break
        previous_count = count
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(int(random.uniform(800, 1500)))


def list_offers(page: Page, settings: Settings) -> list[RawOfferCard]:
    page.goto(settings.amazon_offers_url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(SEL.OFFER_CARD, timeout=30000, state="attached")
    except Exception:
        logger.warning("Nenhum card Amazon apareceu em 30s - pagina pode estar bloqueada/vazia/lenta")
    _dismiss_cookie_banner(page)
    _load_cards(page, settings.max_products_per_cycle)

    cards = page.locator(SEL.OFFER_CARD)
    count = cards.count()
    offers: list[RawOfferCard] = []
    # O grid e virtualizado (cards saem/entram do DOM ao rolar), entao o
    # mesmo produto pode aparecer mais de uma vez entre leituras - dedupe
    # por ASIN.
    seen_asins: set[str] = set()

    for i in range(count):
        card = cards.nth(i)
        try:
            asin = card.get_attribute("data-asin", timeout=1500)
            link = card.locator(SEL.OFFER_LINK).first
            if link.count() == 0:
                continue
            product_url = link.get_attribute("href", timeout=2000)
            if not product_url:
                continue

            if not asin:
                try:
                    asin = extract_amazon_asin(product_url)
                except ValueError:
                    continue
            if asin in seen_asins:
                continue

            title_loc = card.locator(SEL.OFFER_TITLE).first
            name = title_loc.inner_text(timeout=1500).strip() if title_loc.count() > 0 else None
            if not name:
                continue

            image_url = None
            img_loc = card.locator(SEL.OFFER_IMAGE).first
            if img_loc.count() > 0:
                image_url = img_loc.get_attribute("src", timeout=1500)

            discount_loc = card.locator(SEL.OFFER_PRICE_DISCOUNT).first
            if discount_loc.count() == 0:
                continue
            discount_price = parse_price(discount_loc.inner_text(timeout=1500))
            if discount_price is None:
                continue

            original_price = None
            orig_loc = card.locator(SEL.OFFER_PRICE_ORIGINAL).first
            if orig_loc.count() > 0:
                original_price = parse_price(orig_loc.inner_text(timeout=1500))

            discount_percent = None
            badge_loc = card.locator(SEL.OFFER_DISCOUNT_BADGE).first
            if badge_loc.count() > 0:
                discount_percent = parse_discount(badge_loc.inner_text(timeout=1500))
            if discount_percent is None:
                discount_percent = compute_discount_percent(original_price, discount_price)

            seen_asins.add(asin)
            offers.append(
                RawOfferCard(
                    name=name,
                    product_url=product_url,
                    image_url=image_url,
                    original_price=original_price,
                    discount_price=discount_price,
                    discount_percent=discount_percent,
                )
            )
        except Exception:
            logger.debug("Falha ao extrair card Amazon %d, pulando", i, exc_info=True)
            continue

    return offers
