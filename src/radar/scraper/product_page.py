import logging
import re

import pyperclip
from playwright.sync_api import BrowserContext

from radar.exceptions import AffiliateLinkNotFoundError
from radar.selectors import ProductPageSelectors as SEL

logger = logging.getLogger(__name__)

AFFILIATE_LINK_PATTERN = re.compile(
    r"(meli\.la/|mercadolivre\.com(\.br)?/sec/|matt_word=|matt_tool=)", re.IGNORECASE
)


def _looks_like_affiliate_link(value: str | None) -> bool:
    return bool(value) and bool(AFFILIATE_LINK_PATTERN.search(value))


def get_affiliate_link(context: BrowserContext, product_url: str, timeout_ms: int = 15000) -> str:
    """Abre o produto numa nova aba, clica em Compartilhar e captura o link de afiliado.

    O popup de compartilhamento do ML tem duas variantes (ver selectors.py):
    produtos em campanha "oferta" mostram um gerador de link com <textarea>;
    produtos normais mostram um menu social cujo item "Copiar link" ja tem
    o href com os parametros de afiliado (matt_tool=) embutidos. Le-se o
    href diretamente do DOM nesse caso - mais confiavel que depender de
    clipboard, que pode reter valor antigo de uma iteracao anterior.

    Camada 3 (clipboard do SO) e mantida apenas como ultimo recurso, caso
    nenhuma das duas variantes conhecidas seja encontrada.
    """
    page = context.new_page()
    try:
        # wait_until="load" (nao "domcontentloaded") e importante: o botao
        # Compartilhar so responde ao clique depois que o React hidrata a
        # pagina. Com domcontentloaded o clique acontece cedo demais e o
        # popup as vezes nao abre (ou abre com estado desatualizado).
        page.goto(product_url, wait_until="load", timeout=timeout_ms)
        page.wait_for_timeout(1000)

        share_button = page.get_by_role("button", name=re.compile("ompartilhar", re.I))
        if share_button.count() == 0:
            share_button = page.locator(SEL.SHARE_BUTTON)
        if share_button.count() == 0:
            raise AffiliateLinkNotFoundError(product_url)
        share_button.first.scroll_into_view_if_needed()
        share_button.first.click(timeout=timeout_ms)

        # Espera diretamente por um dos dois elementos conhecidos aparecer,
        # em vez de sleep fixo ou de detectar '[data-tippy-root]' generico
        # (a pagina pode ter outros tooltips/popups nao relacionados soltos
        # no DOM, o que gerava falsos negativos).
        combined_selector = f"{SEL.SHARE_MODAL_LINK_INPUT}, {SEL.COPY_LINK_ANCHOR}"
        try:
            page.wait_for_selector(combined_selector, timeout=6000, state="attached")
        except Exception:
            pass

        # Camada 1: gerador de link de afiliado (formato mais comum, meli.la)
        link_input = page.locator(SEL.SHARE_MODAL_LINK_INPUT)
        if link_input.count() > 0:
            value = link_input.first.input_value(timeout=5000)
            if _looks_like_affiliate_link(value):
                return value

        # Camada 2: href do item "Copiar link" do popup social padrao
        copy_link_anchor = page.locator(SEL.COPY_LINK_ANCHOR)
        if copy_link_anchor.count() > 0:
            href = copy_link_anchor.first.get_attribute("href", timeout=3000)
            if _looks_like_affiliate_link(href):
                return href

        # Camada 3 (ultimo recurso): clicar 'Copiar' e ler clipboard
        copy_button = page.locator(SEL.SHARE_MODAL_COPY_BUTTON)
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

        try:
            os_clip = pyperclip.paste()
        except Exception:
            os_clip = None
        if _looks_like_affiliate_link(os_clip):
            return os_clip

        raise AffiliateLinkNotFoundError(product_url)
    finally:
        page.close()
