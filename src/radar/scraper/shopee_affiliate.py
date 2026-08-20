import logging
import re

import pyperclip
from playwright.sync_api import BrowserContext

from radar.exceptions import AffiliateLinkNotFoundError
from radar.parsing import extract_shopee_item_id
from radar.selectors import ShopeeAffiliatePortalSelectors as SEL

logger = logging.getLogger(__name__)

AFFILIATE_PORTAL_URL = "https://affiliate.shopee.com.br/offer/product_offer/{item_id}"

AFFILIATE_LINK_PATTERN = re.compile(
    r"(s\.shopee|shope\.ee|affiliate\.shopee|smtt=|utm_campaign=)", re.IGNORECASE
)


def _looks_like_affiliate_link(value: str | None) -> bool:
    return bool(value) and bool(AFFILIATE_LINK_PATTERN.search(value))


def get_affiliate_link(context: BrowserContext, product_url: str, timeout_ms: int = 15000) -> str:
    """Abre o produto no portal de afiliados Shopee e captura o link gerado.

    Diferente do Mercado Livre, a resolucao de afiliado da Shopee nao
    acontece na propria pagina do produto: acontece no portal
    affiliate.shopee.com.br/offer/product_offer/{item_id}, clicando no
    botao "Obter link". Nao ha confirmacao de onde exatamente o link
    aparece apos o clique (modal com campo de texto vs. clipboard direto),
    entao tenta-se em camadas, igual ao product_page.py do ML.
    """
    item_id = extract_shopee_item_id(product_url)
    portal_url = AFFILIATE_PORTAL_URL.format(item_id=item_id)

    page = context.new_page()
    try:
        page.goto(portal_url, wait_until="load", timeout=timeout_ms)
        page.wait_for_timeout(1000)

        get_link_button = page.locator(SEL.GET_LINK_BUTTON)
        if get_link_button.count() == 0:
            raise AffiliateLinkNotFoundError(product_url)
        get_link_button.first.scroll_into_view_if_needed()
        get_link_button.first.click(timeout=timeout_ms)

        combined_selector = f"{SEL.LINK_MODAL_INPUT}, {SEL.COPY_LINK_ANCHOR}"
        try:
            page.wait_for_selector(combined_selector, timeout=6000, state="attached")
        except Exception:
            pass

        # Camada 1: campo de texto com o link pronto
        link_input = page.locator(SEL.LINK_MODAL_INPUT)
        if link_input.count() > 0:
            value = link_input.first.input_value(timeout=5000)
            if _looks_like_affiliate_link(value):
                return value

        # Camada 2: href de um link "Copiar link"
        copy_link_anchor = page.locator(SEL.COPY_LINK_ANCHOR)
        if copy_link_anchor.count() > 0:
            href = copy_link_anchor.first.get_attribute("href", timeout=3000)
            if _looks_like_affiliate_link(href):
                return href

        # Camada 3 (ultimo recurso): clicar 'Copiar' e ler clipboard da pagina
        copy_button = page.locator(SEL.LINK_COPY_BUTTON)
        if copy_button.count() > 0:
            copy_button.first.click(timeout=3000)
            page.wait_for_timeout(500)
            page.bring_to_front()
            try:
                clip_value = page.evaluate("navigator.clipboard.readText()")
            except Exception:
                clip_value = None
            if _looks_like_affiliate_link(clip_value):
                return clip_value

        # Camada 4 (ultimo recurso): clipboard do sistema operacional
        try:
            os_clip = pyperclip.paste()
        except Exception:
            os_clip = None
        if _looks_like_affiliate_link(os_clip):
            return os_clip

        raise AffiliateLinkNotFoundError(product_url)
    finally:
        page.close()
