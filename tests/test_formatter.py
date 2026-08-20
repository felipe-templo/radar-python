import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.formatter import build_message, format_brl
from radar.models import Product


def make_product(**overrides) -> Product:
    defaults = dict(
        product_id="MLB123",
        name="Fone Bluetooth XYZ",
        product_url="https://produto.mercadolivre.com.br/MLB-123",
        image_url="https://example.com/img.jpg",
        original_price=Decimal("199.90"),
        discount_price=Decimal("149.90"),
        discount_percent=25,
        affiliate_link="https://mercadolivre.com/sec/abc123",
        collected_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    defaults.update(overrides)
    return Product(**defaults)


def test_format_brl():
    assert format_brl(Decimal("1234.5")) == "R$ 1.234,50"


def test_build_message_contains_key_fields():
    product = make_product()
    msg = build_message(product)
    assert product.name in msg
    assert "149,90" in msg
    assert "199,90" in msg
    assert "25% OFF" in msg
    assert product.affiliate_link in msg


def test_build_message_without_original_price():
    product = make_product(original_price=None)
    msg = build_message(product)
    assert "De:" not in msg


def test_build_message_shopee_source():
    product = make_product(source="shopee", product_id="18899837421")
    msg = build_message(product)
    assert "Shopee" in msg
    assert product.name in msg
