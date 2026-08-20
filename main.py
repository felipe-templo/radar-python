import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from radar.config import load_settings
from radar.logging_setup import setup_logging
from radar.scheduler import run_forever
from radar.sites import SITES_BY_KEY, SiteConfig

MENU_OPTIONS = {"1": ["ml"], "2": ["shopee"], "3": ["ml", "shopee"]}


def prompt_sites() -> list[SiteConfig]:
    print("Qual radar rodar?")
    print("  1) Mercado Livre")
    print("  2) Shopee")
    print("  3) Ambos")
    while True:
        choice = input("Escolha [1/2/3]: ").strip()
        keys = MENU_OPTIONS.get(choice)
        if keys:
            return [SITES_BY_KEY[key] for key in keys]
        print("Opcao invalida, digite 1, 2 ou 3.")


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    sites = prompt_sites()
    run_forever(settings, sites)


if __name__ == "__main__":
    main()
