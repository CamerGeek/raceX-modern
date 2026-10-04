from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

import app.services.turfomania_download as download_module
import turfomania_race
from model_functions import success_coefficient
from app.services.turfomania_download import download_turfomania_meeting
from turfomania_race import parse_runners
from bs4 import BeautifulSoup

MEETING = {"id": "m-1", "source": "turfomania", "meeting_date": "2026-09-30", "name": "R1 LAVAL", "url": None, "metadata": {}}


def test_success_coefficient_accepts_missing_discipline() -> None:
    assert success_coefficient("1p 2p", None) == 0.0


def test_parse_runners_accepts_a_table_without_tbody_or_tableau_line_class() -> None:
    soup = BeautifulSoup(
        '''<table><tr><th>N°</th><th>Cheval</th><th>Cote</th></tr>
        <tr><td><span class="num">4</span></td><td><a href="/cheval/demo"><b>DEMO HORSE</b></a><br>1p 2p</td><td>3,5</td></tr></table>''',
        "html.parser",
    )

    rows = parse_runners(soup, "flat", {"RACE_URL": "https://example.test"})

    assert rows == [{
        "RACE_URL": "https://example.test",
        "TABLE_INDEX": 2,
        "N°": "4",
        "CHEVAL": "DEMO HORSE",
        "MUSIQUE": "1p 2p",
        "DERNIÈRES PERF.": "1p 2p",
        "HORSE_LINK": "https://www.turfomania.fr/cheval/demo",
        "COTE": 3.5,
    }]


def test_parse_quinte_title_block_metadata() -> None:
    soup = BeautifulSoup(
        '''<div class="table-head-bloc-title">
        <div class="rc_big">R1C4<span class="specialQuinte">Spécial Quinté+</span></div>
        <div class="h2">QATAR PRIX DE LA PLACE DES VOSGES (LONGCHAMP)</div>
        <div class="date">Samedi 03 Octobre 2026 - 15h15</div>
        <div class="detail">Plat - Handicap Classe 1 - 2500 mètres</div>
        <span title="Quinté+">Q+</span></div>''',
        "html.parser",
    )

    metadata = turfomania_race.parse_race_metadata(
        soup,
        "https://www.turfomania.fr/quinte/",
    )

    assert metadata["REF_COURSE"] == "R1C4"
    assert metadata["DESCRIPTIF"] == "QATAR PRIX DE LA PLACE DES VOSGES (LONGCHAMP)"
    assert metadata["RACE_DATE"] == "03/10/2026"
    assert metadata["START_TIME"] == "15h15"
    assert metadata["HIPPODROME"] == "LONGCHAMP"
    assert metadata["DIST"] == 2500
    assert metadata["Q+"] is True


def test_fetch_race_html_returns_runner_page_from_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    request_html = '<table><tr><td><a href="/cheval/demo">DEMO</a></td></tr></table>'
    request_response = SimpleNamespace(text=request_html, raise_for_status=lambda: None)
    monkeypatch.setattr(
        turfomania_race,
        "_session",
        lambda: SimpleNamespace(get=lambda *_args, **_kwargs: request_response),
    )

    url = "https://www.turfomania.fr/pronostics/partants-demo.html"
    assert turfomania_race.fetch_race_html(url) == request_html


def test_fetch_race_html_rejects_request_page_without_runners(monkeypatch: pytest.MonkeyPatch) -> None:
    request_response = SimpleNamespace(text="<html>challenge</html>", raise_for_status=lambda: None)
    monkeypatch.setattr(
        turfomania_race,
        "_session",
        lambda: SimpleNamespace(get=lambda *_args, **_kwargs: request_response),
    )

    with pytest.raises(RuntimeError, match="no runners table"):
        turfomania_race.fetch_race_html("https://www.turfomania.fr/pronostics/partants-demo.html")


def _race(race_id: str, key: str, status: str, race_type: str = "trot", url: str | None = None, number: str | None = None) -> dict:
    return {
        "id": race_id,
        "meeting_id": "m-1",
        "race_key": key,
        "race_number": number,
        "race_type": race_type,
        "source_url": url or f"https://www.turfomania.fr/pronostics/partants-{key.lower()}.html?idcourse={race_id}",
        "status": status,
        "summary": {"status": status, "q_plus": False},
        "raw_snapshot": {},
    }


class _Client:
    def __init__(self, meeting: dict | None, races: list[dict]) -> None:
        self.meeting = meeting
        self.races = races
        self.race_updates: list[tuple[str, dict]] = []
        self.runner_upserts: list[tuple[str, dict, str | None]] = []

    def select_one(self, table: str, *, filters=None, **_: object) -> dict | None:
        if table == "meetings":
            return self.meeting
        if table == "races":
            wanted = {column: value for column, op, value in filters or [] if op == "eq"}
            return next((race for race in self.races if all(race.get(column) == value for column, value in wanted.items())), None)
        return None

    def list(self, table: str, *, filters=None, limit: int = 100, order_by=None) -> list[dict]:
        return list(self.races)

    def update(self, table: str, *, id_value: str, payload: dict) -> dict:
        if table == "races":
            self.race_updates.append((id_value, payload))
        return {"id": id_value, **payload}

    def insert(self, table: str, payload: dict) -> dict:
        raise AssertionError(f"unexpected insert into {table}")

    def upsert(self, table: str, *, key: str, key_value: object, payload: dict, on_conflict: str | None = None) -> dict:
        self.runner_upserts.append((table, payload, on_conflict))
        return {"id": "runner-1"}


