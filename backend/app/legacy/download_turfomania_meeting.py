"""Download all runners from a Turfomania meeting into the legacy CSV schema."""

from __future__ import annotations

import argparse
import csv
import logging
import re
from threading import Lock
from time import monotonic, sleep
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry
import pandas as pd

from turfomania_race import detect_discipline, parse_race_metadata


BASE_URL = "https://www.turfomania.fr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}
OUTPUT_COLUMNS = [
    "N°", "CHEVAL", "Poids", "Dech.", "CORDE", "S/A", "JOCKEY",
    "ENTRAINEUR", "Gain", "OEILL.", "COTE", "date", "track",
    "descriptif", "ID_COURSE", "horse_ids", "jockey_ids", "trainer_ids",
    "horse_music", "jockey_music", "trainer_music", "INDICS",
]
REQUEST_INTERVAL_SECONDS = 1.5
LOGGER = logging.getLogger(__name__)


class RateLimitedRequester:
    def __init__(self, minimum_interval: float = REQUEST_INTERVAL_SECONDS):
        self.minimum_interval = minimum_interval
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self._lock = Lock()
        self._last_request_finished = 0.0

    def get(self, url: str) -> requests.Response:
        with self._lock:
            delay = self.minimum_interval - (monotonic() - self._last_request_finished)
            if delay > 0:
                sleep(delay)
            try:
                response = self.session.get(url, headers=HEADERS, timeout=30)
            finally:
                self._last_request_finished = monotonic()
        response.raise_for_status()
        return response


REQUESTER = RateLimitedRequester()


def clean_text(value: str) -> str:
    return " ".join(value.split())


def request_soup(url: str) -> BeautifulSoup:
    response = REQUESTER.get(url)
    return BeautifulSoup(response.content, "html.parser")


def profile_fields(url: str) -> dict[str, str]:
    try:
        soup = request_soup(url)
    except requests.RequestException as exc:
        LOGGER.warning("Unable to fetch profile %s: %s", url, exc)
        return {"music": "", "indics": ""}

    text = clean_text(soup.get_text(" ", strip=True))
    music_match = re.search(r"\bMusique\s+(.+?)\s+Ecart gagnant\b", text, re.IGNORECASE)
    form_match = re.search(
        r"(Indice de forme\s+\S+\s+Dernière sortie\s+\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    evolution_match = re.search(
        r"(Evolution cotations\s*:\s*.*?)(?=\s+Engagement en cours|\s+Courses\b|$)",
        text,
        re.IGNORECASE,
    )
    indicators = [match.group(1).strip() for match in (form_match, evolution_match) if match]
    return {
        "music": clean_text(music_match.group(1)) if music_match else "",
        "indics": " | ".join(indicators),
    }


def meeting_race_urls(soup: BeautifulSoup) -> list[str]:
    urls = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/pronostics/partants-" not in href or "idcourse=" not in href:
            continue
        absolute_url = urljoin(BASE_URL, href)
        if absolute_url not in seen:
            seen.add(absolute_url)
            urls.append(absolute_url)
    return urls


def race_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        if "tableauLine" in table.get("class", []) and table.select_one('a[href^="/cheval/"]'):
            return table
    return None


def cell_text(cells, headers: list[str], match: str) -> str:
    index = next((i for i, header in enumerate(headers) if match in header.lower()), None)
    if index is None or index >= len(cells):
        return ""
    return clean_text(cells[index].get_text(" ", strip=True))


def id_from_link(href: str, key: str) -> str:
    values = parse_qs(urlparse(href).query).get(key, [])
    if values:
        return values[0]
    match = re.search(r"_(\d+)$", urlparse(href).path)
    return match.group(1) if match else ""


def number_or_none(value: str) -> float | None:
    normalized = value.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    match = re.search(r"[+-]?\d+(?:\.\d+)?", normalized)
    return float(match.group(0)) if match else None


