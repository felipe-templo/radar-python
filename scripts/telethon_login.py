"""Login inicial da conta pessoal no Telethon (MTProto).

So precisa rodar uma vez. Pede telefone + codigo (SMS/Telegram) interativamente.
Depois disso a sessao fica salva em TELETHON_SESSION_PATH e as proximas
execucoes do bridge nao pedem login de novo.

Uso: python scripts/telethon_login.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telethon.sync import TelegramClient

from radar.bridge.config import load_bridge_settings


def main() -> None:
    settings = load_bridge_settings()
    os.makedirs(Path(settings.telethon_session_path).parent, exist_ok=True)
    with TelegramClient(settings.telethon_session_path, settings.telegram_api_id, settings.telegram_api_hash) as client:
        me = client.get_me()
        print(f"Login OK: {me.first_name} (id={me.id}, phone={me.phone})")


if __name__ == "__main__":
    main()
