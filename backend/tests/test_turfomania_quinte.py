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


def test_quinte_race_type_uses_obstacle_conditions_before_missing_weight_heuristic() -> None:
    frame = _frame().drop(columns=["POIDS"])
    frame["RACE_CONDITIONS"] = "Haies - 3600 mètres"

    assert turfomania_quinte_race_type(frame) == "obstacles"


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

        def list(self, *_args: object, **_kwargs: object) -> list[dict]:
            return []

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
    cached = races_api.TurfomaniaQuinteAnalysisResponse(
        race_id="race-today",
        race_type="flat",
        source="turfomania",
        row_count=1,
        columns=["N°", "CHEVAL", "Composite"],
        rows=[{"N°": "1", "CHEVAL": "TEST HORSE", "Composite": 0.9}],
        model_version="initial-migration",
        prognosis=[],
    )
    race = {
        "id": "race-today",
        "source": "turfomania",
        "race_type": "flat",
        "summary": {"q_plus": True},
    }
    analysis_run = {
        "race_id": race["id"],
        "created_at": "2026-10-03T10:00:00+00:00",
        "summary": {
            "homepage_cache_version": races_api.HOMEPAGE_QUINTE_CACHE_VERSION,
            "homepage_analysis": cached.model_dump(mode="json"),
        },
    }

    class Client:
        def list(self, table: str, *, filters: list[tuple[str, str, object]], **_: object) -> list[dict]:
            if table == "meetings":
                return [meeting]
            if table == "races":
                return [race]
            if table == "analysis_runs":
                return [analysis_run]
            raise AssertionError(f"unexpected list table: {table}")

        def select_one(self, table: str, *, filters: list[tuple[str, str, object]], **_: object) -> dict | None:
            if table == "flat_race_runners":
                return {"updated_at": "2026-10-03T10:00:00+00:00"}
            raise AssertionError(f"unexpected select table: {table}")

    client = Client()
    monkeypatch.setattr(races_api, "SupabaseClientWrapper", lambda: client)
    monkeypatch.setattr(races_api, "_analysis_response", lambda *_args, **_kwargs: pytest.fail("cached reads must not analyze"))
    monkeypatch.setattr(races_api, "scrape_turfomania_quinte", lambda *_args: pytest.fail("cached reads must not scrape"))
    request = races_api.TodayQuinteAnalysisRequest(date="2026-10-03")

    first = races_api.analyze_today_turfomania_quinte(request)
    second = races_api.analyze_today_turfomania_quinte(request)

    assert first.race_id == "race-today"
    assert second.model_dump() == first.model_dump()
