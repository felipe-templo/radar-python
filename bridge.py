"""Entrypoint da ponte WhatsApp -> Telegram.

Fluxo interativo: extrai participantes do grupo aberto no WhatsApp Web,
deduplica, consulta quais tem conta no Telegram e (apos confirmacao manual)
adiciona os elegiveis ao grupo alvo.

Pre-requisitos:
  1. Chrome aberto com --remote-debugging-port=9222 (ver README.md).
  2. web.whatsapp.com logado, grupo aberto, painel "Dados do grupo" aberto
     e, se o grupo for grande, "Ver tudo" clicado.
  3. Sessao Telethon criada uma vez com: python scripts/telethon_login.py

Uso: python bridge.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from radar.bridge.cli import run


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrompido. O progresso ja gravado no banco e preservado; "
              "rode de novo para retomar de onde parou.")
        sys.exit(130)
    except RuntimeError as exc:
        print(f"\nErro: {exc}")
        sys.exit(1)
