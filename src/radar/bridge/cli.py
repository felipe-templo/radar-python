import asyncio
import csv
import logging
import os
from datetime import datetime

from telethon import TelegramClient

from radar.browser import connect_to_chrome
from radar.bridge.config import BridgeSettings, load_bridge_settings
from radar.bridge.normalize import dedupe_contacts
from radar.bridge.repository import BridgeRepository
from radar.bridge.telegram_inviter import PeerFloodStop, run_add_batch
from radar.bridge.telegram_resolver import TelegramResolver
from radar.bridge.whatsapp_scraper import extract_participants
from radar.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [s/N]: ").strip().lower()
    return answer in {"s", "sim", "y", "yes"}


def extract_from_whatsapp(settings: BridgeSettings) -> tuple[str, list]:
    """Extrai participantes do grupo atualmente aberto no WhatsApp Web.

    Requer que o usuario ja tenha aberto o grupo e o painel de participantes
    (Dados do grupo -> Ver tudo). Nao faz login nem navega sozinho.
    """
    pw, _browser, context = connect_to_chrome(settings.chrome_debug_url)
    try:
        pages = [p for p in context.pages if "web.whatsapp.com" in p.url]
        if not pages:
            raise RuntimeError(
                "Nenhuma aba com web.whatsapp.com aberta. Abra o WhatsApp Web logado "
                "no Chrome com debug port antes de rodar."
            )
        page = pages[0]

        drawer = page.locator('[data-testid="chat-info-drawer"]')
        if drawer.count() == 0:
            raise RuntimeError(
                "Painel de dados do grupo nao esta aberto. Clique no nome do grupo "
                "no topo da conversa antes de rodar."
            )
        lines = [l for l in drawer.first.evaluate("el => el.innerText").split("\n") if l.strip()]
        group_name = lines[1] if len(lines) > 1 else "Grupo desconhecido"

        container = page.locator('div[role="dialog"][aria-label*="embros" i]')
        container = container.first if container.count() > 0 else drawer.first

        raw_contacts = extract_participants(page, container, source_group=group_name)
        return group_name, raw_contacts
    finally:
        pw.stop()


async def _resolve(settings: BridgeSettings, repo: BridgeRepository, pending: list[tuple[int, str]]) -> int:
    client = TelegramClient(
        settings.telethon_session_path, settings.telegram_api_id, settings.telegram_api_hash
    )
    await client.start()
    try:
        resolver = TelegramResolver(client)
        resolved = await resolver.resolve_batch([phone for _, phone in pending])
    finally:
        await client.disconnect()

    found = 0
    for contact_id, phone in pending:
        match = resolved.get(phone)
        if match is None:
            repo.record_resolution(contact_id, resolved=False)
            continue
        user_id, username = match
        repo.record_resolution(
            contact_id, resolved=True, telegram_user_id=user_id, telegram_username=username
        )
        found += 1
    return found


async def _add(settings: BridgeSettings, repo: BridgeRepository, candidates: list[tuple[int, int]]) -> None:
    client = TelegramClient(
        settings.telethon_session_path, settings.telegram_api_id, settings.telegram_api_hash
    )
    await client.start()
    try:
        target = await client.get_entity(int(settings.telegram_target_group_id))
        title = getattr(target, "title", settings.telegram_target_group_id)
        print(f"Grupo alvo no Telegram: {title}")
        await run_add_batch(client, repo, settings, target, candidates)
    except PeerFloodStop:
        print(
            "\nPARADO: o Telegram sinalizou a conta por comportamento tipo spam (PeerFloodError).\n"
            "Nao retente automaticamente. Espere varios dias antes de tentar de novo."
        )
    finally:
        await client.disconnect()


