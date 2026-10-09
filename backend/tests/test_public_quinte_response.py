from datetime import date

from app.api import races
from app.schemas.races import ModelPredictionResponse, TurfomaniaQuinteAnalysisResponse
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