def _fake_scrape(url: str, race_type: str, **kwargs) -> pd.DataFrame:
    _fake_scrape.calls.append((url, race_type))
    return pd.DataFrame(
        [
            {
                "N°": "1",
                "CHEVAL": "HORSE ONE",
                "MUSIQUE": "1a 2a",
                "DERNIÈRES PERF.": "1a 2a",
                "REC.": "1'12\"0",
                "REF_COURSE": "SCRAPED-KEY",
                "RACE_URL": url,
                "Q+": False,
            },
            {
                "N°": "2",
                "CHEVAL": "HORSE TWO",
                "MUSIQUE": "3a Da",
                "DERNIÈRES PERF.": "3a Da",
                "REC.": "1'13\"0",
                "REF_COURSE": "SCRAPED-KEY",
                "RACE_URL": url,
                "Q+": False,
            },
        ]
    )


_fake_scrape.calls: list[tuple[str, str]] = []


@pytest.fixture()
def fake_manager(monkeypatch: pytest.MonkeyPatch):
    _fake_scrape.calls.clear()
    manager = SimpleNamespace(scrape_races=_fake_scrape)
    monkeypatch.setattr(download_module, "data_source_manager", manager)
    return manager


def test_meeting_not_found() -> None:
    with pytest.raises(LookupError):
        download_turfomania_meeting("missing", client=_Client(None, []))


def test_rejects_non_turfomania_meeting() -> None:
    client = _Client({**MEETING, "source": "zone-turf", "url": "https://example.test"}, [])
    with pytest.raises(ValueError):
        download_turfomania_meeting("m-1", client=client)


def test_downloads_pending_races_and_skips_scraped(fake_manager) -> None:
    races = [
        _race("r-2", "R1C2", "pending", "trot", number="2"),
        _race("r-1", "R1C1", "pending", "flat", number="1"),
        _race("r-3", "R1C3", "scraped", "trot", number="3"),
    ]
    client = _Client(MEETING, races)

    result = download_turfomania_meeting("m-1", client=client)

    assert [call[0] for call in _fake_scrape.calls] == [races[1]["source_url"], races[0]["source_url"]]
    assert [call[1] for call in _fake_scrape.calls] == ["flat", "trot"]
    assert result["race_count"] == 2
    assert result["runner_count"] == 4
    assert result["skipped_count"] == 1
    assert len(result["races"]) == 3
    assert {race["id"] for race in result["races"]} == {"r-1", "r-2", "r-3"}

    updated_ids = {race_id for race_id, _ in client.race_updates}
    assert updated_ids == {"r-1", "r-2"}
    assert all(payload["status"] == "scraped" for _, payload in client.race_updates)

    assert len(client.runner_upserts) == 4
    tables = {table for table, _, _ in client.runner_upserts}
    assert tables == {"flat_race_runners", "trot_race_runners"}
    assert all(conflict == 'race_id,"N°"' for _, _, conflict in client.runner_upserts)

    trot_runners = [payload for table, payload, _ in client.runner_upserts if table == "trot_race_runners"]
    assert trot_runners[0]["race_id"] == "r-2"
    assert trot_runners[0]["raw_data"]["REF_COURSE"] == "R1C2"
    assert trot_runners[0]["raw_data"]["REF_COURSE"] != "SCRAPED-KEY"


def test_failed_race_is_marked_and_flow_continues(fake_manager, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_scrape(url: str, race_type: str, **kwargs) -> pd.DataFrame:
        if "partants-r1c1" in url:
            raise RuntimeError("boom")
        return _fake_scrape(url, race_type)

    monkeypatch.setattr(download_module, "data_source_manager", SimpleNamespace(scrape_races=failing_scrape))

    races = [_race("r-1", "R1C1", "pending", number="1"), _race("r-2", "R1C2", "pending", number="2")]
    client = _Client(MEETING, races)

    result = download_turfomania_meeting("m-1", client=client)

    assert result["race_count"] == 1
    assert result["failed"] == [{"race_key": "R1C1", "error": "boom"}]
    failed_update = next(payload for race_id, payload in client.race_updates if race_id == "r-1")
    assert failed_update["status"] == "failed"
    assert failed_update["summary"]["error"] == "boom"


def test_force_refresh_redownloads_scraped_race(fake_manager) -> None:
    races = [_race("r-1", "R1C1", "scraped", number="1")]
    client = _Client(MEETING, races)

    result = download_turfomania_meeting("m-1", force_refresh=True, client=client)

    assert result["race_count"] == 1
    assert result["skipped_count"] == 0
    assert len(_fake_scrape.calls) == 1


def test_cancel_stops_download(fake_manager) -> None:
    races = [_race("r-1", "R1C1", "pending", number="1"), _race("r-2", "R1C2", "pending", number="2")]
    client = _Client(MEETING, races)
    calls = {"count": 0}

    def cancel() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    result = download_turfomania_meeting("m-1", cancel_check=cancel, client=client)

    assert len(_fake_scrape.calls) == 1
    assert result["race_count"] == 1


def test_marks_non_partants_url_as_failed(fake_manager) -> None:
    client = _Client(MEETING, [_race("r-1", "R1C1", "pending", url="https://www.turfomania.fr/quinte/")])

    result = download_turfomania_meeting("m-1", client=client)

    assert _fake_scrape.calls == []
    assert result["failed"] == [{"race_key": "R1C1", "error": "race URL is not a Turfomania partants page"}]
    assert client.race_updates[0][1]["status"] == "failed"
