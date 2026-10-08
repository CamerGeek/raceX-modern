from __future__ import annotations

import logging
import sys
from pathlib import Path

legacy_path = Path(__file__).resolve().parents[1] / "legacy"
if str(legacy_path) not in sys.path:
    sys.path.insert(0, str(legacy_path))

from app.services.quinte_odds_service import collect_today_quinte_odds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    result = collect_today_quinte_odds()
    logger.info("Quinté odds poll completed: %s", result)


if __name__ == "__main__":
    main()
