import logging
import random
import time
from datetime import datetime

from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError

from radar.config import Settings
from radar.dedup import DedupRepository
from radar.exceptions import AffiliateLinkNotFoundError
from radar.formatter import build_message
from radar.models import Product
from radar.parsing import extract_product_id
from radar.scraper.offers_page import list_offers
from radar.scraper.product_page import get_affiliate_link
from radar.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


def run_cycle(
    settings: Settings,
    context: BrowserContext,
    dedup: DedupRepository,
    telegram: TelegramClient,
) -> None:
    # Aba de listagem e aberta e fechada a cada ciclo (nao reaproveitada
    # entre execucoes) para nao depender de uma aba sobreviver parada por
    # CHECK_INTERVAL_SECONDS - uma aba de longa duracao pode ser fechada
    # por fora (usuario, o proprio Chrome) e o bot nao teria como detectar
    # isso sem essa checagem.
    page = context.new_page()
    try:
        raw_offers = list_offers(page, settings)
    finally:
        page.close()
    logger.info("%d ofertas encontradas na pagina", len(raw_offers))

    if len(raw_offers) == 0:
        logger.warning("Nenhuma oferta extraida - possivel seletor quebrado ou bloqueio")
        telegram.send_alert(
            settings.telegram_admin_chat_id,
            "Radar ML: 0 ofertas extraidas, verificar seletores em selectors.py",
        )
        return

    processed = 0
    for raw in raw_offers:
        if processed >= settings.max_products_per_cycle:
            break

        try:
            product_id = extract_product_id(raw.product_url)
        except ValueError:
            continue

        if dedup.is_posted(product_id):
            continue

        if (raw.discount_percent or 0) < settings.min_discount_percent:
            continue

        try:
            affiliate_link = get_affiliate_link(context, raw.product_url)
        except AffiliateLinkNotFoundError:
            logger.error("Link de afiliado nao encontrado para %s", raw.product_url)
            continue
        except PlaywrightError:
            # Timeout de navegacao, pagina indisponivel, etc num produto
            # especifico nao pode derrubar o ciclo inteiro (os produtos
            # seguintes ainda tem chance de funcionar normalmente).
            logger.exception("Falha de navegacao ao buscar link de afiliado para %s", raw.product_url)
            continue

        product = Product(
            product_id=product_id,
            name=raw.name,
            product_url=raw.product_url,
            image_url=raw.image_url,
            original_price=raw.original_price,
            discount_price=raw.discount_price,
            discount_percent=raw.discount_percent or 0,
            affiliate_link=affiliate_link,
            collected_at=datetime.now(),
        )

        message = build_message(product)
        if settings.dry_run:
            logger.info("[DRY RUN] Mensagem que seria enviada:\n%s", message)
            dedup.mark_posted(product, telegram_message_id=None)
        else:
            result = telegram.send_offer(product, message)
            msg_id = result.get("result", {}).get("message_id")
            dedup.mark_posted(product, telegram_message_id=msg_id)

        processed += 1
        time.sleep(random.uniform(2, 5))

    logger.info("Ciclo concluido: %d produto(s) novo(s) postado(s)", processed)
