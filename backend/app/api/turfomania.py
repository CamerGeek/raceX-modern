from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.turfomania_catalog import persist_turfomania_reunions, scrape_turfomania_reunions

router = APIRouter(prefix="/turfomania", tags=["turfomania"])


class TurfomaniaCatalogRequest(BaseModel):
    meeting_date: date | None = Field(default=None, alias="date")


@router.post("/reunions")
def catalog_reunions(request: TurfomaniaCatalogRequest | None = None) -> dict[str, Any]:
    """Scrape today's turfomania.fr réunion cards and store them as pending races."""
    try:
        reunions = scrape_turfomania_reunions()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Turfomania scrape failed: {exc}") from exc

    meeting_date = (request.meeting_date if request else None) or date.today()
    try:
        return persist_turfomania_reunions(reunions, meeting_date=meeting_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Turfomania persistence failed: {exc}") from exc
