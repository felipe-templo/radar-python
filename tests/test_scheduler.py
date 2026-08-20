import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from radar.scheduler import run_all_sites
from radar.sites import SiteConfig


def make_site(key: str) -> SiteConfig:
    return SiteConfig(
        key=key,
        label=key.upper(),
        emoji="X",
        list_offers=lambda page, settings: [],
        get_affiliate_link=lambda context, url: "",
        extract_product_id=lambda url: url,
    )


def test_ml_discovery_failure_does_not_prevent_shopee_discovery(mocker):
    calls = []

    def fake_discover(settings, context, site, queue, dedup):
        calls.append(site.key)
        if site.key == "ml":
            raise RuntimeError("ML quebrou na descoberta")
        return 1

    mocker.patch("radar.scheduler.discover_offers", side_effect=fake_discover)
    mocker.patch("radar.scheduler.process_queue", return_value=0)

    settings = mocker.Mock(telegram_admin_chat_id=None, max_products_per_cycle=15)
    telegram = mocker.Mock()
    sites = [make_site("ml"), make_site("shopee")]

    run_all_sites(settings, context=None, dedup=None, telegram=telegram, queue=None, sites=sites)

    assert calls == ["ml", "shopee"]


def test_shopee_discovery_failure_does_not_prevent_ml_discovery(mocker):
    calls = []

    def fake_discover(settings, context, site, queue, dedup):
        calls.append(site.key)
        if site.key == "shopee":
            raise RuntimeError("Shopee quebrou na descoberta")
        return 1

    mocker.patch("radar.scheduler.discover_offers", side_effect=fake_discover)
    mocker.patch("radar.scheduler.process_queue", return_value=0)

    settings = mocker.Mock(telegram_admin_chat_id=None, max_products_per_cycle=15)
    telegram = mocker.Mock()
    sites = [make_site("ml"), make_site("shopee")]

    run_all_sites(settings, context=None, dedup=None, telegram=telegram, queue=None, sites=sites)

    assert calls == ["ml", "shopee"]


def test_discovery_failure_sends_alert_naming_the_failing_site(mocker):
    def fake_discover(settings, context, site, queue, dedup):
        if site.key == "ml":
            raise RuntimeError("ML quebrou")
        return 1

    mocker.patch("radar.scheduler.discover_offers", side_effect=fake_discover)
    mocker.patch("radar.scheduler.process_queue", return_value=0)

    settings = mocker.Mock(telegram_admin_chat_id="admin123", max_products_per_cycle=15)
    telegram = mocker.Mock()
    sites = [make_site("ml"), make_site("shopee")]

    run_all_sites(settings, context=None, dedup=None, telegram=telegram, queue=None, sites=sites)

    alert_messages = [call.args[1] for call in telegram.send_alert.call_args_list]
    assert any("ML" in msg for msg in alert_messages)


def test_process_queue_batch_size_scales_with_number_of_sites(mocker):
    mocker.patch("radar.scheduler.discover_offers", return_value=1)
    process_queue_mock = mocker.patch("radar.scheduler.process_queue", return_value=0)

    settings = mocker.Mock(telegram_admin_chat_id=None, max_products_per_cycle=15)
    telegram = mocker.Mock()
    sites = [make_site("ml"), make_site("shopee")]

    run_all_sites(settings, context=None, dedup=None, telegram=telegram, queue=None, sites=sites)

    batch_size = process_queue_mock.call_args.args[-1]
    assert batch_size == 15 * 2
