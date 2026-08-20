from dataclasses import dataclass
import os
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_admin_chat_id: str | None
    chrome_debug_url: str
    offers_url: str
    shopee_offers_url: str
    amazon_offers_url: str
    check_interval_seconds: int
    max_products_per_cycle: int
    min_discount_percent: int
    db_path: str
    log_level: str
    dry_run: bool


def load_settings() -> Settings:
    load_dotenv()

    def require(key: str) -> str:
        val = os.getenv(key)
        if not val:
            raise RuntimeError(f"Variavel obrigatoria ausente no .env: {key}")
        return val

    return Settings(
        telegram_bot_token=require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=require("TELEGRAM_CHAT_ID"),
        telegram_admin_chat_id=os.getenv("TELEGRAM_ADMIN_CHAT_ID"),
        chrome_debug_url=os.getenv("CHROME_DEBUG_URL", "http://localhost:9222"),
        offers_url=os.getenv("OFFERS_URL", "https://www.mercadolivre.com.br/ofertas#nav-header"),
        shopee_offers_url=os.getenv("SHOPEE_OFFERS_URL", "https://shopee.com.br/flash_sale"),
        amazon_offers_url=os.getenv("AMAZON_OFFERS_URL", "https://www.amazon.com.br/deals?ref_=nav_cs_gb"),
        check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "300")),
        max_products_per_cycle=int(os.getenv("MAX_PRODUCTS_PER_CYCLE", "15")),
        min_discount_percent=int(os.getenv("MIN_DISCOUNT_PERCENT", "10")),
        db_path=os.getenv("DB_PATH", "data/posted_products.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
    )
