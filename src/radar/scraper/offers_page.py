import logging
import random

from playwright.sync_api import Page

from radar.config import Settings
from radar.models import RawOfferCard
from radar.parsing import compute_discount_percent, parse_discount, parse_price
from radar.selectors import OffersPageSelectors as SEL

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
    previous_count = 0
    for _ in range(MAX_SCROLL_ITERATIONS):
        cards = page.locator(SEL.OFFER_CARD)
        count = cards.count()
        if count >= target_count or count == previous_count:
            break
        previous_count = count
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(int(random.uniform(800, 1500)))


def list_offers(page: Page, settings: Settings) -> list[RawOfferCard]:
    page.goto(settings.offers_url, wait_until="domcontentloaded")
    _dismiss_cookie_banner(page)
    _load_cards(page, settings.max_products_per_cycle)

    cards = page.locator(SEL.OFFER_CARD)
    count = cards.count()
    offers: list[RawOfferCard] = []

    for i in range(count):
        card = cards.nth(i)
        try:
            name = card.locator(SEL.OFFER_TITLE).first.inner_text(timeout=2000).strip()
            product_url = card.locator(SEL.OFFER_LINK).first.get_attribute("href", timeout=2000)
            if not product_url:
                continue

            image_url = None
            img_loc = card.locator(SEL.OFFER_IMAGE).first
            if img_loc.count() > 0:
                image_url = img_loc.get_attribute("data-src") or img_loc.get_attribute("src")

            original_price = None
            orig_loc = card.locator(SEL.OFFER_PRICE_ORIGINAL).first
            if orig_loc.count() > 0:
                original_price = parse_price(orig_loc.inner_text(timeout=1500))

            discount_loc = card.locator(SEL.OFFER_PRICE_DISCOUNT).first
            if discount_loc.count() == 0:
                continue
            discount_price = parse_price(discount_loc.inner_text(timeout=1500))
            if discount_price is None:
                continue

            discount_percent = None
            badge_loc = card.locator(SEL.OFFER_DISCOUNT_BADGE).first
            if badge_loc.count() > 0:
                discount_percent = parse_discount(badge_loc.inner_text(timeout=1500))
            if discount_percent is None:
                discount_percent = compute_discount_percent(original_price, discount_price)

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
            logger.debug("Falha ao extrair card %d, pulando", i, exc_info=True)
            continue

    return offers
