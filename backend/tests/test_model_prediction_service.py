import pandas as pd

from app.api import races
from app.schemas.races import AnalysisRequest
from app.services import model_prediction_service


def test_predict_race_returns_model_scores(monkeypatch) -> None:
    class Predictor:
        meta = {"created": "2026-09-29"}

        def predict_race(self, frame, source):
            assert source == "turfomania"
            assert len(frame) == 1
            return {
                "bet_list": [4],
                "table": pd.DataFrame([{"NUMERO": 4, "place_prob": 0.75}]),
            }

    monkeypatch.setattr(model_prediction_service, "_get_predictor", lambda: Predictor())

    result = model_prediction_service.predict_race(pd.DataFrame([{"N°": "4"}]), "flat", "turfomania")

    assert result == {
        "status": "ready",
        "model_version": "2026-09-29",
        "bet_list": [4],
        "rows": [{"NUMERO": 4, "place_prob": 0.75}],
        "message": None,
    }


def test_predict_race_skips_unsupported_race_type(monkeypatch) -> None:
    monkeypatch.setattr(
        model_prediction_service,
        "_get_predictor",
        lambda: (_ for _ in ()).throw(AssertionError("predictor should not load")),
    )

    result = model_prediction_service.predict_race(pd.DataFrame(), "trot", "turfomania")

    assert result["status"] == "unsupported"
    assert result["bet_list"] == []


def test_analyze_includes_model_predictions(monkeypatch) -> None:
    frame = pd.DataFrame([{"N°": "4", "CHEVAL": "Runner"}])
    prediction = {
        "status": "ready",
        "model_version": "2026-09-29",
        "bet_list": [4],
        "rows": [{"NUMERO": 4, "place_prob": 0.75}],
        "message": None,
    }
    monkeypatch.setattr(races, "scrape_race", lambda *_: frame)
    monkeypatch.setattr(races, "analyze_race", lambda source, *_args, **_kwargs: (source, pd.DataFrame(), None))
    monkeypatch.setattr(races, "_prognosis_rows", lambda *_: [])
    monkeypatch.setattr(races, "_legacy_sections", lambda *_: [])
    monkeypatch.setattr(races, "_flat_overview", lambda *_: {})
    monkeypatch.setattr(races, "predict_model_race", lambda *_: prediction)

    result = races.analyze(AnalysisRequest(url="https://example.test/race", race_type="flat", source="turfomania"))

    assert result.model_predictions is not None
    assert result.model_predictions.status == "ready"
    assert result.model_predictions.bet_list == [4]