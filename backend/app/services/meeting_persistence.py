from __future__ import annotations

from datetime import date
import re
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
    "N°", "CHEVAL", "COTE", "DIST.", "SEXE", "AGE", "DERNIÈRES PERF.", "MUSIQUE",
    "REC.", "DEF.", "JOCKEY", "ENTRAINEUR", "JOCKEY_MUSIC", "TRAINER_MUSIC", "FORME_J", "FORME_T",
    "FA", "FM", "IF", "S_COEFF", "S_COEFF_norm", "disq_count", "disq_harness_rate",
    "disq_mounted_rate", "recent_disq_count", "recent_disq_rate", "DQ_Risk", "DQ_Risk_Amplified",
    "shoeing_aggressiveness", "HORSE_LINK", "RACE_URL",
    "RACE_DATE", "HIPPODROME", "REF_COURSE", "PRIZE_NAME", "DIST",
    "RACE_CONDITIONS", "DESCRIPTIF", "Q+", "TABLE_INDEX", "COURSE_ID", "MEETING_ID",
}

INTEGER_COLUMNS = {"AGE", "DIST.", "DIST", "TABLE_INDEX", "HIPPOID", "DSCP", "disq_count", "recent_disq_count"}
NUMERIC_COLUMNS = {
    "COTE", "POIDS", "PAST_POIDS", "FORME_J", "FORME_T", "FORME", "IF", "S_COEFF", "IC",
    "COMPOSITE_SCORE", "CLASS_ADVANTAGE", "J-DECH.", "N_WEIGHT", "ALLOCATION", "REC.", "FA", "FM",
    "S_COEFF_norm", "disq_harness_rate", "disq_mounted_rate", "recent_disq_rate", "DQ_Risk",
    "DQ_Risk_Amplified", "shoeing_aggressiveness", "STARTERS", "NUM_STARTERS", "DISTANCE",
    "HANDICAP_DISTANCE", "LICE", "G", "P", "M", "N", "R", "Q", "Q+"
}


def persist_scraped_meeting(
    frame: pd.DataFrame,
    *,
    meeting_date: date,
    meeting_name: str | None,
    meeting_url: str | None,
    race_type: str,
    source: str = "zone-turf",
    client: SupabaseClientWrapper | None = None,
    meeting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if race_type not in {"flat", "trot"}:
        raise ValueError("race_type must be flat or trot")
    if frame.empty:
        return {"meeting": meeting, "race_count": 0, "runner_count": 0, "runner_table": _runner_table(race_type), "races": []}

    supabase = client or SupabaseClientWrapper()
    if meeting is None:
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
            if race_type == "trot":
                row = _normalize_trot_row(row)
            payload = {key: value for key, value in row.items() if key in (FLAT_COLUMNS if race_type == "flat" else TROT_COLUMNS)}
            payload = _normalize_integer_columns(payload)
            payload["race_id"] = race["id"]
            payload.setdefault("N°", str(runner_index))
            payload["runner_number"] = payload["N°"]
            payload["raw_data"] = row
            supabase.upsert(
                runner_table,
                key="race_id",
                key_value=race["id"],
                payload=payload,
                on_conflict='race_id,"N°"',
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


def _normalize_integer_columns(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for column, value in list(normalized.items()):
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int):
            continue
        if isinstance(value, float):
            if column in INTEGER_COLUMNS:
                normalized[column] = int(value) if value.is_integer() else value
            continue

        if column not in INTEGER_COLUMNS and column not in NUMERIC_COLUMNS:
            continue

        text = str(value).strip().replace("\u00a0", " ")
        if not text or text in {"-", "—", "–", "--", "-.-"}:
            normalized[column] = None
            continue

        cleaned = text.replace(" ", "")
        if cleaned.endswith("m") and cleaned[:-1].replace("-", "").replace(".", "").replace(",", "").isdigit():
            cleaned = cleaned[:-1]

        cleaned = re.sub(r"[^0-9,\.\-]", "", cleaned)
        if not cleaned or cleaned in {"-", "--", "-."}:
            normalized[column] = None
            continue

        if cleaned.count(",") and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif cleaned.count(",") and cleaned.count("."):
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")

        if cleaned.startswith("-") and cleaned.count("-") == 1:
            cleaned = cleaned[1:]

        try:
            number = float(cleaned)
        except ValueError:
            normalized[column] = None
            continue

        if column in INTEGER_COLUMNS:
            normalized[column] = int(number) if number.is_integer() else number
        else:
            normalized[column] = number
    return normalized


def _normalize_trot_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if normalized.get("REC.") is not None:
        from model_functions import time_to_seconds

        value = normalized["REC."]
        if isinstance(value, str):
            normalized["REC."] = time_to_seconds(value)
    if not normalized.get("SEXE") and normalized.get("SEX"):
        normalized["SEXE"] = normalized["SEX"]
    if not normalized.get("MUSIQUE"):
        for source_column in ("DERNIÈRES PERF.", "DERNIÈRES PERF", "DERNIERES PERF.", "DERNIERES PERF", "PERFORMANCES"):
            if normalized.get(source_column):
                normalized["MUSIQUE"] = normalized[source_column]
                break
    performance = normalized.get("DERNIÈRES PERF.") or normalized.get("MUSIQUE")
    if performance:
        from model_functions import compute_d_perf, parse_performance_string, success_coefficient

        fitness = compute_d_perf(str(performance))
        if not normalized.get("FA"):
            normalized["FA"] = fitness.get("a")
        if not normalized.get("FM"):
            normalized["FM"] = fitness.get("m")
        if not normalized.get("IF"):
            normalized["IF"] = fitness.get("a") or fitness.get("m")
        if not normalized.get("S_COEFF"):
            normalized["S_COEFF"] = success_coefficient(str(performance), "a")
        parsed = parse_performance_string(str(performance))
        for column, value in parsed.items():
            if not normalized.get(column):
                normalized[column] = value.item() if hasattr(value, "item") else value
        if not normalized.get("DERNIÈRES PERF."):
            normalized["DERNIÈRES PERF."] = str(performance)
    return normalized


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
    existing = client.select_one(
        "meetings",
        filters=[("source", "eq", source), ("meeting_date", "eq", meeting_date), ("url", "eq", meeting_url)],
        order_by=("created_at", "desc"),
    )
    if existing:
        return existing
    return client.insert("meetings", {"source": source, "meeting_date": meeting_date, "name": meeting_name, "url": meeting_url, "metadata": {}})


def _get_or_create_race(client: SupabaseClientWrapper, *, meeting_id: str, source: str, race_type: str, source_url: str, race_key: str, rows: list[dict[str, Any]], q_plus: bool = False) -> dict[str, Any]:
    existing = client.select_one(
        "races",
        filters=[("meeting_id", "eq", meeting_id), ("race_key", "eq", race_key)],
        order_by=("created_at", "desc"),
    )
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