from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from turfomania_race import (
    extract_track_from_multiple_parenthetical_items,
    fetch_race_html,
    scrape_turfomania_race,
)
from turfomania_reunions import HEADERS, TIMEOUT_SECONDS, _session, detect_race_type_from_text

QUINTE_URL = "https://www.turfomania.fr/quinte/"
QUINTE_TOMORROW_URL = "https://www.turfomania.fr/quinte/demain/"
logger = logging.getLogger(__name__)


def scrape_turfomania_quinte(
    meeting: dict[str, Any],
    frame: pd.DataFrame | None = None,
    *,
    url: str = QUINTE_URL,
) -> pd.DataFrame:
    """Scrape Quinté runners after verifying the selected meeting."""
    if meeting.get("source") != "turfomania":
        raise ValueError("Selected meeting is not a Turfomania meeting")

    source_frame = frame if frame is not None else _scrape_quinte_landing(url)
    return _validate_quinte_frame(meeting, source_frame)


def find_turfomania_quinte_meeting(
    meetings: list[dict[str, Any]],
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Scrape the current Quinté once and match it to today's stored meeting."""
    if not meetings:
        raise ValueError("No Turfomania meetings are available for today's Quinté")

    frame = _scrape_quinte_landing(QUINTE_URL)
    if frame.empty:
        raise ValueError("Turfomania Quinté page returned no runners")
    frame = _correct_track_from_title(frame)
    race_date_text = str(frame["RACE_DATE"].iloc[0] or "")
    try:
        race_date = datetime.strptime(race_date_text, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(
            f"Could not determine the Quinté race date from Turfomania: {race_date_text!r}"
        ) from exc
    race_track = str(frame["HIPPODROME"].iloc[0] or "")
    meeting = next(
        (
            item
            for item in meetings
            if item.get("meeting_date") == race_date.isoformat()
            and _same_track(race_track, str(item.get("name") or ""))
        ),
        None,
    )
    if not meeting:
        raise ValueError(
            f"No Turfomania meeting found for the Quinté at {race_track or 'an unknown track'} "
            f"on {race_date.isoformat()}"
        )
    frame = _validate_quinte_frame(meeting, frame)
    return meeting, frame


def _scrape_quinte_landing(url: str) -> pd.DataFrame:
    html = fetch_race_html(url)
    partants_url = _quinte_partants_url(html, landing_url=url)
    frame = scrape_turfomania_race(partants_url, None)
    if frame.empty:
        return frame

    expert_url = _quinte_expert_commentary_url(html, landing_url=url)
    frame.attrs["turfomania_expert_commentary"] = (
        _fetch_turfomania_expert_commentary(expert_url) if expert_url else None
    )
    return frame


def _quinte_partants_url(html: str, *, landing_url: str = QUINTE_URL) -> str:
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select(".onglets-bis-bloc.course-more-links .bis-cards a[href]")
    return (
        _validated_quinte_link_url(links[0] if links else None, "partants-", landing_url=landing_url)
        or landing_url
    )


def _quinte_expert_commentary_url(html: str, *, landing_url: str = QUINTE_URL) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select(".onglets-bis-bloc.course-more-links .bis-cards a[href]")
    return _validated_quinte_link_url(
        links[1] if len(links) > 1 else None,
        "pronostics-",
        landing_url=landing_url,
    )


def _validated_quinte_link_url(link, filename_prefix: str, *, landing_url: str) -> str | None:
    if link is None:
        return None
    url = urljoin(landing_url, str(link["href"]))
    parsed_url = urlparse(url)
    query = parse_qs(parsed_url.query)
    if (
        parsed_url.hostname not in {"turfomania.fr", "www.turfomania.fr"}
        or not parsed_url.path.startswith(f"/pronostics/{filename_prefix}")
        or not query.get("idcourse")
    ):
        return None
    return url


def _fetch_turfomania_expert_commentary(url: str) -> str | None:
    try:
        response = _session().get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Could not load Turfomania expert pronostic page: %s", url, exc_info=True)
        return None

    commentary = BeautifulSoup(response.text, "html.parser").select_one(".prono-commentaire")
    if commentary is None:
        return None
    text = "\n".join(line.strip() for line in commentary.get_text("\n").splitlines() if line.strip())
    return text or None


def _validate_quinte_frame(meeting: dict[str, Any], source_frame: pd.DataFrame) -> pd.DataFrame:
    meeting_date = date.fromisoformat(str(meeting["meeting_date"]))
    frame = source_frame
    if frame.empty:
        raise ValueError("Turfomania Quinté page returned no runners")
    frame = _correct_track_from_title(frame)

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
    if meeting_track and not _same_track(race_track, meeting_track):
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


def _correct_track_from_title(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "DESCRIPTIF" not in frame.columns:
        return frame
    track = extract_track_from_multiple_parenthetical_items(
        str(frame["DESCRIPTIF"].iloc[0] or "")
    )
    if not track:
        return frame
    corrected = frame.copy()
    corrected["HIPPODROME"] = track
    return corrected


def turfomania_quinte_race_type(frame: pd.DataFrame) -> str:
    text = " ".join(
        str(frame[col].iloc[0]) for col in ("RACE_CONDITIONS", "DESCRIPTIF") if col in frame.columns
    )
    detected = detect_race_type_from_text(text)
    if detected:
        return detected
    return "trot" if "POIDS" not in frame.columns else "flat"


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
