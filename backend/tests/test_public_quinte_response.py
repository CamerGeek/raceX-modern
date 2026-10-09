from datetime import date

import pandas as pd

from app.api import races
from app.schemas.races import AnalysisResponse, ModelPredictionResponse, TurfomaniaQuinteAnalysisResponse
from app.schemas.races import TodayQuinteAnalysisRequest


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
    monkeypatch.setattr(races, "_analyze_today_turfomania_quinte", lambda _: analysis)

    response = races.public_today_turfomania_quinte(
        TodayQuinteAnalysisRequest(date=date(2026, 10, 8))
    )

    assert response["rows"] == [{"N°": "7", "Composite": 0.9}, {"N°": "4", "Composite": 0.8}, {"N°": "2", "Composite": 0.5}]
    assert "prognosis" not in response
    assert "model_predictions" not in response
    assert "race_id" not in response
    assert "race_details" not in response
    assert all("CHEVAL" not in row for row in response["rows"])


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


def test_stale_homepage_analysis_is_recomputed_from_persisted_runners(monkeypatch) -> None:
    class Client:
        def select_one(self, table, *, filters, **kwargs):
            if table == "analysis_runs":
                return {
                    "created_at": "2026-10-09T06:33:31+00:00",
                    "summary": {
                        "homepage_cache_version": "daily-quinte-composite-v1",
                        "homepage_analysis": {"rows": []},
                    },
                }
            if table == "flat_race_runners":
                return {"updated_at": "2026-10-09T07:55:10+00:00"}
            raise AssertionError(f"unexpected select table: {table}")

        def list(self, table, *, filters, limit, order_by):
            assert table == "flat_race_runners"
            return [
                {"runner_number": "3", "raw_data": {"CHEVAL": "Horse Three"}},
                {"runner_number": "4", "raw_data": {"CHEVAL": "Horse Four"}},
            ]

        def insert(self, table, payload):
            assert table == "analysis_runs"
            return payload

    analyzed_rows = []

    def analyze(frame, **kwargs):
        analyzed_rows.extend(frame.to_dict("records"))
        return AnalysisResponse(
            race_type="flat",
            source="turfomania",
            row_count=len(frame),
            columns=["N°", "CHEVAL", "Composite"],
            rows=[
                {"N°": row["N°"], "CHEVAL": row["CHEVAL"], "Composite": score}
                for row, score in zip(frame.to_dict("records"), [0.9, 0.8])
            ],
            model_version="test",
            prognosis=[],
        )

    monkeypatch.setattr(races, "_analysis_response", analyze)

    result = races._reanalyze_stale_homepage_quinte(Client(), "race-id", "flat")

    assert result is not None
    assert result.race_id == "race-id"
    assert [row["N°"] for row in analyzed_rows] == ["3", "4"]
