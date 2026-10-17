from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

legacy_path = Path(__file__).resolve().parents[1] / "legacy"
if str(legacy_path) not in sys.path:
    sys.path.insert(0, str(legacy_path))

from app.api.races import (
    _analyze_today_turfomania_quinte,
    _cached_homepage_quinte_for_date,
)
from app.schemas.races import TodayQuinteAnalysisRequest
from app.services.supabase_client import SupabaseClientWrapper

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def prepare_tomorrow_quinte(*, now: datetime | None = None) -> dict[str, str]:
    local_now = now or datetime.now(PARIS_TIMEZONE)
    if local_now.tzinfo is None:
        raise ValueError("now must include a timezone")
    local_now = local_now.astimezone(PARIS_TIMEZONE)

    if local_now.hour != 23:
        return {"status": "not_scheduled", "paris_time": local_now.isoformat()}

    meeting_date = local_now.date() + timedelta(days=1)
    cached = _cached_homepage_quinte_for_date(
        SupabaseClientWrapper(),
        meeting_date,
    )
    if cached:
        return {
            "status": "already_cached",
            "meeting_date": meeting_date.isoformat(),
            "race_id": cached.race_id,
        }

    result = _analyze_today_turfomania_quinte(
        TodayQuinteAnalysisRequest(date=meeting_date),
        allow_tomorrow_analysis=True,
    )
    if not result.race_id:
        raise ValueError("Prepared Quinté analysis did not include a race ID")

    return {
        "status": "cached",
        "meeting_date": meeting_date.isoformat(),
        "race_id": result.race_id,
    }


def main() -> None:
    result = prepare_tomorrow_quinte()
    logger.info("Tomorrow Quinté preparation completed: %s", result)


if __name__ == "__main__":
    main()
