from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

import pandas as pd

from turfomania_race import scrape_turfomania_race

QUINTE_URL = "https://www.turfomania.fr/quinte/"


def scrape_turfomania_quinte(meeting: dict[str, Any]) -> pd.DataFrame:
    """Scrape today's Quinté runners after verifying the selected meeting."""
    if meeting.get("source") != "turfomania":
        raise ValueError("Selected meeting is not a Turfomania meeting")

    meeting_date = date.fromisoformat(str(meeting["meeting_date"]))
    frame = scrape_turfomania_race(QUINTE_URL, None)
    if frame.empty:
        raise ValueError("Turfomania Quinté page returned no runners")

    race_date_text = str(frame["RACE_DATE"].iloc[0] or "")
    try:
        race_date = datetime.strptime(race_date_text, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"Could not determine the Quinté race date from Turfomania: {race_date_text!r}") from exc
    if race_date != meeting_date:
        raise ValueError(
            f"Turfomania's Quinté is dated {race_date.isoformat()}, not {meeting_date.isoformat()}"
        )

    race_track = str(frame["HIPPODROME"].iloc[0] or "")
    meeting_track = str(meeting.get("name") or "")
    if not _same_track(race_track, meeting_track):
        raise ValueError(
            f"Turfomania's Quinté is at {race_track or 'an unknown track'}, "
            f"not {meeting_track or 'the selected meeting'}"
        )

    race_key = str(frame["REF_COURSE"].iloc[0] or "")
    if not re.fullmatch(r"R\d+C\d+", race_key, re.IGNORECASE):
        raise ValueError(f"Could not determine a valid Quinté race code: {race_key!r}")
    if "Q+" not in frame.columns or not frame["Q+"].map(_is_true).any():
        raise ValueError("Turfomania's current race is not marked as a Quinté+")

    frame = frame.copy()
    frame["REF_COURSE"] = race_key.upper()
    if "STARTERS" not in frame.columns or frame["STARTERS"].isna().all():
        frame["STARTERS"] = len(frame)
    return frame


def turfomania_quinte_race_type(frame: pd.DataFrame) -> str:
    return "flat" if "POIDS" in frame.columns else "trot"


def _same_track(first: str, second: str) -> bool:
    normalized_first = _normalize_track(first)
    normalized_second = _normalize_track(second)
    return bool(
        normalized_first
        and normalized_second
        and (
            normalized_first == normalized_second
            or normalized_first.endswith(normalized_second)
            or normalized_second.endswith(normalized_first)
        )
    )


def _normalize_track(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_value.casefold())


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}
