from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

from data_sources import data_source_manager
from model_functions import detect_race_type_from_html
from race_scraper_app import scrape_meeting_urls
from app.core.config import get_settings


def get_meetings(meeting_date: date, force_refresh: bool = False) -> dict:
    return scrape_meeting_urls(meeting_date, force_refresh=force_refresh)


def scrape_race(url: str, race_type: str, source: str = "zone-turf") -> pd.DataFrame:
    frame = data_source_manager.scrape_races(url, race_type, source_name=source)
    if frame is None:
        return pd.DataFrame()
    return frame


def detect_race_type(url: str) -> str:
    response = requests.get(url, timeout=get_settings().source_timeout_seconds)
    response.raise_for_status()
    return detect_race_type_from_html(BeautifulSoup(response.text, "html.parser"))
