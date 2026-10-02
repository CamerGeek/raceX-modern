"""Scrape a Turfomania 'partants' page into an analysis-ready runners DataFrame."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from model_functions import (
    bayesian_performance_score,
    clean_distance,
    clean_ref_course,
    success_coefficient,
)
from turfomania_reunions import (
    BASE_URL,
    FLAT_DISCIPLINES,
    HEADERS,
    TIMEOUT_SECONDS,
    TROT_DISCIPLINES,
    _clean,
    _session,
)

FRENCH_MONTHS = {
    "janvier": "01", "février": "02", "fevrier": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08", "aout": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12", "decembre": "12",
}

FLAT_SEX_MAP = {"H": 0, "M": 1, "F": 2}
DISC_MAP = {1: "p", 2: "s", 3: "h", 4: "c"}


def fetch_race_html(url: str) -> str:
    try:
        response = _session().get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Could not load Turfomania race page: {exc}") from exc
    if not _has_runner_table(response.text):
        raise RuntimeError("Turfomania page loaded, but no runners table was found")
    return response.text


def _has_runner_table(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(".table-head-bloc-title"):
        return True
    return any(table.select_one('a[href^="/cheval/"]') for table in soup.find_all("table"))


def detect_discipline(conditions_text: str) -> str | None:
    lowered = (conditions_text or "").lower()
    if any(d in lowered for d in TROT_DISCIPLINES):
        return "trot"
    if any(d in lowered for d in FLAT_DISCIPLINES):
        return "flat"
    return None


def parse_race_metadata(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    title_block = soup.find("div", class_="table-head-bloc-title")
    h1 = title_block.find("h1") if title_block else soup.find("h1")
    h2 = soup.find("h2", class_="date")
    title = soup.find("title")
    conditions_div = soup.select_one("div.detailCourseCaract2-pictos")

    conditions = _clean(conditions_div.get_text(" ")) if conditions_div else ""
    descriptif = _clean(h1.get_text()) if h1 else ""
    if not conditions and title_block:
        detail = title_block.find("div", class_="detail")
        conditions = _clean(detail.get_text(" ")) if detail else ""
    if not descriptif:
        old_detail = soup.find("div", class_="detailCourseCaract")
        descriptif = _clean(old_detail.get_text(" ")) if old_detail else ""
    header2 = _clean(h2.get_text()) if h2 else ""
    hippodrome = ""
    if title and "-" in title.get_text():
        hippodrome = _clean(title.get_text().split("-")[-1])

    ref_course = None
    match = re.search(r"R(\d+)\s*C(\d+)", header2, re.IGNORECASE)
    if match:
        ref_course = f"R{match.group(1)}C{match.group(2)}"
    elif header2:
        ref_course = clean_ref_course(header2)

    race_date = None
    start_time = None
    match = re.search(r"(\d{1,2})\s+([A-Za-zéû]+)\s+(\d{4})", header2)
    if match:
        day, month_name, year = match.groups()
        month = FRENCH_MONTHS.get(month_name.lower())
        if month:
            race_date = f"{int(day):02d}/{month}/{year}"
    match = re.search(r"\b(\d{1,2}h\d{2})\b", header2)
    if match:
        start_time = match.group(1)

    distance = None
    match = re.search(r"(\d[\d\s\u00a0]*)\s*m\b", conditions)
    if match:
        distance = clean_distance(match.group(1))

    allocation = None
    match = re.search(r"([\d\s\u00a0]+)\s*€", conditions)
    if match:
        digits = re.sub(r"\D", "", match.group(1))
        allocation = int(digits) if digits else None

    starters = None
    match = re.search(r"(\d+)\s*partants", conditions, re.IGNORECASE)
    if match:
        starters = int(match.group(1))

    return {
        "DESCRIPTIF": descriptif,
        "REF_COURSE": ref_course,
        "RACE_DATE": race_date,
        "START_TIME": start_time,
        "HIPPODROME": hippodrome,
        "RACE_CONDITIONS": conditions,
        "DIST": distance,
        "ALLOCATION": allocation,
        "STARTERS": starters,
        "Q+": ("quinté" in conditions.lower()) or ("quinte" in conditions.lower()),
        "RACE_URL": url,
    }


def _header_roles(table) -> list[str]:
    roles = []
    headers = table.select("thead th")
    if not headers:
        # Some Turfomania cards render the header as the first row instead of
        # inside a thead.
        header_row = table.find("tr")
        headers = header_row.find_all(["th", "td"], recursive=False) if header_row else []
    for th in headers:
        text = _clean(th.get_text(" ")).lower()
        if text.startswith("n°"):
            roles.append("num")
        elif "cheval" in text:
            roles.append("cheval")
        elif text.startswith("dist"):
            roles.append("dist")
        elif text.startswith("def"):
            roles.append("def")
        elif text.startswith("poids"):
            roles.append("poids")
        elif "déch" in text or "dech" in text:
            roles.append("dech")
        elif text.startswith("corde"):
            roles.append("corde")
        elif text.startswith("s/a"):
            roles.append("sa")
        elif "driver" in text or "jockey" in text:
            roles.append("jockey")
        elif text.startswith("record"):
            roles.append("record")
        elif text.startswith("gain"):
            roles.append("gain")
        elif text.startswith("oe"):
            roles.append("oeill")
        elif "cote" in text:
            roles.append("cote")
        else:
            roles.append("skip")
    return roles


def _parse_num(td) -> str:
    span = td.select_one("span.num")
    return _clean(span.get_text()) if span else _clean(td.get_text())


def _parse_cheval(td):
    link = td.find("a", href=re.compile(r"^/cheval/"))
    name = ""
    href = ""
    horse_id = None
    if link:
        bold = link.find("b")
        name = _clean(bold.get_text()) if bold else _clean(link.get_text())
        href = link.get("href", "")
        match = re.search(r":\s*(\d+)\s*$", link.get("title", ""))
        if match:
            horse_id = match.group(1)
    music = ""
    br = td.find("br")
    if br is not None and br.next_sibling is not None:
        music = _clean(str(br.next_sibling))
    horse_link = (BASE_URL.rstrip("/") + href) if href.startswith("/") else href
    return name, music, horse_link, horse_id


def _parse_jockey_trainer(td):
    links = td.find_all("a")
    jockey = _clean(links[0].get_text()) if len(links) >= 1 else ""
    trainer = _clean(links[1].get_text()) if len(links) >= 2 else ""
    return jockey, trainer


def _parse_gain(td):
    raw = td.get("data-text")
    digits = re.sub(r"\D", "", raw) if raw else re.sub(r"\D", "", td.get_text())
    return int(digits) if digits else 0


def _parse_cote(td):
    span = td.find("span")
    text = _clean(span.get_text()) if span else _clean(td.get_text())
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _parse_weight(text):
    text = _clean(text).replace(",", ".")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_intish(text):
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def _split_sa(text):
    match = re.match(r"\s*([A-Za-z]+)\s*(\d+)", text or "")
    if not match:
        return "", None
    return match.group(1).upper(), int(match.group(2))


def parse_runners(soup: BeautifulSoup, race_type: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
    table = soup.find("table", class_="tableauLine")
    if table is None:
        # Turfomania has used multiple table classes. A runners table is
        # reliably identifiable by its links to individual horse profiles.
        table = next((candidate for candidate in soup.find_all("table") if candidate.select_one('a[href^="/cheval/"]')), None)
    if table is None:
        return []
    roles = _header_roles(table)
    if not roles:
        return []
    rows = []
    tbody = table.find("tbody")
    trs = tbody.find_all("tr", recursive=False) if tbody else table.find_all("tr")
    for index, tr in enumerate(trs):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        row: dict[str, Any] = dict(meta)
        row["TABLE_INDEX"] = index + 1
        for role, td in zip(roles, tds):
            if role == "num":
                row["N°"] = _parse_num(td)
            elif role == "cheval":
                name, music, horse_link, horse_id = _parse_cheval(td)
                row["CHEVAL"] = name
                row["MUSIQUE"] = music
                row["DERNIÈRES PERF."] = music
                row["HORSE_LINK"] = horse_link
                if horse_id:
                    row["HORSE_ID"] = horse_id
            elif role == "dist":
                row["DIST."] = clean_distance(td.get_text())
            elif role == "def":
                row["DEF."] = _clean(td.get_text())
            elif role == "poids":
                row["POIDS"] = _parse_weight(td.get_text())
            elif role == "dech":
                row["J-DECH."] = _clean(td.get_text())
            elif role == "corde":
                row["CORDE"] = _parse_intish(td.get_text())
            elif role == "sa":
                sex, age = _split_sa(td.get_text())
                row["SEXE"] = FLAT_SEX_MAP.get(sex, sex) if race_type == "flat" else sex
                row["AGE"] = age
            elif role == "jockey":
                jockey, trainer = _parse_jockey_trainer(td)
                row["JOCKEY"] = jockey
                row["ENTRAINEUR"] = trainer
            elif role == "record":
                row["REC."] = _clean(td.get_text())
            elif role == "gain":
                row["GAIN"] = _parse_gain(td)
            elif role == "oeill":
                row["OEILL."] = _clean(td.get_text())
            elif role == "cote":
                row["COTE"] = _parse_cote(td)
        if row.get("N°") and row.get("CHEVAL"):
            rows.append(row)
    return rows


def _extract_dscp(conditions: str):
    text = (conditions or "").lower()
    if "plat" in text:
        return 1
    if "steeple" in text:
        return 2
    if "cross" in text:
        return 4
    if "haies" in text:
        return 3
    return None


def _add_flat_derived(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conditions = rows[0].get("RACE_CONDITIONS", "") if rows else ""
    dscp = _extract_dscp(conditions)
    disc_char = DISC_MAP.get(dscp) if dscp else None
    for row in rows:
        music = row.get("MUSIQUE") or ""
        poids = row.get("POIDS")
        cote = row.get("COTE")
        row["DSCP"] = dscp
        try:
            row["IC"] = round(float(poids) - float(cote), 1) if poids is not None and cote is not None else None
        except (TypeError, ValueError):
            row["IC"] = None
        forme = bayesian_performance_score(music)
        row["FORME"] = forme
        row["IF"] = round(forme, 2) if forme is not None else None
        if not music.strip():
            row["S_COEFF"] = bayesian_performance_score("")
        else:
            coefficient = success_coefficient(music, disc_char)
            row["S_COEFF"] = coefficient if coefficient else bayesian_performance_score(music)
    return rows


def scrape_turfomania_race(url, race_type=None, progress_callback=None, cancel_check=None) -> pd.DataFrame:
    html = fetch_race_html(url)
    soup = BeautifulSoup(html, "html.parser")
    meta = parse_race_metadata(soup, url)
    if race_type is None:
        race_type = detect_discipline(meta.get("RACE_CONDITIONS", "")) or "flat"
    if progress_callback:
        progress_callback(20, f"Parsed race metadata ({race_type})")
    rows = parse_runners(soup, race_type, meta)
    if cancel_check and cancel_check():
        return pd.DataFrame()
    if race_type == "flat":
        rows = _add_flat_derived(rows)
    if progress_callback:
        progress_callback(100, f"Scraped {len(rows)} runners")
    return pd.DataFrame(rows)


def scrape_turfomania_flat(url, progress_callback=None, cancel_check=None) -> pd.DataFrame:
    return scrape_turfomania_race(url, "flat", progress_callback, cancel_check)


def scrape_turfomania_trot(url, progress_callback=None, cancel_check=None) -> pd.DataFrame:
    return scrape_turfomania_race(url, "trot", progress_callback, cancel_check)
