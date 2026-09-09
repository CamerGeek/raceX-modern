from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas.meetings import MeetingResponse
from app.services.meeting_persistence import persist_scraped_meeting
from app.services.scraping_service import detect_race_type, get_meetings, scrape_race
from app.services.supabase_client import SupabaseClientWrapper

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _race_is_q_plus(race: dict[str, Any]) -> bool:
    summary = race.get("summary") or {}
    if summary.get("q_plus") is not None:
        return bool(summary["q_plus"])
    rows = (race.get("raw_snapshot") or {}).get("rows") or []
    return any(str(row.get("Q+", "")).strip().lower() in {"true", "1", "yes"} for row in rows if isinstance(row, dict))


def _stored_meeting(meeting_url: str) -> dict[str, Any] | None:
    client = SupabaseClientWrapper()
    meeting = client.select_one("meetings", filters=[("url", "eq", meeting_url)], order_by=("created_at", "desc"))
    if not meeting:
        return None
    races = client.list("races", filters=[("meeting_id", "eq", meeting["id"])], order_by=("race_key", "asc"))
    return {"meeting": meeting, "races": [{"id": race["id"], "race_key": race.get("race_key", ""), "url": race["source_url"], "race_type": race.get("race_type"), "q_plus": _race_is_q_plus(race)} for race in races]}


@router.get("/stored")
def stored_meeting(meeting_url: str = Query(min_length=1)) -> dict[str, Any]:
    try:
        stored = _stored_meeting(meeting_url)
        return {"exists": stored is not None, **(stored or {"meeting": None, "races": []})}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stored meeting check failed: {exc}") from exc


@router.get("", response_model=MeetingResponse)
def list_meetings(
    meeting_date: date = Query(default_factory=date.today, alias="date"),
    refresh: bool = False,
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
def scrape_meeting(request: MeetingScrapeRequest) -> dict[str, Any]:
    try:
        if not request.force_refresh:
            stored = _stored_meeting(request.meeting_url)
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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Meeting scrape failed: {exc}") from exc
