import logging

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from radar.exceptions import ChromeNotConnectableError

logger = logging.getLogger(__name__)


def connect_to_chrome(cdp_url: str) -> tuple[Playwright, Browser, BrowserContext]:
    """Conecta a um Chrome ja em execucao via Chrome DevTools Protocol.

    O Chrome precisa ter sido iniciado manualmente com --remote-debugging-port
    e ja estar logado no Mercado Livre (ver README.md). Este script NUNCA abre
    nem loga um Chrome novo.
    """
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:
        pw.stop()
        raise ChromeNotConnectableError(
            f"Nao foi possivel conectar ao Chrome em {cdp_url}. "
            "Verifique se ele foi iniciado com --remote-debugging-port (ver README.md)."
        ) from exc

    if not browser.contexts:
        raise ChromeNotConnectableError("Chrome conectado, mas sem contexto/aba aberta.")

    context = browser.contexts[0]
    try:
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://www.mercadolivre.com.br",
        )
    except Exception:
        logger.warning("Nao foi possivel conceder permissao de clipboard; fallback via pyperclip")

    return pw, browser, context
