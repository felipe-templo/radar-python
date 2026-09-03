import asyncio
import logging
import random

from telethon import TelegramClient
from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError
from telethon.tl.functions.channels import InviteToChannelRequest

from radar.bridge.config import BridgeSettings
from radar.bridge.repository import BridgeRepository

logger = logging.getLogger(__name__)


class PeerFloodStop(Exception):
    """Levantado quando o Telegram sinaliza risco de spam na conta. Para tudo."""


async def add_one(
    client: TelegramClient, target_entity, contact_id: int, telegram_user_id: int
) -> tuple[bool, str | None, int | None]:
    try:
        await client(InviteToChannelRequest(channel=target_entity, users=[telegram_user_id]))
        return True, None, None
    except FloodWaitError as exc:
        return False, "FloodWait", exc.seconds
    except PeerFloodError:
        return False, "PeerFlood", None
    except UserPrivacyRestrictedError:
        return False, "PrivacyRestricted", None
    except Exception as exc:
        return False, f"Other: {exc}", None


async def run_add_batch(
    client: TelegramClient,
    repo: BridgeRepository,
    settings: BridgeSettings,
    target_entity,
    candidates: list[tuple[int, int]],
) -> None:
    """candidates: lista de (contact_id, telegram_user_id) ja aprovados manualmente."""
    total_before = repo.total_successful_adds()
    remaining_global = settings.max_total_adds - total_before
    if remaining_global <= 0:
        logger.warning(
            "Teto global de adicoes (%d) ja atingido. Nenhuma adicao sera feita.",
            settings.max_total_adds,
        )
        return

    to_process = candidates[: min(settings.max_adds_per_run, remaining_global)]
    logger.info(
        "Iniciando lote de adicao: %d contatos (limite por execucao=%d, restante do teto global=%d).",
        len(to_process),
        settings.max_adds_per_run,
        remaining_global,
    )

    for contact_id, telegram_user_id in to_process:
        if settings.dry_run:
            logger.info("[DRY RUN] adicionaria contact_id=%d (telegram_user_id=%d)", contact_id, telegram_user_id)
            repo.record_add_attempt(contact_id, settings.telegram_target_group_id, success=True, error_reason="dry_run")
            continue

        success, error_reason, wait_seconds = await add_one(
            client, target_entity, contact_id, telegram_user_id
        )

        if error_reason == "PeerFlood":
            repo.record_add_attempt(
                contact_id, settings.telegram_target_group_id, success=False, error_reason=error_reason
            )
            logger.error(
                "PeerFloodError recebido - parando lote imediatamente. "
                "Conta sinalizada por comportamento de spam; NAO retente automaticamente."
            )
            raise PeerFloodStop()

        if error_reason == "FloodWait":
            if wait_seconds is not None and wait_seconds <= settings.floodwait_auto_sleep_max_seconds:
                logger.warning("FloodWait de %ds - aguardando automaticamente.", wait_seconds)
                await asyncio.sleep(wait_seconds)
                success, error_reason, wait_seconds = await add_one(
                    client, target_entity, contact_id, telegram_user_id
                )
            else:
                repo.record_add_attempt(
                    contact_id,
                    settings.telegram_target_group_id,
                    success=False,
                    error_reason=error_reason,
                    wait_seconds=wait_seconds,
                )
                logger.error(
                    "FloodWait de %ss excede o limite configurado (%ds) - parando execucao. "
                    "Retome manualmente mais tarde.",
                    wait_seconds,
                    settings.floodwait_auto_sleep_max_seconds,
                )
                return

        repo.record_add_attempt(
            contact_id,
            settings.telegram_target_group_id,
            success=success,
            error_reason=error_reason,
            wait_seconds=wait_seconds,
        )
        logger.info(
            "contact_id=%d -> %s%s",
            contact_id,
            "adicionado" if success else "falhou",
            f" ({error_reason})" if error_reason else "",
        )

        delay = random.uniform(settings.min_delay_between_adds_seconds, settings.max_delay_between_adds_seconds)
        await asyncio.sleep(delay)

    logger.info("Lote de adicao finalizado.")
