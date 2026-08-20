import logging
import time

from radar.browser import connect_to_chrome
from radar.config import Settings
from radar.dedup import DedupRepository
from radar.exceptions import ChromeNotConnectableError
from radar.pipeline import discover_offers, process_queue
from radar.queue_repo import OfferQueue
from radar.sites import SiteConfig
from radar.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

MAX_RECONNECT_BEFORE_LONG_WAIT = 5
LONG_WAIT_SECONDS = 900


def run_all_sites(
    settings: Settings,
    context,
    dedup: DedupRepository,
    telegram: TelegramClient,
    queue: OfferQueue,
    sites: list[SiteConfig],
) -> None:
    """Roda um ciclo completo: descobre ofertas de cada site (isolado - erro
    num site nao impede os demais) e depois drena a fila compartilhada.

    A fila (ver radar.queue_repo) intercala itens entre sites, entao se o
    processamento de um site falhar/travar num item, o proximo item do
    lote ja e de outro site - nao precisa esperar o site com problema
    terminar nem tentar de novo antes de dar a vez ao outro.
    """
    sites_by_key = {site.key: site for site in sites}

    for site in sites:
        try:
            count = discover_offers(settings, context, site, queue, dedup)
            if count == 0:
                telegram.send_alert(
                    settings.telegram_admin_chat_id,
                    f"Radar {site.label}: 0 ofertas novas encontradas, verificar seletores em selectors.py",
                )
        except Exception:
            logger.exception("Erro ao descobrir ofertas de %s, demais sites continuam normalmente", site.label)
            telegram.send_alert(
                settings.telegram_admin_chat_id,
                f"Radar {site.label}: erro ao descobrir ofertas, verificar logs/radar.log. "
                "Outros sites nao foram afetados.",
            )

    batch_size = settings.max_products_per_cycle * max(len(sites), 1)
    try:
        processed = process_queue(settings, context, dedup, telegram, queue, sites_by_key, batch_size)
        logger.info("Ciclo concluido: %d produto(s) novo(s) postado(s)", processed)
    except Exception:
        # process_queue ja isola erro por item internamente - chegar aqui
        # significa falha fora do loop de itens (ex.: erro no proprio
        # SQLite da fila), no caso raro em que isso acontece nao vale a
        # pena isolar por site (a fila e compartilhada).
        logger.exception("Erro inesperado processando a fila")
        telegram.send_alert(
            settings.telegram_admin_chat_id,
            "Radar: erro inesperado processando a fila, verificar logs/radar.log",
        )


def run_forever(settings: Settings, sites: list[SiteConfig]) -> None:
    pw = browser = context = None
    reconnect_attempts = 0
    dedup = DedupRepository(settings.db_path)
    queue = OfferQueue(settings.db_path)
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)

    try:
        while True:
            try:
                if browser is None or not browser.is_connected():
                    if pw:
                        pw.stop()
                    pw, browser, context = connect_to_chrome(settings.chrome_debug_url)
                    reconnect_attempts = 0

                run_all_sites(settings, context, dedup, telegram, queue, sites)

            except ChromeNotConnectableError as exc:
                reconnect_attempts += 1
                logger.error("Chrome nao conectavel (tentativa %d): %s", reconnect_attempts, exc)
                browser = None
                if reconnect_attempts >= MAX_RECONNECT_BEFORE_LONG_WAIT:
                    telegram.send_alert(
                        settings.telegram_admin_chat_id,
                        f"Radar: Chrome inacessivel apos {reconnect_attempts} tentativas. "
                        "Verifique se ele esta aberto com --remote-debugging-port.",
                    )
                    time.sleep(LONG_WAIT_SECONDS)
                    continue
            except Exception:
                logger.exception("Erro inesperado no ciclo")
                telegram.send_alert(
                    settings.telegram_admin_chat_id,
                    "Radar: erro inesperado no ciclo, verificar logs/radar.log",
                )

            time.sleep(settings.check_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Encerrando por Ctrl+C")
    finally:
        if pw:
            pw.stop()
