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


def test_prognosis_outside_top_three_uses_composite_rank_and_normalized_numbers() -> None:
    analyzed = pd.DataFrame(
        [
            {"N°": "1.0", "Composite": 0.95},
            {"N°": "2", "Composite": 0.85},
            {"N°": "3", "Composite": 0.75},
            {"N°": "4", "Composite": 0.65},
            {"N°": "5", "Composite": 0.55},
        ]
    )
    prognosis = [{"N°": "5.0"}, {"N°": "2"}, {"N°": "4"}]

    assert races._prognosis_outside_top_three(prognosis, analyzed) == [
        {"N°": "5.0"},
        {"N°": "4"},
    ]


def test_prognosis_outside_top_three_is_unavailable_without_composite_ranking() -> None:
    assert races._prognosis_outside_top_three([{"N°": "5"}], pd.DataFrame({"N°": ["5"]})) is None
