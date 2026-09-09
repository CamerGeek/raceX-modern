from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.services.serialization import dataframe_records
from app.services.supabase_client import SupabaseClientWrapper


FLAT_TABLE = "flat_race_runners"
TROT_TABLE = "trot_race_runners"

FLAT_COLUMNS = {
    "N°", "CHEVAL", "COTE", "DIST.", "SEXE", "AGE", "POIDS", "PAST_POIDS",
    "MUSIQUE", "JOCKEY", "ENTRAINEUR", "JOCKEY_MUSIC", "TRAINER_MUSIC",
    "FORME_J", "FORME_T", "FORME", "IF", "S_COEFF", "IC", "COMPOSITE_SCORE",
    "CLASS_ADVANTAGE", "IS_PENALIZED", "HORSE_LINK", "RACE_URL", "RACE_DATE",
    "HIPPODROME", "REF_COURSE", "PRIZE_NAME", "DIST", "RACE_CONDITIONS",
    "DESCRIPTIF", "Q+", "TABLE_INDEX", "COURSE_ID", "MEETING_ID", "STARTERS",
    "NUM_STARTERS", "ALLOCATION", "LICE", "DISTANCE", "HANDICAP", "RECLAMER",
    "LISTED", "GRP", "CLASSE", "HIPPOID", "SURFACE", "OEILL.", "DEF.",
    "J-DECH.", "N_WEIGHT", "GAIN", "PMU", "PMU_FR", "DSCP",
}

TROT_COLUMNS = {
    "N°", "CHEVAL", "COTE", "DIST.", "SEXE", "AGE", "POIDS", "MUSIQUE",
    "JOCKEY", "ENTRAINEUR", "JOCKEY_MUSIC", "TRAINER_MUSIC", "FORME_J", "FORME_T",
    "IF", "S_COEFF", "IC", "HANDICAP_DISTANCE", "HORSE_LINK", "RACE_URL",
    "RACE_DATE", "HIPPODROME", "REF_COURSE", "PRIZE_NAME", "DIST",
    "RACE_CONDITIONS", "DESCRIPTIF", "Q+", "TABLE_INDEX", "COURSE_ID", "MEETING_ID",
}


def persist_scraped_meeting(
    frame: pd.DataFrame,
    *,
    meeting_date: date,
    meeting_name: str | None,
    meeting_url: str,
    race_type: str,
    source: str = "zone-turf",
    client: SupabaseClientWrapper | None = None,
) -> dict[str, Any]:
    if race_type not in {"flat", "trot"}:
        raise ValueError("race_type must be flat or trot")
    if frame.empty:
        return {"meeting": None, "race_count": 0, "runner_count": 0, "runner_table": _runner_table(race_type)}

    supabase = client or SupabaseClientWrapper()
    meeting = _get_or_create_meeting(
        supabase,
        source=source,
        meeting_date=meeting_date.isoformat(),
        meeting_name=meeting_name,
        meeting_url=meeting_url,
    )
    runner_table = _runner_table(race_type)
    race_key_column = _first_column(frame, ("REF_COURSE", "ID_COURSE", "COURSE_ID"))
    if not race_key_column:
        raise ValueError("Scraped data does not contain a race identifier column")

    persisted_races = 0
    persisted_runners = 0
    races: list[dict[str, Any]] = []
    for race_key, race_frame in frame.groupby(race_key_column, dropna=False):
        normalized_key = str(race_key) if pd.notna(race_key) else None
        if not normalized_key:
            continue
        source_url = _race_source_url(race_frame, meeting_url, normalized_key)
        q_plus = _is_q_plus(race_frame)
        race = _get_or_create_race(
            supabase,
            meeting_id=meeting["id"],
            source=source,
            race_type=race_type,
            source_url=source_url,
            race_key=normalized_key,
            rows=dataframe_records(race_frame),
            q_plus=q_plus,
        )
        persisted_races += 1
        races.append({"id": race["id"], "race_key": normalized_key, "url": source_url, "race_type": race_type, "q_plus": q_plus})
        for runner_index, row in enumerate(dataframe_records(race_frame), start=1):
            payload = {key: value for key, value in row.items() if key in (FLAT_COLUMNS if race_type == "flat" else TROT_COLUMNS)}
            payload["race_id"] = race["id"]
            payload.setdefault("N°", str(runner_index))
            payload["runner_number"] = payload["N°"]
            payload["raw_data"] = row
            supabase.upsert(
                runner_table,
                key="race_id",
                key_value=race["id"],
                payload=payload,
                on_conflict="race_id,runner_number",
            )
            persisted_runners += 1

    return {
        "meeting": meeting,
        "race_count": persisted_races,
        "runner_count": persisted_runners,
        "runner_table": runner_table,
        "races": races,
    }


def _runner_table(race_type: str) -> str:
    return FLAT_TABLE if race_type == "flat" else TROT_TABLE


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)


def _race_source_url(frame: pd.DataFrame, meeting_url: str, race_key: str) -> str:
    url_column = _first_column(frame, ("RACE_URL",))
    if url_column:
        values = frame[url_column].dropna()
        if not values.empty and str(values.iloc[0]).strip():
            return str(values.iloc[0])
    return f"{meeting_url}#race={race_key}"


def _is_q_plus(frame: pd.DataFrame) -> bool:
    if "Q+" not in frame.columns:
        return False
    values = frame["Q+"].map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
    return bool(values.any())


def _get_or_create_meeting(client: SupabaseClientWrapper, *, source: str, meeting_date: str, meeting_name: str | None, meeting_url: str) -> dict[str, Any]:
    existing = client.select_one("meetings", filters=[("source", "eq", source), ("url", "eq", meeting_url)], order_by=("created_at", "desc"))
    if existing:
        return existing
    return client.insert("meetings", {"source": source, "meeting_date": meeting_date, "name": meeting_name, "url": meeting_url, "metadata": {}})


def _get_or_create_race(client: SupabaseClientWrapper, *, meeting_id: str, source: str, race_type: str, source_url: str, race_key: str, rows: list[dict[str, Any]], q_plus: bool = False) -> dict[str, Any]:
    existing = client.select_one("races", filters=[("source_url", "eq", source_url)], order_by=("created_at", "desc"))
    payload = {
        "meeting_id": meeting_id,
        "source": source,
        "race_type": race_type,
        "source_url": source_url,
        "race_key": race_key,
        "raw_snapshot": {"rows": rows},
        "summary": {"runner_count": len(rows), "status": "scraped", "q_plus": q_plus},
        "status": "scraped",
    }
    if existing:
        return client.update("races", id_value=existing["id"], payload=payload)
    return client.insert("races", payload)