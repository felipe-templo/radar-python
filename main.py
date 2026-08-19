import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from radar.config import load_settings
from radar.logging_setup import setup_logging
from radar.scheduler import run_forever


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    run_forever(settings)


if __name__ == "__main__":
    main()