def _resolved_candidates(repo: BridgeRepository) -> list[tuple[int, int, str | None, str | None]]:
    """Retorna (contact_id, telegram_user_id, username, phone) de quem esta resolvido e ainda nao adicionado."""
    candidates = []
    for row in repo.contacts_by_status("resolved"):
        with repo._connect() as conn:
            match = conn.execute(
                "SELECT telegram_user_id, telegram_username FROM telegram_resolutions "
                "WHERE contact_id = ? AND resolved = 1",
                (row["id"],),
            ).fetchone()
        if match:
            candidates.append((row["id"], match[0], match[1], row["phone_e164"]))
    return candidates


def _export_csv(repo: BridgeRepository) -> str:
    os.makedirs("data/exports", exist_ok=True)
    path = f"data/exports/bridge-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    rows = repo.report_rows()
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["telefone", "nome", "grupo_origem", "status", "telegram_username", "resolvido", "adicionado", "motivo_falha", "tentado_em"]
        )
        for row in rows:
            writer.writerow([row[k] for k in row.keys()])
    return path


def run() -> None:
    settings = load_bridge_settings()
    setup_logging(settings.log_level, log_path="logs/bridge.log")
    repo = BridgeRepository(settings.db_path)

    print("=== Ponte WhatsApp -> Telegram ===")
    if settings.dry_run:
        print("MODO DRY RUN ativo (BRIDGE_DRY_RUN=true): nenhuma adicao real sera feita.\n")

    # 1. Extracao
    group_name, raw_contacts = extract_from_whatsapp(settings)
    normalized = dedupe_contacts(raw_contacts)
    with_phone = [c for c in normalized if c.phone_e164]
    print(f"\nGrupo: {group_name}")
    print(f"Participantes capturados: {len(raw_contacts)}")
    print(f"Apos deduplicacao: {len(normalized)}")
    print(f"Com telefone valido: {len(with_phone)}")
    print(f"Sem telefone utilizavel: {len(normalized) - len(with_phone)}")

    pending: list[tuple[int, str]] = []
    for contact in with_phone:
        contact_id = repo.upsert_contact(contact.phone_e164, contact.display_name, contact.source_group)
        if repo.contact_status(contact_id) == "extracted":
            pending.append((contact_id, contact.phone_e164))
    print(f"Novos, ainda nao consultados no Telegram: {len(pending)}")

    # 2. Resolucao no Telegram
    if pending:
        print(
            "\nA proxima etapa consulta o Telegram (contacts.importContacts) para descobrir "
            "quais numeros tem conta.\nEfeito colateral: voce pode aparecer como sugestao de "
            "contato para essas pessoas."
        )
        if _confirm("Prosseguir com a consulta"):
            found = asyncio.run(_resolve(settings, repo, pending))
            print(f"Encontrados no Telegram nesta rodada: {found}/{len(pending)}")
        else:
            print("Consulta cancelada.")

    # 3. Candidatos + confirmacao antes de adicionar
    candidates = _resolved_candidates(repo)
    if not candidates:
        print("\nNenhum candidato elegivel para adicao. Encerrando.")
        print(f"Relatorio: {_export_csv(repo)}")
        return

    already = repo.total_successful_adds()
    print(f"\n--- {len(candidates)} candidato(s) elegivel(is) ---")
    for contact_id, user_id, username, phone in candidates:
        print(f"  [{contact_id}] {phone} -> telegram_user_id={user_id} username={username}")
    print(
        f"\nJa adicionados historicamente: {already}/{settings.max_total_adds} (teto global)."
        f"\nSerao processados no maximo {settings.max_adds_per_run} nesta execucao."
    )

    if not _confirm("Confirmar adicao ao grupo do Telegram"):
        print("Adicao cancelada. Nada foi alterado no Telegram.")
        print(f"Relatorio: {_export_csv(repo)}")
        return

    asyncio.run(_add(settings, repo, [(cid, uid) for cid, uid, _, _ in candidates]))

    # 4. Relatorio final
    print("\n--- Relatorio final ---")
    print(f"Adicoes bem-sucedidas acumuladas: {repo.total_successful_adds()}/{settings.max_total_adds}")
    print(f"CSV: {_export_csv(repo)}")
    print("Log detalhado: logs/bridge.log")
