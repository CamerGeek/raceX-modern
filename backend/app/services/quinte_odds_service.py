from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd

from app.services.meeting_persistence import persist_scraped_meeting
from app.services.supabase_client import SupabaseClientWrapper
from app.services.turfomania_catalog import persist_turfomania_reunions, scrape_turfomania_reunions
from app.services.turfomania_quinte import find_turfomania_quinte_meeting, turfomania_quinte_race_type
from app.services.serialization import dataframe_records

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
ODDS_HISTORY_TABLE = "quinte_odds_snapshots"
ODDS_SNAPSHOT_CONFLICT = 'race_id,captured_at,"N°"'


def collect_today_quinte_odds(
    client: SupabaseClientWrapper | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record one fresh snapshot of today's Quinté+ starter odds."""
    supabase = client or SupabaseClientWrapper()
    local_now = now.astimezone(PARIS_TIMEZONE) if now else datetime.now(PARIS_TIMEZONE)
    meeting_date = local_now.date()

    meetings = supabase.list(
        "meetings",
        filters=[("source", "eq", "turfomania"), ("meeting_date", "eq", meeting_date.isoformat())],
        limit=100,
    )
    if not meetings:
        reunions = scrape_turfomania_reunions()
        persist_turfomania_reunions(reunions, meeting_date=meeting_date, client=supabase)
        meetings = supabase.list(
            "meetings",
            filters=[("source", "eq", "turfomania"), ("meeting_date", "eq", meeting_date.isoformat())],
            limit=100,
        )
    if not meetings:
        return {"status": "no_meeting", "date": meeting_date.isoformat(), "samples_saved": 0}

    meeting, frame = find_turfomania_quinte_meeting(meetings)
    race_type = turfomania_quinte_race_type(frame)
    start_time = _race_start_time(frame)
    if start_time and local_now.timetz().replace(tzinfo=None) >= start_time:
        return {
            "status": "race_started",
            "date": meeting_date.isoformat(),
            "start_time": start_time.strftime("%H:%M"),
            "samples_saved": 0,
        }

    persisted = persist_scraped_meeting(
        frame,
        meeting_date=meeting_date,
        meeting_name=meeting.get("name"),
        meeting_url=None,
        race_type=race_type,
        source="turfomania",
        client=supabase,
        meeting=meeting,
    )
    if not persisted["races"]:
        raise ValueError("No Quinté race was persisted while collecting odds")

    race_id = persisted["races"][0]["id"]
    captured_at = local_now.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
    samples = _odds_samples(frame, race_id=race_id, captured_at=captured_at)
    if not samples:
        raise ValueError("The current Quinté+ page contains no valid horse odds")

    saved = supabase.upsert_many(
        ODDS_HISTORY_TABLE,
        samples,
        on_conflict=ODDS_SNAPSHOT_CONFLICT,
    )
    return {
        "status": "saved",
        "date": meeting_date.isoformat(),
        "race_id": race_id,
        "race_key": persisted["races"][0]["race_key"],
        "captured_at": captured_at,
        "samples_saved": len(saved) if saved else len(samples),
    }


def get_today_quinte_odds_history(
    client: SupabaseClientWrapper | None = None,
    *,
    meeting_date: date,
) -> dict[str, Any]:
    """Return today's stored odds time series grouped by runner."""
    supabase = client or SupabaseClientWrapper()
    meetings = supabase.list(
        "meetings",
        filters=[("source", "eq", "turfomania"), ("meeting_date", "eq", meeting_date.isoformat())],
        limit=100,
    )
    races: list[dict[str, Any]] = []
    for meeting in meetings:
        races.extend(
            supabase.list(
                "races",
                filters=[("meeting_id", "eq", meeting["id"])],
                limit=500,
            )
        )
    quinte_race = next(
        (
            race
            for race in races
            if race.get("source") == "turfomania"
            and bool((race.get("summary") or {}).get("q_plus"))
        ),
        None,
    )
    if not quinte_race:
        return {"date": meeting_date.isoformat(), "race": None, "series": []}

    samples = supabase.list(
        ODDS_HISTORY_TABLE,
        filters=[("race_id", "eq", quinte_race["id"])],
        limit=5000,
        order_by=("captured_at", "asc"),
    )
    runners: dict[str, dict[str, Any]] = {}
    for sample in samples:
        number = str(sample.get("N°") or "").strip()
        if not number:
            continue
        runner = runners.setdefault(
            number,
            {
                "number": number,
                "horse_name": sample.get("CHEVAL") or "",
                "points": [],
            },
        )
        runner["points"].append(
            {
                "captured_at": sample["captured_at"],
                "odds": float(sample["odds"]),
            }
        )
    for runner in runners.values():
        runner["points"].sort(key=lambda point: point["captured_at"])
    return {
        "date": meeting_date.isoformat(),
        "race": {
            "id": quinte_race["id"],
            "race_key": quinte_race.get("race_key"),
            "race_type": quinte_race.get("race_type"),
            "summary": quinte_race.get("summary") or {},
        },
        "series": sorted(runners.values(), key=lambda row: _number_sort_key(row["number"])),
    }


def _odds_samples(frame: pd.DataFrame, *, race_id: str, captured_at: str) -> list[dict[str, Any]]:
    records = dataframe_records(frame)
    samples: list[dict[str, Any]] = []
    for row in records:
        number = str(row.get("N°") or "").strip()
        odds = _parse_odds(row.get("COTE"))
        if not number or odds is None:
            continue
        samples.append(
            {
                "race_id": race_id,
                "captured_at": captured_at,
                "N°": number,
                "CHEVAL": str(row.get("CHEVAL") or ""),
                "odds": odds,
            }
        )
    return samples


def _parse_odds(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        odds = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return odds if pd.notna(odds) and odds > 0 else None


def _race_start_time(frame: pd.DataFrame) -> time | None:
    if "START_TIME" not in frame.columns or frame.empty:
        return None
    value = str(frame["START_TIME"].iloc[0] or "").strip().lower()
    if not value:
        return None
    try:
        hour, minute = value.replace("h", ":").split(":", maxsplit=1)
        return time(hour=int(hour), minute=int(minute))
    except (ValueError, TypeError):
        return None


def _number_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value), value
    except ValueError:
        return 10**9, value
