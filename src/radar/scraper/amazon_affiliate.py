import logging
import re

import pyperclip
from playwright.sync_api import BrowserContext

from radar.exceptions import AffiliateLinkNotFoundError
from radar.selectors import AmazonSiteStripeSelectors as SEL

logger = logging.getLogger(__name__)

# link.amazon/ e o dominio do link curto gerado pelo SiteStripe (confirmado
# em 2026-08-19 contra o DOM real, ver selectors.py) - amzn.to e o
# encurtador antigo, mantido no regex como fallback caso a Amazon volte a
# usa-lo. tag=/linkCode= sao os parametros de comissao de um link completo
# (variante "link completo" do popover, nao usada por padrao).
AFFILIATE_LINK_PATTERN = re.compile(r"(link\.amazon/|amzn\.to/|[?&]tag=|linkCode=)", re.IGNORECASE)


def _looks_like_affiliate_link(value: str | None) -> bool:
    return bool(value) and bool(AFFILIATE_LINK_PATTERN.search(value))


def get_affiliate_link(context: BrowserContext, product_url: str, timeout_ms: int = 15000) -> str:
    """Abre o produto numa nova aba e captura o link de afiliado via
    SiteStripe (Amazon Associates).

    Fluxo confirmado contra o DOM real: clicar em "Obter link"
    (`#amzn-ss-get-link-button`, fixo no topo da pagina) abre um popover
    com um botao "Copiar link de afiliado"
    (`#amzn-ss-copy-affiliate-link-btn`); ao clicar nele, o link e
    copiado direto pro clipboard - nao ha campo de texto visivel pra ler
    o valor (diferente de ML/Shopee), entao a unica camada real e
    clipboard (da pagina, com fallback pro clipboard do SO).
    """
    page = context.new_page()
    try:
        page.goto(product_url, wait_until="load", timeout=timeout_ms)
        page.wait_for_timeout(1000)

        get_link_button = page.locator(SEL.GET_LINK_BUTTON)
        if get_link_button.count() == 0:
            get_link_button = page.get_by_role("button", name=re.compile("obter link", re.I))
        if get_link_button.count() == 0:
            raise AffiliateLinkNotFoundError(product_url)
        get_link_button.first.scroll_into_view_if_needed()
        get_link_button.first.click(timeout=timeout_ms)

        copy_button = page.locator(SEL.COPY_LINK_BUTTON)
        try:
            copy_button.first.wait_for(state="visible", timeout=6000)
        except Exception:
            pass
        if copy_button.count() == 0:
            raise AffiliateLinkNotFoundError(product_url)
        copy_button.first.click(timeout=timeout_ms)
        page.wait_for_timeout(500)

        page.bring_to_front()
        try:
            clip_value = page.evaluate("navigator.clipboard.readText()")
        except Exception:
            clip_value = None
        if _looks_like_affiliate_link(clip_value):
            return clip_value

        # Ultimo recurso: clipboard do sistema operacional (exige janela
        # do Chrome visivel/nao minimizada).
        try:
            os_clip = pyperclip.paste()
        except Exception:
            os_clip = None
        if _looks_like_affiliate_link(os_clip):
            return os_clip

        raise AffiliateLinkNotFoundError(product_url)
    finally:
        page.close()
