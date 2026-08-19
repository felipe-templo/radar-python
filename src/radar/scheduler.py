import logging
import time

from radar.browser import connect_to_chrome
from radar.config import Settings
from radar.dedup import DedupRepository
from radar.exceptions import ChromeNotConnectableError
from radar.pipeline import run_cycle
from radar.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

MAX_RECONNECT_BEFORE_LONG_WAIT = 5
LONG_WAIT_SECONDS = 900


def run_forever(settings: Settings) -> None:
    pw = browser = context = None
    reconnect_attempts = 0
    dedup = DedupRepository(settings.db_path)
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)

    try:
        while True:
            try:
                if browser is None or not browser.is_connected():
                    if pw:
                        pw.stop()
                    pw, browser, context = connect_to_chrome(settings.chrome_debug_url)
                    reconnect_attempts = 0

                run_cycle(settings, context, dedup, telegram)

            except ChromeNotConnectableError as exc:
                reconnect_attempts += 1
                logger.error("Chrome nao conectavel (tentativa %d): %s", reconnect_attempts, exc)
                browser = None
                if reconnect_attempts >= MAX_RECONNECT_BEFORE_LONG_WAIT:
                    telegram.send_alert(
                        settings.telegram_admin_chat_id,
                        f"Radar ML: Chrome inacessivel apos {reconnect_attempts} tentativas. "
                        "Verifique se ele esta aberto com --remote-debugging-port.",
                    )
                    time.sleep(LONG_WAIT_SECONDS)
                    continue
            except Exception:
                logger.exception("Erro inesperado no ciclo")
                telegram.send_alert(
                    settings.telegram_admin_chat_id,
                    "Radar ML: erro inesperado no ciclo, verificar logs/radar.log",
                )

            time.sleep(settings.check_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Encerrando por Ctrl+C")
    finally:
        if pw:
            pw.stop()
