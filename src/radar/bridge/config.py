from dataclasses import dataclass
import os
from dotenv import load_dotenv


@dataclass(frozen=True)
class BridgeSettings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_target_group_id: str
    telethon_session_path: str
    chrome_debug_url: str
    db_path: str
    log_level: str
    dry_run: bool
    max_adds_per_run: int
    max_groups_per_run: int
    max_total_adds: int
    min_delay_between_adds_seconds: float
    max_delay_between_adds_seconds: float
    floodwait_auto_sleep_max_seconds: int


def load_bridge_settings() -> BridgeSettings:
    load_dotenv()

    def require(key: str) -> str:
        val = os.getenv(key)
        if not val:
            raise RuntimeError(f"Variavel obrigatoria ausente no .env: {key}")
        return val

    return BridgeSettings(
        telegram_api_id=int(require("TELEGRAM_API_ID")),
        telegram_api_hash=require("TELEGRAM_API_HASH"),
        telegram_target_group_id=require("TELEGRAM_TARGET_GROUP_ID"),
        telethon_session_path=os.getenv("TELETHON_SESSION_PATH", "telethon_session/bridge"),
        chrome_debug_url=os.getenv("CHROME_DEBUG_URL", "http://localhost:9222"),
        db_path=os.getenv("BRIDGE_DB_PATH", "data/bridge.db"),
        log_level=os.getenv("BRIDGE_LOG_LEVEL", "INFO"),
        dry_run=os.getenv("BRIDGE_DRY_RUN", "true").lower() == "true",
        max_adds_per_run=int(os.getenv("MAX_ADDS_PER_RUN", "20")),
        max_groups_per_run=int(os.getenv("MAX_GROUPS_PER_RUN", "3")),
        max_total_adds=int(os.getenv("MAX_TOTAL_ADDS", "1000")),
        min_delay_between_adds_seconds=float(os.getenv("MIN_DELAY_BETWEEN_ADDS_SECONDS", "45")),
        max_delay_between_adds_seconds=float(os.getenv("MAX_DELAY_BETWEEN_ADDS_SECONDS", "90")),
        floodwait_auto_sleep_max_seconds=int(os.getenv("FLOODWAIT_AUTO_SLEEP_MAX_SECONDS", "120")),
    )
