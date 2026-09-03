import logging
import random
import re

from playwright.sync_api import Locator, Page

from radar.bridge.normalize import RawContact

logger = logging.getLogger(__name__)

_ROW_SELECTOR = '[data-testid="cell-frame-container"]'
_MEMBERS_DIALOG_SELECTOR = 'div[role="dialog"][aria-label*="embros" i]'
_DRAWER_SELECTOR = '[data-testid="chat-info-drawer"]'
_PHONE_RE = re.compile(r"^\+?[\d\s()\-]{8,}$")
_SELF_LABELS = {"você", "voce", "you"}


def open_group_participants(page: Page, group_name: str) -> Locator:
    """Abre a conversa do grupo e retorna o container com a lista de participantes.

    Assume que o usuario ja abriu manualmente o web.whatsapp.com logado e que
    o grupo esta acessivel na lista de conversas. Nao tenta logar sozinho.
    """
    if page.locator(_DRAWER_SELECTOR).count() == 0:
        chat_title = page.locator('[data-testid="conversation-header"]').get_by_text(
            group_name, exact=False
        )
        chat_title.first.click()
        page.wait_for_timeout(500)
        page.locator('[data-testid="conversation-header"] [aria-label="Dados do perfil"]').first.click()
        page.wait_for_selector(_DRAWER_SELECTOR, timeout=10_000)

    ver_tudo = page.locator('div[role="button"]').filter(has_text="Ver tudo")
    if ver_tudo.count() > 0:
        ver_tudo.first.click()
        page.wait_for_selector(_MEMBERS_DIALOG_SELECTOR, timeout=10_000)
        return page.locator(_MEMBERS_DIALOG_SELECTOR).first

    return page.locator(_DRAWER_SELECTOR).first


def _find_scroller(container: Locator) -> object:
    return container.evaluate_handle(
        f"""el => {{
            const rows = el.querySelectorAll('{_ROW_SELECTOR}');
            let node = rows[0];
            while (node && node !== el) {{
                const style = getComputedStyle(node);
                if ((style.overflowY === 'auto' || style.overflowY === 'scroll')
                    && node.scrollHeight > node.clientHeight) {{
                    return node;
                }}
                node = node.parentElement;
            }}
            return null;
        }}"""
    )


def _parse_row(row: Locator, source_group: str) -> RawContact | None:
    title_locator = row.locator('[data-testid="cell-frame-title"] span[title]').first
    if title_locator.count() == 0:
        return None
    title_text = (title_locator.get_attribute("title") or "").strip()
    if not title_text or title_text.lower() in _SELF_LABELS:
        return None

    if _PHONE_RE.match(title_text):
        return RawContact(display_name=title_text, phone_raw=title_text, source_group=source_group)

    display_name = re.sub(r"^~\s*", "", title_text).strip()
    phone_raw = None
    secondary_phone = row.locator(
        '[data-testid="cell-frame-secondary"] [role="gridcell"][aria-colindex="1"] span'
    ).first
    if secondary_phone.count() > 0:
        text = secondary_phone.inner_text().strip()
        if _PHONE_RE.match(text):
            phone_raw = text

    return RawContact(display_name=display_name, phone_raw=phone_raw, source_group=source_group)


def extract_participants(
    page: Page,
    container: Locator,
    source_group: str,
    max_iterations: int = 400,
    stall_limit: int = 4,
    min_delay: float = 0.4,
    max_delay: float = 0.9,
) -> list[RawContact]:
    """Rola o painel de participantes e extrai nome/telefone visiveis.

    Dedupe interno por texto de titulo (nome ou telefone) para nao repetir
    contatos capturados em janelas de scroll sobrepostas. Dedupe final por
    telefone E.164 e responsabilidade de normalize.dedupe_contacts.
    """
    rows = container.locator(_ROW_SELECTOR)
    scroller = _find_scroller(container)

    seen_titles: set[str] = set()
    contacts: list[RawContact] = []
    stalled_iterations = 0

    for _ in range(max_iterations):
        new_in_this_pass = 0
        for i in range(rows.count()):
            row = rows.nth(i)
            try:
                title_locator = row.locator('[data-testid="cell-frame-title"] span[title]').first
                if title_locator.count() == 0:
                    continue
                title_text = (title_locator.get_attribute("title") or "").strip()
                if not title_text or title_text in seen_titles:
                    continue
                seen_titles.add(title_text)
                contact = _parse_row(row, source_group)
                if contact is not None:
                    contacts.append(contact)
                    new_in_this_pass += 1
            except Exception:
                logger.warning("Falha ao extrair participante na linha %d, pulando.", i, exc_info=True)

        stalled_iterations = stalled_iterations + 1 if new_in_this_pass == 0 else 0
        if stalled_iterations >= stall_limit:
            break

        at_bottom = scroller.evaluate(
            "el => el ? (el.scrollTop + el.clientHeight >= el.scrollHeight - 2) : true"
        )
        if at_bottom:
            break

        scroller.evaluate("el => el.scrollBy(0, 550)")
        page.wait_for_timeout(int(random.uniform(min_delay, max_delay) * 1000))

    logger.info("Extraidos %d participantes do grupo '%s'.", len(contacts), source_group)
    return contacts
