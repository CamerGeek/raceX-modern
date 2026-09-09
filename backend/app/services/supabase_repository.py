import json
from typing import Any

from supabase import Client, create_client

from app.core.config import get_settings


class SupabaseRaceRepository:
    def __init__(self, client: Client | None = None):
        self.settings = get_settings()
        self.client = client or create_client(
            self.settings.supabase_url,
            self.settings.supabase_key,
        )

    def create_meeting(self, *, source: str, meeting_date: str, name: str | None, url: str | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "source": source,
            "meeting_date": meeting_date,
            "name": name,
            "url": url,
            "metadata": metadata or {},
        }
        response = self.client.table("meetings").insert(payload).execute()
        return response.data[0] if response.data else {}

    def get_meeting_by_date(self, *, source: str, meeting_date: str) -> dict[str, Any] | None:
        response = (
            self.client.table("meetings")
            .select("*")
            .eq("source", source)
            .eq("meeting_date", meeting_date)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def create_race(
        self,
        *,
        meeting_id: str,
        source: str,
        race_type: str,
        source_url: str,
        race_number: str | None = None,
        race_key: str | None = None,
        raw_snapshot: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> dict[str, Any]:
        payload = {
            "meeting_id": meeting_id,
            "source": source,
            "race_type": race_type,
            "source_url": source_url,
            "race_number": race_number,
            "race_key": race_key,
            "raw_snapshot": raw_snapshot or {},
            "summary": summary or {},
            "status": status,
        }
        response = self.client.table("races").insert(payload).execute()
        return response.data[0] if response.data else {}

    def get_race_by_url(self, *, source_url: str) -> dict[str, Any] | None:
        response = (
            self.client.table("races")
            .select("*")
            .eq("source_url", source_url)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def upsert_race(self, *, source_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_race_by_url(source_url=source_url)
        if existing:
            response = (
                self.client.table("races")
                .update(payload)
                .eq("id", existing["id"])
                .execute()
            )
            return response.data[0] if response.data else existing
        return self.create_race(
            meeting_id=payload["meeting_id"],
            source=payload["source"],
            race_type=payload["race_type"],
            source_url=source_url,
            race_number=payload.get("race_number"),
            race_key=payload.get("race_key"),
            raw_snapshot=payload.get("raw_snapshot") or {},
            summary=payload.get("summary") or {},
            status=payload.get("status", "pending"),
        )

    def create_analysis_run(
        self,
        *,
        race_id: str,
        model_version: str,
        summary: dict[str, Any] | None = None,
        prognosis: list[dict[str, Any]] | None = None,
        handicap: dict[str, Any] | None = None,
        raw_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "race_id": race_id,
            "model_version": model_version,
            "summary": summary or {},
            "prognosis": prognosis or [],
            "handicap": handicap or {},
            "raw_rows": raw_rows or [],
        }
        response = self.client.table("analysis_runs").insert(payload).execute()
        return response.data[0] if response.data else {}

    def get_latest_analysis_for_race(self, *, race_id: str) -> dict[str, Any] | None:
        response = (
            self.client.table("analysis_runs")
            .select("*")
            .eq("race_id", race_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_race_with_latest_analysis(self, *, race_id: str) -> dict[str, Any] | None:
        race = (
            self.client.table("races")
            .select("*, analysis_runs(*)")
            .eq("id", race_id)
            .limit(1)
            .execute()
        )
        return race.data[0] if race.data else None

    def create_job(
        self,
        *,
        job_type: str,
        status: str = "queued",
        progress: int = 0,
        metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
        result_url: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "type": job_type,
            "status": status,
            "progress": progress,
            "metadata": metadata or {},
            "error_message": error_message,
            "result_url": result_url,
        }
        response = self.client.table("jobs").insert(payload).execute()
        return response.data[0] if response.data else {}

    def update_job(self, *, job_id: str, **fields: Any) -> dict[str, Any] | None:
        response = self.client.table("jobs").update(fields).eq("id", job_id).execute()
        return response.data[0] if response.data else None

    def list_recent_races(self, *, limit: int = 25) -> list[dict[str, Any]]:
        response = (
            self.client.table("races")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
