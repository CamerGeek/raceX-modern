from __future__ import annotations

import pandas as pd
import pytest

import app.api.races as races_api
import app.services.turfomania_quinte as quinte_module
from app.schemas.races import AnalysisResponse, TurfomaniaQuinteAnalysisRequest
from app.services.turfomania_quinte import scrape_turfomania_quinte, turfomania_quinte_race_type

MEETING = {
    "id": "meeting-1",
    "source": "turfomania",
    "meeting_date": "2026-10-03",
    "name": "Longchamp",
}


def _frame(
    *,
    race_date: str = "03/10/2026",
    track: str = "LONGCHAMP",
    race_key: str = "R1C4",
    q_plus: bool = True,
) -> pd.DataFrame:
    return pd.DataFrame(
        [{
            "RACE_DATE": race_date,
            "HIPPODROME": track,
            "REF_COURSE": race_key,
            "Q+": q_plus,
            "POIDS": 55.0,
            "N°": "1",
            "CHEVAL": "TEST HORSE",
        }]
    )


def test_scrape_quinte_accepts_matching_meeting(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_scrape(url: str, race_type: str | None) -> pd.DataFrame:
        calls.append((url, race_type))
        return _frame()

    monkeypatch.setattr(quinte_module, "scrape_turfomania_race", fake_scrape)

    result = scrape_turfomania_quinte(MEETING)

    assert calls == [(quinte_module.QUINTE_URL, None)]
    assert result["REF_COURSE"].tolist() == ["R1C4"]
    assert result["STARTERS"].tolist() == [1]
    assert turfomania_quinte_race_type(result) == "flat"
    assert turfomania_quinte_race_type(result.drop(columns=["POIDS"])) == "trot"


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (_frame(race_date="02/10/2026"), "dated 2026-10-02"),
        (_frame(track="VINCENNES"), "not Longchamp"),
        (_frame(q_plus=False), "not marked as a Quinté"),
        (_frame(race_key="684516"), "valid Quinté race code"),
    ],
)
def test_scrape_quinte_rejects_mismatched_or_unidentified_race(
    monkeypatch: pytest.MonkeyPatch,
    frame: pd.DataFrame,
    message: str,
) -> None:
    monkeypatch.setattr(quinte_module, "scrape_turfomania_race", lambda *_args: frame)

    with pytest.raises(ValueError, match=message):
        scrape_turfomania_quinte(MEETING)


def test_scrape_quinte_rejects_non_turfomania_meeting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        quinte_module,
        "scrape_turfomania_race",
        lambda *_args: pytest.fail("scraper should not run for another source"),
    )

    with pytest.raises(ValueError, match="not a Turfomania meeting"):
        scrape_turfomania_quinte({**MEETING, "source": "zone-turf"})


def test_quinte_analysis_endpoint_persists_and_returns_race_id(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def select_one(self, *_args: object, **_kwargs: object) -> dict:
            return MEETING

        def insert(self, *_args: object, **_kwargs: object) -> dict:
            return {}

    client = Client()
    frame = _frame()
    monkeypatch.setattr(races_api, "SupabaseClientWrapper", lambda: client)
    monkeypatch.setattr(races_api, "scrape_turfomania_quinte", lambda _meeting: frame)

    def persist(*_args: object, **kwargs: object) -> dict:
        assert kwargs["meeting"] == MEETING
        assert kwargs["race_type"] == "flat"
        return {"races": [{"id": "race-quinte"}]}

    monkeypatch.setattr(races_api, "persist_scraped_meeting", persist)
    monkeypatch.setattr(
        races_api,
        "_analysis_response",
        lambda *_args, **_kwargs: AnalysisResponse(
            race_type="flat",
            source="turfomania",
            row_count=1,
            columns=[],
            rows=[],
            model_version="test",
            prognosis=[],
        ),
    )

    result = races_api.analyze_turfomania_quinte(
        TurfomaniaQuinteAnalysisRequest(meeting_id="meeting-1")
    )

    assert result.race_id == "race-quinte"
    assert result.source == "turfomania"


def test_today_quinte_analysis_reuses_cached_response(monkeypatch: pytest.MonkeyPatch) -> None:
    meeting = {**MEETING, "meeting_date": "2026-10-03"}

    class Client:
        def __init__(self) -> None:
            self.races: list[dict] = []
            self.analysis_runs: list[dict] = []

        def list(self, table: str, *, filters: list[tuple[str, str, object]], **_: object) -> list[dict]:
            if table == "meetings":
                return [meeting]
            if table == "races":
                return self.races
            raise AssertionError(f"unexpected list table: {table}")

        def select_one(self, table: str, *, filters: list[tuple[str, str, object]], **_: object) -> dict | None:
            race_id = next(value for column, _, value in filters if column == "race_id")
            if table == "analysis_runs":
                return next((run for run in reversed(self.analysis_runs) if run["race_id"] == race_id), None)
            if table == "flat_race_runners":
                return {"updated_at": "2026-10-03T10:00:00+00:00"}
            raise AssertionError(f"unexpected select table: {table}")

        def insert(self, table: str, payload: dict) -> dict:
            if table == "analysis_runs":
                run = {**payload, "created_at": "2026-10-03T10:00:00+00:00"}
                self.analysis_runs.append(run)
                return run
            raise AssertionError(f"unexpected insert table: {table}")

    client = Client()
    monkeypatch.setattr(races_api, "SupabaseClientWrapper", lambda: client)
    monkeypatch.setattr(
        races_api,
        "find_turfomania_quinte_meeting",
        lambda _meetings: (meeting, _frame()),
    )

    def persist(*_args: object, **_kwargs: object) -> dict:
        race = {
            "id": "race-today",
            "source": "turfomania",
            "race_type": "flat",
            "summary": {"q_plus": True},
        }
        client.races = [race]
        return {"races": [{"id": race["id"]}]}

    monkeypatch.setattr(races_api, "persist_scraped_meeting", persist)
    analysis_calls = 0

    def analyze(*_args: object, **_kwargs: object) -> AnalysisResponse:
        nonlocal analysis_calls
        analysis_calls += 1
        return AnalysisResponse(
            race_type="flat",
            source="turfomania",
            row_count=1,
            columns=["N°", "CHEVAL", "Composite"],
            rows=[{"N°": "1", "CHEVAL": "TEST HORSE", "Composite": 0.9}],
            model_version="initial-migration",
            prognosis=[],
        )

    monkeypatch.setattr(races_api, "_analysis_response", analyze)
    request = races_api.TodayQuinteAnalysisRequest(date="2026-10-03")

    first = races_api.analyze_today_turfomania_quinte(request)
    second = races_api.analyze_today_turfomania_quinte(request)

    assert first.race_id == "race-today"
    assert second.model_dump() == first.model_dump()
    assert analysis_calls == 1
    assert len(client.analysis_runs) == 1
