from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class RawOfferCard:
    name: str
    product_url: str
    image_url: str | None
    original_price: Decimal | None
    discount_price: Decimal
    discount_percent: int | None


@dataclass
class Product:
    product_id: str
    name: str
    product_url: str
    image_url: str | None
    original_price: Decimal | None
    discount_price: Decimal
    discount_percent: int
    affiliate_link: str
    collected_at: datetime
    source: str = "ml"
