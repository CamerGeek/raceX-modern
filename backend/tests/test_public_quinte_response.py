from datetime import date

import pandas as pd
import pytest
from fastapi import HTTPException

from app.api import races
from app.schemas.races import ModelPredictionResponse, TurfomaniaQuinteAnalysisResponse


@pytest.fixture(autouse=True)
def clear_public_quinte_cache():
    races._public_quinte_cache.clear()
    yield
    races._public_quinte_cache.clear()


def test_public_quinte_response_only_returns_number_selections(monkeypatch) -> None:
    analysis = TurfomaniaQuinteAnalysisResponse(
        race_id="race-id",
        race_type="flat",
        source="turfomania",
        row_count=3,
        columns=["N°", "CHEVAL", "Composite", "SENSITIVE_FIELD"],
        rows=[
            {"N°": "4", "CHEVAL": "Horse Four", "Composite": 0.8, "SENSITIVE_FIELD": "private"},
            {"N°": "7", "CHEVAL": "Horse Seven", "Composite": 0.9, "SENSITIVE_FIELD": "private"},
            {"N°": "2", "CHEVAL": "Horse Two", "Composite": 0.5, "SENSITIVE_FIELD": "private"},
        ],
        prognosis=[{"N°": "4", "CHEVAL": "Horse Four"}, {"N°": "7", "CHEVAL": "Horse Seven"}],
        model_version="test",
        race_details="not public",
        model_predictions=ModelPredictionResponse(
            status="ready",
            bet_list=[7, 4],
            rows=[
                {"NUMERO": 4, "place_prob_deep": 0.5, "CHEVAL": "Horse Four"},
                {"NUMERO": 7, "place_prob_deep": 0.9, "CHEVAL": "Horse Seven"},
            ],
        ),
    )
    monkeypatch.setattr(races, "_analyze_today_turfomania_quinte", lambda *_args, **_kwargs: analysis)

    response = races._public_today_quinte_payload(date(2026, 10, 8))

    assert response["rows"] == [{"N°": "7", "Composite": 0.9}, {"N°": "4", "Composite": 0.8}, {"N°": "2", "Composite": 0.5}]
    assert "prognosis" not in response
    assert "model_predictions" not in response
    assert "race_id" not in response
    assert "race_details" not in response
    assert all("CHEVAL" not in row for row in response["rows"])


def test_public_quinte_payload_is_served_from_ttl_cache(monkeypatch) -> None:
    analysis = TurfomaniaQuinteAnalysisResponse(
        race_id="race-id",
        race_type="flat",
        source="turfomania",
        row_count=1,
        columns=["N°", "Composite"],
        rows=[{"N°": "4", "Composite": 0.8}],
        model_version="test",
        prognosis=[],
    )
    calls: list[date] = []

    def fake_analyze(request, **_kwargs):
        calls.append(request.meeting_date)
        return analysis

    monkeypatch.setattr(races, "_analyze_today_turfomania_quinte", fake_analyze)

    first = races._public_today_quinte_payload(date(2026, 10, 8))
    second = races._public_today_quinte_payload(date(2026, 10, 8))
    other_day = races._public_today_quinte_payload(date(2026, 10, 9))

    assert first == second
    assert other_day["rows"] == first["rows"]
    assert calls == [date(2026, 10, 8), date(2026, 10, 9)]


def test_homepage_analysis_cache_is_rejected_when_runner_data_is_newer() -> None:
    assert not races._homepage_cache_is_fresh(
        {"created_at": "2026-10-09T06:33:31.609252+00:00"},
        {"updated_at": "2026-10-09T07:55:10.174291+00:00"},
    )


def test_homepage_analysis_cache_is_reused_when_runners_are_unchanged() -> None:
    assert races._homepage_cache_is_fresh(
        {"created_at": "2026-10-09T07:55:10.174291+00:00"},
        {"updated_at": "2026-10-09T07:55:10.174291+00:00"},
    )


def test_homepage_analysis_cache_is_rejected_without_runner_timestamp() -> None:
    assert not races._homepage_cache_is_fresh(
        {"created_at": "2026-10-09T08:00:00Z"},
        {"updated_at": None},
    )


def test_display_frame_aligns_computed_scores_by_runner_number() -> None:
    source = pd.DataFrame([{"N°": "1"}, {"N°": "2"}])
    analyzed = pd.DataFrame([{"N°": "2", "Composite": 0.9}, {"N°": "1", "Composite": 0.1}])

    display = races._display_frame(source, analyzed, "flat")

    assert display[["N°", "Composite"]].to_dict("records") == [
        {"N°": "1", "Composite": 0.1},
        {"N°": "2", "Composite": 0.9},
    ]


def test_non_partant_numbers_are_normalized_and_numerically_sorted() -> None:
    frame = pd.DataFrame([
        {"N°": "12.0", "NON_PARTANT": True},
        {"N°": 3, "NON_PARTANT": "NON PARTANT"},
        {"N°": 1, "NON_PARTANT": False},
        {"N°": "4", "NON_PARTANT": True},
    ])

    assert races._non_partant_numbers(frame) == ["3", "4", "12"]


