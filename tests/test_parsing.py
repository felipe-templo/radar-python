import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.parsing import compute_discount_percent, extract_product_id, parse_discount, parse_price


def test_parse_price_simple():
    assert parse_price("R$ 1.234,56") == Decimal("1234.56")


def test_parse_price_no_thousands():
    assert parse_price("R$ 99,90") == Decimal("99.90")


def test_parse_price_invalid_returns_none():
    assert parse_price("indisponivel") is None


def test_parse_price_empty_returns_none():
    assert parse_price("") is None


def test_parse_discount_found():
    assert parse_discount("-23% OFF") == 23


def test_parse_discount_not_found():
    assert parse_discount("sem desconto") is None


def test_compute_discount_percent():
    assert compute_discount_percent(Decimal("100"), Decimal("77")) == 23


def test_compute_discount_percent_no_original():
    assert compute_discount_percent(None, Decimal("77")) is None


def test_extract_product_id():
    assert extract_product_id("https://produto.mercadolivre.com.br/MLB-1234567890-item") == "MLB1234567890"


def test_extract_product_id_invalid():
    try:
        extract_product_id("https://example.com/nope")
        assert False, "deveria ter lancado ValueError"
    except ValueError:
        pass
