import argparse
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from radar.config import load_settings
from radar.logging_setup import setup_logging
from radar.scheduler import run_forever, run_once
from radar.sites import SITES_BY_KEY, SiteConfig
from radar.telegram_client import TelegramClient

MENU_OPTIONS = {"1": ["ml"], "2": ["shopee"], "3": ["amazon"], "4": ["ml", "shopee", "amazon"]}


def prompt_sites() -> list[SiteConfig]:
    print("Qual radar rodar?")
    print("  1) Mercado Livre")
    print("  2) Shopee")
    print("  3) Amazon")
    print("  4) Todos")
    while True:
        choice = input("Escolha [1/2/3/4]: ").strip()
        keys = MENU_OPTIONS.get(choice)
        if keys:
            return [SITES_BY_KEY[key] for key in keys]
        print("Opcao invalida, digite 1, 2, 3 ou 4.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Radar de ofertas (ML/Shopee/Amazon)")
    parser.add_argument(
        "--sites",
        help="Sites a rodar, separados por virgula (ml,shopee,amazon) ou 'all'. "
        "Se omitido, pergunta interativamente.",
    )
    parser.add_argument(
        "--quantity",
        type=int,
        help="Override de MAX_PRODUCTS_PER_CYCLE (quantidade de produtos por site nesta execucao).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Roda um unico ciclo (descoberta + fila) e encerra, em vez do loop continuo.",
    )
    parser.add_argument(
        "--channel",
        choices=["telegram", "whatsapp"],
        default="telegram",
        help="Canal de envio. Apenas 'telegram' esta implementado hoje.",
    )
    parser.add_argument(
        "--message",
        help="Envia esta mensagem (HTML) direto pro Telegram e encerra, sem rodar scraping/Chrome.",
    )
    parser.add_argument(
        "--chat-id",
        help="Chat/canal de destino da --message. Se omitido, usa TELEGRAM_CHAT_ID do .env.",
    )
    return parser.parse_args()


def resolve_sites(sites_arg: str) -> list[SiteConfig]:
    if sites_arg.strip().lower() == "all":
        keys = ["ml", "shopee", "amazon"]
    else:
        keys = [key.strip().lower() for key in sites_arg.split(",") if key.strip()]

    unknown = [key for key in keys if key not in SITES_BY_KEY]
    if unknown:
        raise SystemExit(f"Site(s) desconhecido(s): {', '.join(unknown)}. Use ml, shopee, amazon ou all.")

    return [SITES_BY_KEY[key] for key in keys]


def main() -> None:
    args = parse_args()

    if args.message is not None:
        settings = load_settings()
        setup_logging(settings.log_level)
        telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
        telegram.send_message(args.message, chat_id=args.chat_id)
        return

    if args.channel == "whatsapp":
        print("Canal WhatsApp ainda nao implementado.", file=sys.stderr)
        sys.exit(2)

    settings = load_settings()
    setup_logging(settings.log_level)

    if args.quantity is not None:
        settings = dataclasses.replace(settings, max_products_per_cycle=args.quantity)

    sites = resolve_sites(args.sites) if args.sites else prompt_sites()

    if args.once:
        run_once(settings, sites)
    else:
        run_forever(settings, sites)


if __name__ == "__main__":
    main()
