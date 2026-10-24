import pandas as pd

from app.api import races


def test_flat_overview_uses_odds_divergence_for_upset_potential(monkeypatch) -> None:
    consistency = pd.DataFrame([{"signal": "consistent"}])
    divergence = pd.DataFrame([{"signal": "divergent"}])
    monkeypatch.setattr(races, "analyze_consistency_score", lambda *_: consistency)
    monkeypatch.setattr(races, "analyze_odds_divergence", lambda *_: divergence)

    overview = races._flat_overview(pd.DataFrame([{}]), pd.DataFrame([{"Composite": 0.8}]), [])

    assert overview["upset_potential"] == [{"signal": "divergent"}]
    assert overview["consistency_score"] == [{"signal": "consistent"}]


def test_obstacle_market_signal_overview_includes_consistency_and_outsiders(monkeypatch) -> None:
    consistency = pd.DataFrame([{"N": "2", "consistency_score": 4}])
    divergence = pd.DataFrame([{"N": "5", "Divergence": 3}])
    monkeypatch.setattr(races, "analyze_consistency_score", lambda *_: consistency)
    monkeypatch.setattr(races, "analyze_odds_divergence", lambda *_: divergence)

    overview = races._market_signal_overview(
        pd.DataFrame([{"N°": "2"}]),
        pd.DataFrame([{"N°": "2", "Composite": 0.8}]),
    )

    assert overview["consistency_score"] == [{"N": "2", "consistency_score": 4}]
    assert overview["odds_divergence"] == [{"N": "5", "Divergence": 3}]
    assert overview["upset_potential"] == overview["odds_divergence"]


def test_obstacle_analysis_response_includes_market_signal_overview(monkeypatch) -> None:
    expected_overview = {
        "consistency_score": [{"N": "2"}],
        "odds_divergence": [{"N": "5"}],
        "upset_potential": [{"N": "5"}],
    }
    monkeypatch.setattr(
        races,
        "analyze_race",
        lambda *_args, **_kwargs: (pd.DataFrame([{"N°": "2"}]), pd.DataFrame(), None),
    )
    monkeypatch.setattr(races, "_display_frame", lambda frame, *_args: frame)
    monkeypatch.setattr(races, "_prognosis_rows", lambda *_args: [])
    monkeypatch.setattr(races, "_legacy_sections", lambda *_args: [])
    monkeypatch.setattr(races, "_analysis_signals", lambda *_args: [])
    monkeypatch.setattr(
        races,
        "predict_model_race",
        lambda *_args: {
            "status": "ready",
            "model_version": "test",
            "bet_list": [],
            "rows": [],
        },
    )
    monkeypatch.setattr(races, "_model_check_disagreements", lambda *_args: None)
    monkeypatch.setattr(races, "_market_signal_overview", lambda *_args: expected_overview)

    response = races._analysis_response(
        pd.DataFrame([{"N°": "2"}]),
        race_type="obstacles",
        source="turfomania",
        include_handicap=True,
        max_horses=8,
    )

    assert response.overview == expected_overview


def test_model_check_lists_prognosis_horses_missing_from_either_top_eight() -> None:
    prognosis = [{"N°": "10.0"}, {"N°": "2"}, {"N°": "9"}]
    predictions = {
        "status": "ready",
        "rows": [
            {"NUMERO": number, "place_prob_deep": score}
            for number, score in [(1, 0.95), (2, 0.90), (3, 0.85), (4, 0.80), (5, 0.75),
                                  (6, 0.70), (7, 0.65), (8, 0.60), (9, 0.55), (10, 0.50)]
        ],
    }
    composite = pd.DataFrame([
        {"N°": number, "Composite": score}
        for number, score in [(1, 0.95), (2, 0.90), (3, 0.85), (4, 0.80), (5, 0.75),
                              (6, 0.70), (7, 0.65), (9, 0.60), (8, 0.55), (10, 0.50)]
    ])

    result = races._model_check_disagreements(prognosis, composite, predictions, starter_count=10)

    result_by_number = {row["NUMERO"] if "NUMERO" in row else row["N°"]: row for row in result}
    assert set(result_by_number) == {1, 3, 4, 5, 6, 7, 8, "9", "10.0"}
    assert result_by_number[1]["missing_from"] == "Prognosis"
    assert result_by_number[8]["missing_from"] == "Prognosis, Composite top 8"
    assert result_by_number["9"]["missing_from"] == "Deep score top 8"
    assert result_by_number["10.0"]["missing_from"] == "Deep score top 8, Composite top 8"


def test_model_check_limits_rankings_to_eight_or_fewer_starters() -> None:
    predictions = {
        "status": "ready",
        "rows": [{"NUMERO": number, "place_prob_deep": 1 - number / 10} for number in range(1, 7)],
    }
    composite = pd.DataFrame([
        {"N°": number, "Composite": 1 - number / 10} for number in range(1, 7)
    ])

    result = races._model_check_disagreements(
        [{"N°": str(number)} for number in range(1, 7)],
        composite,
        predictions,
        starter_count=6,
    )

    assert result == []


def test_model_check_is_unavailable_without_deep_scores() -> None:
    predictions = {"status": "ready", "rows": [{"NUMERO": 5, "place_prob_deep": None}]}
    composite = pd.DataFrame([{"N°": 5, "Composite": 0.8}])

    assert races._model_check_disagreements(
        [{"N°": "5"}], composite, predictions, 10
    ) is None


def test_model_check_accepts_displayed_composite_score_alias() -> None:
    predictions = {
        "status": "ready",
        "rows": [
            {"NUMERO": 1, "place_prob_deep": 0.9},
            {"NUMERO": 2, "place_prob_deep": 0.8},
        ],
    }
    displayed_rows = pd.DataFrame([
        {"NUMERO": 1, "COMPOSITE_SCORE": 0.9},
        {"NUMERO": 2, "COMPOSITE_SCORE": 0.8},
    ])

    result = races._model_check_disagreements(
        [{"NUMERO": 1}, {"NUMERO": 2}], displayed_rows, predictions, 2
    )

    assert result == []
