from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

from data_sources import data_source_manager
from model_functions import detect_race_type_from_html
from race_scraper_app import scrape_meeting_urls
from app.core.config import get_settings
from app.services.supabase_client import SupabaseClientWrapper
from app.services.turfomania_download import SOURCE as TURFOMANIA_SOURCE, turfomania_meeting_url


def get_meetings(meeting_date: date, force_refresh: bool = False) -> dict:
    # Each source is independently useful. A Zone-Turf outage must not hide
    # Turfomania meetings that were already catalogued in Supabase.
    try:
        meetings = scrape_meeting_urls(meeting_date, force_refresh=force_refresh)
    except Exception:
        meetings = {}
    meetings.update(_turfomania_meeting_options(meeting_date))
    return meetings


def _turfomania_meeting_options(meeting_date: date) -> dict[str, str]:
    """Catalog meetings persisted from the Turfomania réunion scraper.

    Réunion containers have no page URL of their own, so the option value is a
    synthetic turfomania://meetings/{id} reference resolved by the API.
    """
    try:
        client = SupabaseClientWrapper()
        rows = client.list(
            "meetings",
            filters=[("source", "eq", TURFOMANIA_SOURCE), ("meeting_date", "eq", meeting_date.isoformat())],
            limit=100,
        )
    except Exception:
        return {}
    options: dict[str, str] = {}
    for row in rows:
        name = (row.get("name") or "Réunion").strip()
        options[f"Turfomania · {name}"] = turfomania_meeting_url(row["id"])
    return options


def scrape_race(url: str, race_type: str, source: str = "zone-turf") -> pd.DataFrame:
    frame = data_source_manager.scrape_races(url, race_type, source_name=source)
    if frame is None:
        return pd.DataFrame()
    return frame


def detect_race_type(url: str) -> str:
    response = requests.get(url, timeout=get_settings().source_timeout_seconds)
    response.raise_for_status()
    return detect_race_type_from_html(BeautifulSoup(response.text, "html.parser"))
