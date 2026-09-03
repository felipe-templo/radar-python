import logging

from telethon import TelegramClient
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact

logger = logging.getLogger(__name__)


class TelegramResolver:
    """Resolve numeros de telefone para contas Telegram via contacts.importContacts.

    Efeito colateral conhecido e aceito: importar um contato pode fazer o
    usuario aparecer como sugestao de contato para a outra pessoa. So
    funciona se a privacidade dela permitir ser encontrada por telefone.
    """

    def __init__(self, client: TelegramClient):
        self.client = client

    async def resolve_batch(
        self, phones: list[str]
    ) -> dict[str, tuple[int, str | None] | None]:
        """Retorna {phone_e164: (user_id, username) ou None se nao encontrado}."""
        if not phones:
            return {}

        input_contacts = [
            InputPhoneContact(client_id=i, phone=phone, first_name=phone, last_name="")
            for i, phone in enumerate(phones)
        ]
        result = await self.client(
            ImportContactsRequest(contacts=input_contacts)
        )

        resolved: dict[str, tuple[int, str | None] | None] = {phone: None for phone in phones}
        users_by_id = {user.id: user for user in result.users}
        for imported in result.imported:
            phone = phones[imported.client_id]
            user = users_by_id.get(imported.user_id)
            username = user.username if user else None
            resolved[phone] = (imported.user_id, username)

        matched_user_ids = [uid for uid, _ in (v for v in resolved.values() if v is not None)]
        if matched_user_ids:
            try:
                await self.client(DeleteContactsRequest(id=matched_user_ids))
            except Exception:
                logger.warning(
                    "Falha ao limpar contatos temporarios importados; nao e critico.",
                    exc_info=True,
                )

        found = sum(1 for v in resolved.values() if v is not None)
        logger.info("Resolucao Telegram: %d/%d numeros encontrados.", found, len(phones))
        return resolved