def test_stale_homepage_analysis_is_not_returned_from_cache() -> None:
    cached = TurfomaniaQuinteAnalysisResponse(
        race_id="race-id",
        race_type="flat",
        source="turfomania",
        row_count=1,
        columns=["N°", "CHEVAL", "Composite"],
        rows=[{"N°": "3", "CHEVAL": "Horse Three", "Composite": 0.9}],
        model_version="test",
        prognosis=[],
    )

    class Client:
        def list(self, table, *, filters, **kwargs):
            if table == "analysis_runs":
                return [{
                    "created_at": "2026-10-09T06:33:31+00:00",
                    "summary": {
                        "homepage_cache_version": races.HOMEPAGE_QUINTE_CACHE_VERSION,
                        "homepage_analysis": cached.model_dump(mode="json"),
                    },
                }]
            if table == "meetings":
                return [{"id": "meeting-id"}]
            if table == "races":
                return [{
                    "id": "race-id",
                    "source": "turfomania",
                    "race_type": "flat",
                    "summary": {"q_plus": True},
                }]
            raise AssertionError(f"unexpected list table: {table}")

        def select_one(self, table, *, filters, **kwargs):
            if table == "flat_race_runners":
                return {"updated_at": "2026-10-09T07:55:10+00:00"}
            raise AssertionError(f"unexpected select table: {table}")

    assert races._cached_homepage_quinte_for_date(
        Client(),
        date(2026, 10, 9),
        meetings=[{"id": "meeting-id"}],
    ) is None


def test_date_cache_returns_newest_analysis_across_duplicate_meetings() -> None:
    def cached_response(race_id: str, model_version: str) -> TurfomaniaQuinteAnalysisResponse:
        return TurfomaniaQuinteAnalysisResponse(
            race_id=race_id,
            race_type="flat",
            source="turfomania",
            row_count=1,
            columns=["N°"],
            rows=[{"N°": "1"}],
            model_version=model_version,
            prognosis=[],
        )

    responses = {
        "race-old": cached_response("race-old", "older"),
        "race-new": cached_response("race-new", "newest"),
    }

    class Client:
        def list(self, table, *, filters, **kwargs):
            if table == "races":
                meeting_ids = filters[0][2]
                if not isinstance(meeting_ids, list):
                    meeting_ids = [meeting_ids]
                return [
                    {
                        "id": "race-old" if meeting_id == "meeting-old" else "race-new",
                        "meeting_id": meeting_id,
                        "source": "turfomania",
                        "race_type": "flat",
                        "summary": {"q_plus": True},
                    }
                    for meeting_id in meeting_ids
                ]
            if table == "analysis_runs":
                race_id = filters[0][2]
                created_at = "2026-10-09T09:00:00+00:00" if race_id == "race-old" else "2026-10-09T10:00:00+00:00"
                return [{
                    "created_at": created_at,
                    "summary": {
                        "homepage_cache_version": races.HOMEPAGE_QUINTE_CACHE_VERSION,
                        "homepage_analysis": responses[race_id].model_dump(mode="json"),
                    },
                }]
            raise AssertionError(f"unexpected list table: {table}")

        def select_one(self, table, *, filters, **kwargs):
            assert table == "flat_race_runners"
            return {"updated_at": "2026-10-09T08:00:00+00:00"}

    result = races._cached_homepage_quinte_for_date(
        Client(),
        date(2026, 10, 9),
        meetings=[{"id": "meeting-old"}, {"id": "meeting-new"}],
    )

    assert result is not None
    assert result.model_version == "newest"


def test_today_quinte_cache_miss_returns_no_cached_analysis() -> None:
    class Client:
        def list(self, table, *, filters, **kwargs):
            if table == "meetings":
                return [{"id": "meeting-id"}]
            if table == "races":
                return [{
                    "id": "race-id",
                    "source": "turfomania",
                    "race_type": "flat",
                    "summary": {"q_plus": True},
                }]
            if table == "analysis_runs":
                return []
            raise AssertionError(f"unexpected list table: {table}")

        def select_one(self, *_args, **_kwargs):
            return {"updated_at": "2026-10-09T07:55:10+00:00"}

    assert races._cached_homepage_quinte_for_date(
        Client(),
        date(2026, 10, 9),
        meetings=[{"id": "meeting-id"}],
    ) is None


def test_public_quinte_does_not_trigger_an_analysis_on_cache_miss(monkeypatch) -> None:
    class Client:
        def list(self, table, *, filters, **kwargs):
            if table == "meetings":
                return [{"id": "meeting-id"}]
            if table == "races":
                return [{
                    "id": "race-id",
                    "source": "turfomania",
                    "race_type": "flat",
                    "summary": {"q_plus": True},
                }]
            if table == "analysis_runs":
                return []
            raise AssertionError(f"unexpected list table: {table}")

        def select_one(self, *_args, **_kwargs):
            return {"updated_at": "2026-10-09T07:55:10+00:00"}

    monkeypatch.setattr(races, "SupabaseClientWrapper", Client)
    monkeypatch.setattr(
        races,
        "scrape_turfomania_quinte",
        lambda *_args, **_kwargs: pytest.fail("public reads must not scrape"),
    )
    monkeypatch.setattr(
        races,
        "_analysis_response",
        lambda *_args, **_kwargs: pytest.fail("public reads must not analyze"),
    )

    with pytest.raises(HTTPException, match="ask an admin"):
        races._public_today_quinte_payload(date(2026, 10, 9))
