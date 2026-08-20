import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.dedup import DedupRepository
from radar.models import RawOfferCard
from radar.pipeline import process_queue
from radar.queue_repo import OfferQueue
from radar.sites import SiteConfig


def make_raw(name="Produto Teste") -> RawOfferCard:
    return RawOfferCard(
        name=name,
        product_url="https://example.com/produto",
        image_url=None,
        original_price=Decimal("100"),
        discount_price=Decimal("80"),
        discount_percent=20,
    )


def make_site(key: str, get_affiliate_link) -> SiteConfig:
    return SiteConfig(
        key=key,
        label=key.upper(),
        emoji="X",
        list_offers=lambda page, settings: [],
        get_affiliate_link=get_affiliate_link,
        extract_product_id=lambda url: url,
    )


def test_item_failure_on_one_site_does_not_block_other_site_item(tmp_path, mocker):
    """Nucleo do requisito: fila intercalada entre sites, entao se um item
    de um site falha, o proximo item do lote (de outro site) ainda e
    processado normalmente no mesmo lote - nao espera nem bloqueia."""
    queue = OfferQueue(str(tmp_path / "queue.db"))
    dedup = DedupRepository(str(tmp_path / "dedup.db"))
    queue.enqueue("ml", "MLB1", make_raw("Produto ML"))
    queue.enqueue("shopee", "SHOPEE1", make_raw("Produto Shopee"))

    def ml_fails(context, url):
        raise RuntimeError("ML caiu")

    def shopee_succeeds(context, url):
        return "https://s.shopee.com.br/abc123"

    sites_by_key = {
        "ml": make_site("ml", ml_fails),
        "shopee": make_site("shopee", shopee_succeeds),
    }

    settings = mocker.Mock(dry_run=True)
    telegram = mocker.Mock()

    processed = process_queue(settings, context=None, dedup=dedup, telegram=telegram,
                               queue=queue, sites_by_key=sites_by_key, batch_size=10)

    assert processed == 1
    assert dedup.is_posted("shopee:SHOPEE1") is True
    assert dedup.is_posted("ml:MLB1") is False

    remaining = queue.next_batch(10)
    assert len(remaining) == 1
    assert remaining[0].site_key == "ml"
    assert remaining[0].attempts == 1


def test_all_items_succeed_when_no_failures(tmp_path, mocker):
    queue = OfferQueue(str(tmp_path / "queue.db"))
    dedup = DedupRepository(str(tmp_path / "dedup.db"))
    queue.enqueue("ml", "MLB1", make_raw("Produto ML"))
    queue.enqueue("shopee", "SHOPEE1", make_raw("Produto Shopee"))

    sites_by_key = {
        "ml": make_site("ml", lambda context, url: "https://mercadolivre.com/sec/abc"),
        "shopee": make_site("shopee", lambda context, url: "https://s.shopee.com.br/abc"),
    }

    settings = mocker.Mock(dry_run=True)
    telegram = mocker.Mock()

    processed = process_queue(settings, context=None, dedup=dedup, telegram=telegram,
                               queue=queue, sites_by_key=sites_by_key, batch_size=10)

    assert processed == 2
    assert queue.next_batch(10) == []
