"""Scrape turfomania.fr réunion containers for the meeting/race catalog."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.turfomania.fr/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}

TIMEOUT_SECONDS = 20

TROT_DISCIPLINES = ("attelé", "monté")
OBSTACLE_DISCIPLINES = ("steeple-chase", "steeple", "haie", "cross", "obstacle", "hurdle")
FLAT_DISCIPLINES = (*OBSTACLE_DISCIPLINES, "plat")


def _clean(s):
    return re.sub(r"\s+", " ", s).strip()


def detect_race_type_from_text(text: str) -> str | None:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    normalized = re.sub(r"[-_/]+", " ", normalized)
    if re.search(r"\b(attele|monte)\b", normalized):
        return "trot"
    if re.search(r"\b(steeple(?:\s+chase)?|haies?|cross(?:\s+country)?|obstacles?|hurdles?)\b", normalized):
        return "obstacles"
    if re.search(r"\bplat\b", normalized):
        return "flat"
    return None


def _session():
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch(url=BASE_URL):
    r = _session().get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.text


def parse_card(card):
    """Extract one race card (a.card-course) inside a reunion container."""
    badges = [_clean(b.get_text()) for b in card.select(".badge-text")]
    name_el = card.select_one(".hippodrome")
    href = card.get("href", "")
    return {
        "code": " ".join(badges),
        "name": _clean(name_el.get_text()) if name_el else "",
        "href": (BASE_URL.rstrip("/") + href) if href.startswith("/") else href,
        "text": _clean(card.get_text(" ")),
    }


def _is_partants_url(url: str) -> bool:
    """Return whether a card points to an individual Turfomania race page."""
    return "/pronostics/partants-" in url and "idcourse=" in url


def parse_reunion(div):
    """Extract the contents of a single div.reunion-container."""
    header = div.select_one(".header-row")
    badge = header.select_one(".badge-text") if header else None
    title = header.select_one(".title") if header else None
    title_right = header.select_one(".titleRight") if header else None

    return {
        "reunion": _clean(badge.get_text()) if badge else "",
        "track": _clean(title.get_text()) if title else "",
        "header_right": _clean(title_right.get_text()) if title_right else "",
        "races": [
            card
            for element in div.find_all("a", class_="card-course")
            if _is_partants_url((card := parse_card(element))["href"])
        ],
    }


def scrape_reunions(url=BASE_URL):
    soup = BeautifulSoup(fetch(url), "html.parser")
    containers = soup.find_all("div", class_="reunion-container")
    return [parse_reunion(d) for d in containers]


def parse_race_details(text: str) -> dict[str, Any]:
    """Extract structured catalog details from a race card's text.

    Card text looks like:
    "R1 C1 Grand Prix Anjou-maine Attelé - Groupe III - 2850m - 100000 €
     15 partants Q+ GRP 3 13h55 Parier avec"
    """
    lowered = text.lower()
    distance = re.search(r"(\d{3,4})\s*m\b", text, re.IGNORECASE)
    prize = re.search(r"(\d[\d\s\u00a0]*)\s*€", text)
    starters = re.search(r"(\d+)\s*partants", text, re.IGNORECASE)
    start_time = re.search(r"\b(\d{1,2}h\d{2})\b", text, re.IGNORECASE)
    discipline = next((name for name in TROT_DISCIPLINES if name in lowered), None)
    if discipline is None:
        discipline = next((name for name in OBSTACLE_DISCIPLINES if name in lowered), None)
    if discipline is None:
        discipline = "plat" if detect_race_type_from_text(lowered) == "flat" else None
    race_type = detect_race_type_from_text(text) or "flat"

    return {
        "distance_m": int(distance.group(1)) if distance else None,
        "prize_eur": int(prize.group(1).replace(" ", "").replace("\u00a0", "")) if prize else None,
        "starters": int(starters.group(1)) if starters else None,
        "start_time": start_time.group(1) if start_time else None,
        "q_plus": "q+" in lowered,
        "discipline": discipline,
        "race_type": race_type,
    }
