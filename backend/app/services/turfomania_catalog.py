from __future__ import annotations

import re
from datetime import date
from typing import Any

from turfomania_reunions import parse_race_details, scrape_reunions

from app.services.supabase_client import SupabaseClientWrapper

SOURCE = "turfomania"


def scrape_turfomania_reunions() -> list[dict[str, Any]]:
    return scrape_reunions()


def persist_turfomania_reunions(
    reunions: list[dict[str, Any]],
    *,
    meeting_date: date,
    client: SupabaseClientWrapper | None = None,
) -> dict[str, Any]:
    """Store scraped réunion cards as meetings + pending races rows.

    Réunion containers have no URL of their own, so meetings are deduplicated on
    (source, meeting_date, name) and réunion extras go into metadata. Races are
    deduplicated on (meeting_id, race_key); existing rows are only refreshed
    while still pending, never after a detail scrape has upgraded them.
    """
    supabase = client or SupabaseClientWrapper()
    meeting_date_iso = meeting_date.isoformat()

    meetings: list[dict[str, Any]] = []
    races: list[dict[str, Any]] = []
    created = updated = skipped = 0

    for reunion in reunions:
        name = (reunion.get("track") or "").strip() or reunion.get("reunion") or None
        meeting = _get_or_create_meeting(
            supabase,
            meeting_date=meeting_date_iso,
            name=name,
            metadata={
                "reunion": reunion.get("reunion"),
                "header_right": reunion.get("header_right"),
            },
        )
        meeting_races = reunion.get("races") or []
        meetings.append({"id": meeting["id"], "name": name, "reunion": reunion.get("reunion"), "race_count": len(meeting_races)})

        for card in meeting_races:
            source_url = (card.get("href") or "").strip()
            if not source_url:
                continue
            race, action = _upsert_catalog_race(
                supabase,
                meeting_id=meeting["id"],
                card=card,
                source_url=source_url,
            )
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
            races.append({"id": race["id"], "race_key": race.get("race_key"), "url": source_url, "race_type": race.get("race_type"), "status": race.get("status")})

    return {
        "source": SOURCE,
        "meeting_date": meeting_date_iso,
        "meeting_count": len(meetings),
        "race_count": len(races),
        "races_created": created,
        "races_updated": updated,
        "races_skipped": skipped,
        "meetings": meetings,
        "races": races,
    }


def _get_or_create_meeting(client: SupabaseClientWrapper, *, meeting_date: str, name: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
    filters: list[tuple[str, str, Any]] = [("source", "eq", SOURCE), ("meeting_date", "eq", meeting_date)]
    if name is None:
        filters.append(("name", "is", "null"))
    else:
        filters.append(("name", "eq", name))
    existing = client.select_one("meetings", filters=filters, order_by=("created_at", "desc"))
    if existing:
        return existing
    return client.insert("meetings", {"source": SOURCE, "meeting_date": meeting_date, "name": name, "url": None, "metadata": metadata})


def _upsert_catalog_race(client: SupabaseClientWrapper, *, meeting_id: str, card: dict[str, Any], source_url: str) -> tuple[dict[str, Any], str]:
    code = (card.get("code") or "").strip()
    race_key = code.replace(" ", "") or None
    details = parse_race_details(card.get("text") or "")
    payload = {
        "meeting_id": meeting_id,
        "source": SOURCE,
        "race_type": details["race_type"],
        "source_url": source_url,
        "race_number": _race_number(code),
        "race_key": race_key,
        "raw_snapshot": {"card": card},
        "summary": {**details, "name": card.get("name"), "status": "pending"},
        "status": "pending",
    }

    existing = client.select_one(
        "races",
        filters=[("meeting_id", "eq", meeting_id), ("race_key", "eq", race_key)],
        order_by=("created_at", "desc"),
    )
    if not existing:
        return client.insert("races", payload), "created"
    if existing.get("status") == "pending":
        return client.update("races", id_value=existing["id"], payload=payload), "updated"
    return existing, "skipped"


def _race_number(code: str) -> str | None:
    parts = code.split()
    if not parts:
        return None
    digits = re.sub(r"\D", "", parts[-1])
    return digits or None
