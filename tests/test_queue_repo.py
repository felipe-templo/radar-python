import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.models import RawOfferCard
from radar.queue_repo import MAX_ATTEMPTS, OfferQueue


def make_raw(name="Produto Teste", url="https://example.com/produto") -> RawOfferCard:
    return RawOfferCard(
        name=name,
        product_url=url,
        image_url=None,
        original_price=Decimal("100"),
        discount_price=Decimal("80"),
        discount_percent=20,
    )


def test_enqueue_and_next_batch_returns_item(tmp_path):
    queue = OfferQueue(str(tmp_path / "queue.db"))
    queue.enqueue("ml", "MLB123", make_raw())

    batch = queue.next_batch(10)

    assert len(batch) == 1
    assert batch[0].site_key == "ml"
    assert batch[0].product_id == "MLB123"


def test_enqueue_duplicate_is_ignored(tmp_path):
    queue = OfferQueue(str(tmp_path / "queue.db"))
    queue.enqueue("ml", "MLB123", make_raw())
    queue.enqueue("ml", "MLB123", make_raw())

    assert len(queue.next_batch(10)) == 1


def test_next_batch_interleaves_sites_round_robin(tmp_path):
    queue = OfferQueue(str(tmp_path / "queue.db"))
    queue.enqueue("ml", "MLB1", make_raw("ML 1"))
    queue.enqueue("ml", "MLB2", make_raw("ML 2"))
    queue.enqueue("shopee", "SHOPEE1", make_raw("Shopee 1"))
    queue.enqueue("shopee", "SHOPEE2", make_raw("Shopee 2"))

    batch = queue.next_batch(4)
    site_order = [item.site_key for item in batch]

    # Intercalado: nao pode ter os 2 itens do mesmo site seguidos no inicio
    assert site_order[0] != site_order[1]


def test_mark_done_removes_item_from_pending(tmp_path):
    queue = OfferQueue(str(tmp_path / "queue.db"))
    queue.enqueue("ml", "MLB123", make_raw())
    item = queue.next_batch(1)[0]

    queue.mark_done(item.id)

    assert queue.next_batch(10) == []


def test_mark_failed_keeps_item_pending_until_max_attempts(tmp_path):
    queue = OfferQueue(str(tmp_path / "queue.db"))
    queue.enqueue("ml", "MLB123", make_raw())

    for _ in range(MAX_ATTEMPTS - 1):
        item = queue.next_batch(1)[0]
        queue.mark_failed(item.id, "erro simulado")
        assert queue.next_batch(10) != []  # ainda pendente, tenta de novo

    item = queue.next_batch(1)[0]
    queue.mark_failed(item.id, "erro simulado final")

    assert queue.next_batch(10) == []  # esgotou tentativas, sai da fila