def parse_race(url: str, track: str, race_date: str, meeting_description: str) -> list[dict[str, str]]:
    soup = request_soup(url)
    table = race_table(soup)
    if table is None:
        raise RuntimeError(f"No runners table found at {url}")

    headers = [clean_text(th.get_text(" ", strip=True)).lower() for th in table.select("thead th")]
    race_id = parse_qs(urlparse(url).query).get("idcourse", [""])[0]
    detail = soup.select_one(".detailCourseCaract") or soup.select_one(".detailCourseCaract2-pictos")
    descriptif = clean_text(detail.get_text(" ", strip=True)) if detail else meeting_description
    descriptif = re.sub(r"^Conditions de course\s*:\s*", "", descriptif, flags=re.IGNORECASE)
    metadata = parse_race_metadata(soup, url)
    conditions = metadata.get("RACE_CONDITIONS", "")
    race_type = detect_discipline(conditions) or "flat"
    rows = []

    for tr in table.select("tbody tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        horse_link = tr.find("a", href=re.compile(r"^/cheval/"))
        connections = tr.find("td", class_="jockey")
        jockey_link = connections.find("a", href=re.compile(r"/fiches/jockeys/")) if connections else None
        trainer_link = connections.find("a", href=re.compile(r"/fiches/entraineurs/")) if connections else None
        horse_name = clean_text(horse_link.get_text(" ", strip=True)) if horse_link else cell_text(cells, headers, "cheval")
        horse_index = next((i for i, header in enumerate(headers) if "cheval" in header), None)
        horse_cell = cells[horse_index] if horse_index is not None and horse_index < len(cells) else None
        horse_music = clean_text(horse_cell.get_text(" ", strip=True)) if horse_cell else ""
        if horse_name:
            horse_music = re.sub(rf"^{re.escape(horse_name)}\s*", "", horse_music)
        sex_age = cell_text(cells, headers, "s/a")
        sex_age_match = re.match(r"\s*([A-Za-z])\s*(\d+)", sex_age)
        number = cell_text(cells, headers, "n°")
        horse_url = urljoin(BASE_URL, horse_link["href"]) if horse_link else ""

        rows.append({
            "N°": number,
            "CHEVAL": horse_name,
            "Poids": cell_text(cells, headers, "poids"),
            "Dech.": cell_text(cells, headers, "déch") or cell_text(cells, headers, "dech"),
            "CORDE": cell_text(cells, headers, "corde"),
            "S/A": cell_text(cells, headers, "s/a"),
            "JOCKEY": clean_text(jockey_link.get_text(" ", strip=True)) if jockey_link else "",
            "ENTRAINEUR": clean_text(trainer_link.get_text(" ", strip=True)) if trainer_link else "",
            "Gain": cell_text(cells, headers, "gain"),
            "OEILL.": cell_text(cells, headers, "oe."),
            "COTE": cell_text(cells, headers, "cote pmu"),
            "date": race_date,
            "track": track,
            "descriptif": descriptif,
            "ID_COURSE": race_id,
            "horse_ids": id_from_link(horse_link["href"], "") if horse_link else "",
            "jockey_ids": id_from_link(jockey_link["href"], "idjockey") if jockey_link else "",
            "trainer_ids": id_from_link(trainer_link["href"], "identraineur") if trainer_link else "",
            "horse_music": horse_music,
            "jockey_music": "",
            "trainer_music": "",
            "INDICS": "",
            "REF_COURSE": metadata.get("REF_COURSE") or race_id,
            "RACE_URL": url,
            "RACE_DATE": metadata.get("RACE_DATE") or race_date,
            "HIPPODROME": track or metadata.get("HIPPODROME", ""),
            "PRIZE_NAME": metadata.get("DESCRIPTIF") or descriptif,
            "RACE_CONDITIONS": conditions,
            "DESCRIPTIF": metadata.get("DESCRIPTIF") or descriptif,
            "Q+": bool(metadata.get("Q+")),
            "TABLE_INDEX": int(number) if number.isdigit() else None,
            "COURSE_ID": race_id,
            "STARTERS": metadata.get("STARTERS"),
            "ALLOCATION": metadata.get("ALLOCATION"),
            "DIST": metadata.get("DIST"),
            "POIDS": number_or_none(cell_text(cells, headers, "poids")),
            "SEXE": sex_age_match.group(1).upper() if sex_age_match else "",
            "AGE": int(sex_age_match.group(2)) if sex_age_match else None,
            "MUSIQUE": horse_music,
            "JOCKEY_MUSIC": "",
            "TRAINER_MUSIC": "",
            "HORSE_LINK": horse_url,
            "_RACE_TYPE": race_type,
            "_horse_url": horse_url,
            "_jockey_url": urljoin(BASE_URL, jockey_link["href"]) if jockey_link else "",
            "_trainer_url": urljoin(BASE_URL, trainer_link["href"]) if trainer_link else "",
        })
    return rows


def scrape_meeting_rows(meeting_url: str, *, enrich_profiles: bool = False) -> tuple[dict[str, str], list[dict[str, str]]]:
    meeting_soup = request_soup(meeting_url)
    meeting_title = meeting_soup.title.get_text(" ", strip=True) if meeting_soup.title else ""
    track_match = re.search(r":\s*([^-]+?)\s*-\s*Réunion\b", meeting_title, re.IGNORECASE)
    date_match = re.search(
        r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})",
        meeting_title,
        re.IGNORECASE,
    )
    track = track_match.group(1).strip() if track_match else ""
    race_date = f"{int(date_match.group(1))} {date_match.group(2).lower()} {date_match.group(3)}" if date_match else ""
    tables = [
        table for table in meeting_soup.find_all("table")
        if {"tableauLine", "fs-13", "wrap", "tableauPartants"}.issubset(set(table.get("class", [])))
    ]
    race_urls = meeting_race_urls(meeting_soup)
    if not tables or len(tables) != len(race_urls):
        raise RuntimeError(f"Found {len(tables)} meeting tables and {len(race_urls)} partants links")

    all_rows = []
    for index, race_url in enumerate(race_urls):
        heading = tables[index].find_previous(["h2", "h3", "h4"])
        meeting_description = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        rows = parse_race(race_url, track, race_date, meeting_description)
        all_rows.extend(rows)
        race_id = parse_qs(urlparse(race_url).query).get("idcourse", [""])[0]
        print(f"Race {index + 1}: {len(rows)} runners, course {race_id}")

    profile_data = {}
    if enrich_profiles:
        profile_urls = {
            url
            for row in all_rows
            for url in (row["_horse_url"], row["_jockey_url"], row["_trainer_url"])
            if url
        }
        profile_data = {url: profile_fields(url) for url in profile_urls}

    for row in all_rows:
        horse = profile_data.get(row.pop("_horse_url"), {})
        jockey = profile_data.get(row.pop("_jockey_url"), {})
        trainer = profile_data.get(row.pop("_trainer_url"), {})
        row["INDICS"] = horse.get("indics", "")
        row["jockey_music"] = jockey.get("music", "")
        row["trainer_music"] = trainer.get("music", "")
        row["JOCKEY_MUSIC"] = row["jockey_music"]
        row["TRAINER_MUSIC"] = row["trainer_music"]

    return {"title": meeting_title, "track": track, "date": race_date}, all_rows


def download_meeting(meeting_url: str, output_path: Path) -> int:
    _, all_rows = scrape_meeting_rows(meeting_url, enrich_profiles=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Saved {len(all_rows)} runners from {len(race_urls)} races to {output_path.resolve()}")
    return len(all_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("meeting_url")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=REQUEST_INTERVAL_SECONDS,
        help="Minimum seconds between requests (default: 1.5)",
    )
    args = parser.parse_args()
    if args.request_interval < 0:
        parser.error("--request-interval must be zero or greater")
    REQUESTER.minimum_interval = args.request_interval
    meeting_id = parse_qs(urlparse(args.meeting_url).query).get("idreunion", ["meeting"])[0]
    output_path = args.output or Path(f"turfomania_meeting_{meeting_id}.csv")
    download_meeting(args.meeting_url, output_path)


if __name__ == "__main__":
    main()