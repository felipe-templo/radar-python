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
from radar.queue_repo import OfferQueue
from radar.sites import SiteConfig
from radar.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


def discover_offers(
    settings: Settings,
    context: BrowserContext,
    site: SiteConfig,
    queue: OfferQueue,
    dedup: DedupRepository,
) -> int:
    """Le a pagina de ofertas do site e enfileira as novas (rapido - so
    parsing de DOM, nao abre pagina de produto nenhuma). Nao ha limite de
    quantas ofertas sao enfileiradas aqui (diferente de antes) - quem
    limita ritmo de processamento e process_queue, via batch_size."""
    # Aba de listagem e aberta e fechada a cada ciclo (nao reaproveitada
    # entre execucoes) para nao depender de uma aba sobreviver parada por
    # CHECK_INTERVAL_SECONDS - uma aba de longa duracao pode ser fechada
    # por fora (usuario, o proprio Chrome) e o bot nao teria como detectar
    # isso sem essa checagem.
    page = context.new_page()
    try:
        raw_offers = site.list_offers(page, settings)
    finally:
        page.close()
    logger.info("%d ofertas encontradas na pagina (%s)", len(raw_offers), site.label)

    if len(raw_offers) == 0:
        logger.warning("Nenhuma oferta extraida (%s) - possivel seletor quebrado ou bloqueio", site.label)
        return 0

    enqueued = 0
    for raw in raw_offers:
        try:
            product_id = site.extract_product_id(raw.product_url)
        except ValueError:
            continue

        if (raw.discount_percent or 0) < settings.min_discount_percent:
            continue

        if dedup.is_posted(f"{site.key}:{product_id}"):
            continue

        queue.enqueue(site.key, product_id, raw)
        enqueued += 1

    logger.info("%d oferta(s) nova(s) enfileirada(s) (%s)", enqueued, site.label)
    return enqueued


def process_queue(
    settings: Settings,
    context: BrowserContext,
    dedup: DedupRepository,
    telegram: TelegramClient,
    queue: OfferQueue,
    sites_by_key: dict[str, SiteConfig],
    batch_size: int,
) -> int:
    """Drena ate batch_size itens da fila, intercalados entre sites (ver
    OfferQueue.next_batch). Erro num item so afeta aquele item - o loop
    sempre segue pro proximo, que na pratica costuma ser de outro site
    (por causa do intercalamento round-robin), entao um site com problema
    nunca bloqueia o outro dentro do mesmo lote."""
    batch = queue.next_batch(batch_size)
    processed = 0

    for item in batch:
        site = sites_by_key.get(item.site_key)
        if site is None:
            queue.mark_done(item.id)
            continue

        dedup_key = f"{item.site_key}:{item.product_id}"
        if dedup.is_posted(dedup_key):
            queue.mark_done(item.id)
            continue

        try:
            affiliate_link = site.get_affiliate_link(context, item.product_url)
        except AffiliateLinkNotFoundError:
            logger.error("Link de afiliado nao encontrado para %s", item.product_url)
            queue.mark_failed(item.id, "link de afiliado nao encontrado")
            continue
        except PlaywrightError as exc:
            # Timeout de navegacao, pagina indisponivel, etc num item
            # especifico nao pode derrubar o lote inteiro (os itens
            # seguintes, de qualquer site, ainda tem chance de funcionar).
            logger.exception("Falha de navegacao ao buscar link de afiliado para %s", item.product_url)
            queue.mark_failed(item.id, f"falha de navegacao: {exc}")
            continue
        except Exception as exc:
            logger.exception("Erro inesperado processando item da fila (%s)", item.product_url)
            queue.mark_failed(item.id, str(exc))
            continue

        product = Product(
            product_id=item.product_id,
            name=item.name,
            product_url=item.product_url,
            image_url=item.image_url,
            original_price=item.original_price,
            discount_price=item.discount_price,
            discount_percent=item.discount_percent,
            affiliate_link=affiliate_link,
            collected_at=datetime.now(),
            source=item.site_key,
        )

        message = build_message(product)
        if settings.dry_run:
            logger.info("[DRY RUN] Mensagem que seria enviada:\n%s", message)
            dedup.mark_posted(product, dedup_key=dedup_key, telegram_message_id=None)
        else:
            result = telegram.send_offer(product, message)
            msg_id = result.get("result", {}).get("message_id")
            dedup.mark_posted(product, dedup_key=dedup_key, telegram_message_id=msg_id)

        queue.mark_done(item.id)
        processed += 1
        time.sleep(random.uniform(2, 5))

    return processed
