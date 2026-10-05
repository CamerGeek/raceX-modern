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


def test_prognosis_outside_model_tier_uses_top_half_by_deep_score() -> None:
    prognosis = [{"N°": "10.0"}, {"N°": "2"}, {"N°": "9"}]
    predictions = {
        "status": "ready",
        "rows": [
            {"NUMERO": number, "place_prob_deep": score}
            for number, score in [(1, 0.95), (2, 0.90), (3, 0.85), (4, 0.80), (5, 0.75),
                                  (6, 0.70), (7, 0.65), (8, 0.60), (9, 0.55), (10, 0.50)]
        ],
    }

    outside, tier_size = races._prognosis_outside_model_tier(prognosis, predictions, starter_count=10)

    assert outside == [{"N°": "10.0"}, {"N°": "9"}]
    assert tier_size == 5


def test_prognosis_outside_model_tier_uses_starter_count_not_prediction_row_count() -> None:
    predictions = {
        "status": "ready",
        "rows": [{"NUMERO": number, "place_prob_deep": 1 - number / 10} for number in range(1, 7)],
    }

    outside, tier_size = races._prognosis_outside_model_tier(
        [{"N°": "6"}], predictions, starter_count=9
    )

    assert outside == [{"N°": "6"}]
    assert tier_size == 5


def test_prognosis_outside_model_tier_is_unavailable_without_deep_scores() -> None:
    predictions = {"status": "ready", "rows": [{"NUMERO": 5, "place_prob_deep": None}]}

    assert races._prognosis_outside_model_tier([{"N°": "5"}], predictions, 10) == (None, None)
