import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.dedup import DedupRepository
from radar.models import Product


def make_product(product_id="MLB123") -> Product:
    return Product(
        product_id=product_id,
        name="Produto Teste",
        product_url="https://produto.mercadolivre.com.br/MLB-123",
        image_url=None,
        original_price=Decimal("100"),
        discount_price=Decimal("80"),
        discount_percent=20,
        affiliate_link="https://mercadolivre.com/sec/abc",
        collected_at=datetime(2026, 1, 1),
    )


def test_is_posted_false_for_new_product(tmp_path):
    repo = DedupRepository(str(tmp_path / "test.db"))
    assert repo.is_posted("MLB999") is False


def test_mark_posted_then_is_posted_true(tmp_path):
    repo = DedupRepository(str(tmp_path / "test.db"))
    product = make_product()
    repo.mark_posted(product, telegram_message_id=42)
    assert repo.is_posted(product.product_id) is True


def test_mark_posted_is_idempotent(tmp_path):
    repo = DedupRepository(str(tmp_path / "test.db"))
    product = make_product()
    repo.mark_posted(product, telegram_message_id=1)
    repo.mark_posted(product, telegram_message_id=2)
    assert repo.is_posted(product.product_id) is True
