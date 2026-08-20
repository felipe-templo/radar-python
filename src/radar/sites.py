from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import BrowserContext, Page

from radar.config import Settings
from radar.models import RawOfferCard
from radar.parsing import extract_product_id, extract_shopee_item_id
from radar.scraper.offers_page import list_offers as list_ml_offers
from radar.scraper.product_page import get_affiliate_link as get_ml_affiliate_link
from radar.scraper.shopee_affiliate import get_affiliate_link as get_shopee_affiliate_link
from radar.scraper.shopee_offers_page import list_offers as list_shopee_offers


@dataclass(frozen=True)
class SiteConfig:
    key: str
    label: str
    emoji: str
    list_offers: Callable[[Page, Settings], list[RawOfferCard]]
    get_affiliate_link: Callable[[BrowserContext, str], str]
    extract_product_id: Callable[[str], str]


ML_SITE = SiteConfig(
    key="ml",
    label="Mercado Livre",
    emoji="\U0001F6D2",
    list_offers=list_ml_offers,
    get_affiliate_link=get_ml_affiliate_link,
    extract_product_id=extract_product_id,
)

SHOPEE_SITE = SiteConfig(
    key="shopee",
    label="Shopee",
    emoji="\U0001F6CD",
    list_offers=list_shopee_offers,
    get_affiliate_link=get_shopee_affiliate_link,
    extract_product_id=extract_shopee_item_id,
)

ALL_SITES = [ML_SITE, SHOPEE_SITE]
SITES_BY_KEY = {site.key: site for site in ALL_SITES}
