from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas.meetings import MeetingResponse
from app.services.meeting_persistence import persist_scraped_meeting
from app.services.scraping_service import detect_race_type, get_meetings, scrape_race
from app.services.supabase_client import SupabaseClientWrapper
from app.services.auth_service import require_admin
from app.services.turfomania_download import (
    STORED_STATUSES,
    download_turfomania_meeting,
    parse_turfomania_meeting_url,
)

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _race_is_q_plus(race: dict[str, Any]) -> bool:
    summary = race.get("summary") or {}
    if summary.get("q_plus") is not None:
        return bool(summary["q_plus"])
    rows = (race.get("raw_snapshot") or {}).get("rows") or []
    return any(str(row.get("Q+", "")).strip().lower() in {"true", "1", "yes"} for row in rows if isinstance(row, dict))


def _stored_meeting(meeting_url: str, meeting_date: date) -> dict[str, Any] | None:
    client = SupabaseClientWrapper()
    meeting = client.select_one(
        "meetings",
        filters=[("url", "eq", meeting_url), ("meeting_date", "eq", meeting_date.isoformat())],
        order_by=("created_at", "desc"),
    )
    if not meeting:
        return None
    races = client.list("races", filters=[("meeting_id", "eq", meeting["id"])], order_by=("race_key", "asc"))
    return {"meeting": meeting, "races": [_race_option(race) for race in races]}


def _race_option(race: dict[str, Any]) -> dict[str, Any]:
    return {"id": race["id"], "race_key": race.get("race_key", ""), "url": race.get("source_url"), "race_type": race.get("race_type"), "q_plus": _race_is_q_plus(race)}


def _turfomania_bundle(meeting_id: str) -> dict[str, Any] | None:
    client = SupabaseClientWrapper()
    meeting = client.select_one("meetings", filters=[("id", "eq", meeting_id)])
    if not meeting or meeting.get("source") != "turfomania":
        return None
    races = client.list("races", filters=[("meeting_id", "eq", meeting_id)], limit=500, order_by=("race_key", "asc"))
    return {"meeting": meeting, "races": races}


def _stored_turfomania_meeting(meeting_id: str) -> dict[str, Any] | None:
    bundle = _turfomania_bundle(meeting_id)
    if not bundle or not any(race.get("status") in STORED_STATUSES for race in bundle["races"]):
        return None
    return {"meeting": bundle["meeting"], "races": [_race_option(race) for race in bundle["races"]]}


@router.get("/stored")
def stored_meeting(meeting_url: str = Query(min_length=1), meeting_date: date = Query(alias="date"), _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        turfomania_id = parse_turfomania_meeting_url(meeting_url)
        if turfomania_id:
            stored = _stored_turfomania_meeting(turfomania_id)
            return {"exists": stored is not None, **(stored or {"meeting": None, "races": []})}
        stored = _stored_meeting(meeting_url, meeting_date)
        return {"exists": stored is not None, **(stored or {"meeting": None, "races": []})}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stored meeting check failed: {exc}") from exc


@router.get("", response_model=MeetingResponse)
def list_meetings(
    meeting_date: date = Query(default_factory=date.today, alias="date"),
    refresh: bool = False,
    _: dict[str, Any] = Depends(require_admin),
) -> MeetingResponse:
    return MeetingResponse(date=meeting_date.isoformat(), meetings=get_meetings(meeting_date, force_refresh=refresh))


class MeetingScrapeRequest(BaseModel):
    meeting_date: date = Field(alias="date")
    meeting_url: str = Field(min_length=1)
    meeting_name: str | None = None
    race_type: Literal["flat", "trot"] | None = None
    source: str = "zone-turf"
    force_refresh: bool = False


@router.post("/scrape")
def scrape_meeting(request: MeetingScrapeRequest, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        turfomania_id = parse_turfomania_meeting_url(request.meeting_url)
        if turfomania_id or request.source == "turfomania":
            return _scrape_turfomania_meeting(turfomania_id, request)
        if not request.force_refresh:
            stored = _stored_meeting(request.meeting_url, request.meeting_date)
            if stored:
                return {"already_stored": True, **stored, "race_type": request.race_type}
        race_type = request.race_type or detect_race_type(request.meeting_url)
        frame = scrape_race(request.meeting_url, race_type, request.source)
        return persist_scraped_meeting(
            frame,
            meeting_date=request.meeting_date,
            meeting_name=request.meeting_name,
            meeting_url=request.meeting_url,
            race_type=race_type,
            source=request.source,
        ) | {"race_type": race_type, "columns": [str(column) for column in frame.columns]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Meeting scrape failed: {exc}") from exc


def _scrape_turfomania_meeting(meeting_id: str | None, request: MeetingScrapeRequest) -> dict[str, Any]:
    if not meeting_id:
        raise HTTPException(status_code=422, detail="Turfomania meeting URL must look like turfomania://meetings/{id}")
    bundle = _turfomania_bundle(meeting_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"Turfomania meeting {meeting_id} not found")
    if not request.force_refresh and bundle["races"] and all(race.get("status") in STORED_STATUSES for race in bundle["races"]):
        return {"already_stored": True, "meeting": bundle["meeting"], "races": [_race_option(race) for race in bundle["races"]], "race_type": bundle["races"][0].get("race_type") if bundle["races"] else None}
    result = download_turfomania_meeting(meeting_id, force_refresh=request.force_refresh)
    return result | {"race_type": result["races"][0].get("race_type") if result["races"] else None}
