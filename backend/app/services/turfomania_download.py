"""Download a persisted Turfomania meeting by scraping each of its race pages.

Turfomania has one partants URL per race (unlike zone-turf's single meeting
URL), so the meeting flow iterates the catalog race rows stored by
turfomania_catalog, scrapes each pending race, persists runners, and upgrades
race status pending/failed -> scraped. Races already scraped (or analyzed) are
skipped unless force_refresh is set.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd

from data_sources import data_source_manager
from turfomania_race import scrape_turfomania_race
from turfomania_reunions import _is_partants_url

from app.services.meeting_persistence import persist_scraped_meeting
from app.services.supabase_client import SupabaseClientWrapper

SOURCE = "turfomania"
SCRAPABLE_STATUSES = {"pending", "failed"}
STORED_STATUSES = {"scraped", "analyzed"}
URL_PREFIX = "turfomania://meetings/"


def turfomania_meeting_url(meeting_id: str) -> str:
    return f"{URL_PREFIX}{meeting_id}"


def parse_turfomania_meeting_url(value: str) -> str | None:
    if value.startswith(URL_PREFIX):
        return value[len(URL_PREFIX):] or None
    return None


def download_turfomania_meeting(
    meeting_id: str,
    *,
    force_refresh: bool = False,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    client: SupabaseClientWrapper | None = None,
) -> dict[str, Any]:
    supabase = client or SupabaseClientWrapper()
    meeting = supabase.select_one("meetings", filters=[("id", "eq", meeting_id)])
    if not meeting:
        raise LookupError(f"Meeting {meeting_id} not found")
    if meeting.get("source") != SOURCE:
        raise ValueError(f"Meeting {meeting_id} is source={meeting.get('source')!r}, not {SOURCE!r}")

    race_rows = supabase.list("races", filters=[("meeting_id", "eq", meeting_id)], limit=500)
    race_rows.sort(key=_race_sort_key)
    meeting_date = date.fromisoformat(str(meeting["meeting_date"]))

    def report(percent: int, message: str) -> None:
        if progress_callback:
            progress_callback(percent, message)

    report(2, f"Found {len(race_rows)} races for {meeting.get('name') or meeting_id}")

    scraped: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    runner_total = 0
    runner_tables: set[str] = set()
    columns: set[str] = set()

    for index, race in enumerate(race_rows):
        if cancel_check and cancel_check():
            report(100, "Cancelled")
            break

        race_key = str(race.get("race_key") or "")
        base_percent = 5 + int(90 * index / max(len(race_rows), 1))
        status = race.get("status")

        if status not in SCRAPABLE_STATUSES and not force_refresh:
            skipped.append(_race_option(race))
            continue

        url = (race.get("source_url") or "").strip()
        if not url:
            failure = {"race_key": race_key, "error": "race has no source_url"}
            _mark_failed(supabase, race, failure["error"])
            failed.append(failure)
            continue
        if not _is_partants_url(url):
            failure = {"race_key": race_key, "error": "race URL is not a Turfomania partants page"}
            _mark_failed(supabase, race, failure["error"])
            failed.append(failure)
            continue

        report(base_percent, f"Race {race_key or index + 1} ({index + 1}/{len(race_rows)}): scraping…")

        def race_progress(percent: int, message: str, *, base: int = base_percent) -> None:
            report(base + int(percent * 0.8 / max(len(race_rows), 1)), f"[{race_key}] {message}")

        try:
            race_type = race.get("race_type") if race.get("race_type") in {"flat", "trot"} else None
            if race_type:
                frame = data_source_manager.scrape_races(
                    url, race_type, source_name=SOURCE, progress_callback=race_progress, cancel_check=cancel_check
                )
            else:
                frame = scrape_turfomania_race(url, None, race_progress, cancel_check)
                race_type = _infer_race_type(frame)
            if frame is None or frame.empty:
                raise ValueError("scraper returned no runners")
            if race_key:
                frame = frame.copy()
                frame["REF_COURSE"] = race_key
            result = persist_scraped_meeting(
                frame,
                meeting_date=meeting_date,
                meeting_name=meeting.get("name"),
                meeting_url=None,
                race_type=race_type,
                source=SOURCE,
                client=supabase,
                meeting=meeting,
            )
        except Exception as exc:
            failure = {"race_key": race_key, "error": str(exc)}
            _mark_failed(supabase, race, str(exc))
            failed.append(failure)
            report(base_percent, f"Race {race_key}: failed ({exc})")
            continue

        scraped.extend(result["races"])
        runner_total += result["runner_count"]
        runner_tables.add(result["runner_table"])
        columns.update(str(column) for column in frame.columns)
        report(base_percent + int(80 / max(len(race_rows), 1)), f"Race {race_key}: {result['runner_count']} runners saved")

    report(100, f"Done — {len(scraped)} scraped, {len(skipped)} already stored, {len(failed)} failed")

    return {
        "meeting": meeting,
        "meeting_date": meeting["meeting_date"],
        "race_count": len(scraped),
        "runner_count": runner_total,
        "runner_table": " + ".join(sorted(runner_tables)) if runner_tables else None,
        "columns": sorted(columns),
        "races": scraped + skipped,
        "skipped_count": len(skipped),
        "failed": failed,
        "source": SOURCE,
    }


def _infer_race_type(frame: pd.DataFrame) -> str:
    return "flat" if "POIDS" in frame.columns else "trot"


def _race_sort_key(race: dict[str, Any]) -> tuple[int, str]:
    number = race.get("race_number")
    try:
        return (int(str(number)), str(race.get("race_key") or ""))
    except (TypeError, ValueError):
        return (9999, str(race.get("race_key") or ""))


def _race_option(race: dict[str, Any]) -> dict[str, Any]:
    summary = race.get("summary") or {}
    if summary.get("q_plus") is None:
        rows = (race.get("raw_snapshot") or {}).get("rows") or []
        q_plus = any(str(row.get("Q+", "")).strip().lower() in {"true", "1", "yes"} for row in rows if isinstance(row, dict))
    else:
        q_plus = bool(summary["q_plus"])
    return {
        "id": race["id"],
        "race_key": race.get("race_key") or "",
        "url": race.get("source_url"),
        "race_type": race.get("race_type"),
        "q_plus": q_plus,
    }


def _mark_failed(supabase: SupabaseClientWrapper, race: dict[str, Any], error: str) -> None:
    summary = dict(race.get("summary") or {})
    summary.update({"status": "failed", "error": error})
    supabase.update("races", id_value=race["id"], payload={"status": "failed", "summary": summary})
