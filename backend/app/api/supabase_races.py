from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.supabase_client import SupabaseClientWrapper
from app.services.auth_service import require_admin

router = APIRouter(prefix="/supabase-races", tags=["supabase-races"])


class RaceWriteRequest(BaseModel):
    meeting_id: str | None = None
    source: str = "zone-turf"
    race_type: str = Field(pattern="^(flat|trot)$")
    source_url: str = Field(min_length=1)
    race_number: str | None = None
    race_key: str | None = None
    raw_snapshot: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    status: str = "scraped"


@router.post("", status_code=201)
def write_race_to_supabase(request: RaceWriteRequest, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    client = SupabaseClientWrapper()
    try:
        existing = client.select_one(
            "races",
            filters=[("source_url", "eq", request.source_url)],
            order_by=("created_at", "desc"),
        )

        if existing:
            updated = client.update(
                "races",
                id_value=existing["id"],
                payload={
                    "meeting_id": request.meeting_id,
                    "source": request.source,
                    "race_type": request.race_type,
                    "source_url": request.source_url,
                    "race_number": request.race_number,
                    "race_key": request.race_key,
                    "raw_snapshot": request.raw_snapshot,
                    "summary": request.summary,
                    "status": request.status,
                },
            )
            return {"created": False, "race": updated}

        created = client.insert(
            "races",
            {
                "meeting_id": request.meeting_id,
                "source": request.source,
                "race_type": request.race_type,
                "source_url": request.source_url,
                "race_number": request.race_number,
                "race_key": request.race_key,
                "raw_snapshot": request.raw_snapshot,
                "summary": request.summary,
                "status": request.status,
            },
        )
        return {"created": True, "race": created}
    except Exception as exc:  # pragma: no cover - API boundary error
        raise HTTPException(status_code=500, detail=f"Failed to write race to Supabase: {exc}") from exc


class AnalysisWriteRequest(BaseModel):
    race_id: str = Field(min_length=1)
    model_version: str = "initial-migration"
    summary: dict[str, Any] = {}
    prognosis: list[dict[str, Any]] = []
    handicap: dict[str, Any] = {}
    raw_rows: list[dict[str, Any]] = []


@router.post("/analysis", status_code=201)
def write_analysis_to_supabase(request: AnalysisWriteRequest, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    client = SupabaseClientWrapper()
    try:
        created = client.insert(
            "analysis_runs",
            {
                "race_id": request.race_id,
                "model_version": request.model_version,
                "summary": request.summary,
                "prognosis": request.prognosis,
                "handicap": request.handicap,
                "raw_rows": request.raw_rows,
            },
        )
        return {"created": True, "analysis": created}
    except Exception as exc:  # pragma: no cover - API boundary error
        raise HTTPException(status_code=500, detail=f"Failed to write analysis to Supabase: {exc}") from exc


@router.get("/{race_id}")
def get_race_and_latest_analysis(race_id: str, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    client = SupabaseClientWrapper()
    try:
        race = client.select_one("races", filters=[("id", "eq", race_id)])
        if not race:
            raise HTTPException(status_code=404, detail="Race not found")

        latest_analysis = client.select_one(
            "analysis_runs",
            filters=[("race_id", "eq", race_id)],
            order_by=("created_at", "desc"),
        )

        return {
            "race": race,
            "latest_analysis": latest_analysis,
        }
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - API boundary error
        raise HTTPException(status_code=500, detail=f"Failed to read race data from Supabase: {exc}") from exc
