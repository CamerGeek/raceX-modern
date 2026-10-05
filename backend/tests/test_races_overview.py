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


def test_prognosis_outside_top_composite_uses_top_eight_and_normalized_numbers() -> None:
    analyzed = pd.DataFrame(
        [
            {"N°": str(number), "Composite": 1 - number / 20}
            for number in range(1, 11)
        ]
    )
    prognosis = [{"N°": "10.0"}, {"N°": "2"}, {"N°": "9"}]

    assert races._prognosis_outside_top_composite(prognosis, analyzed) == [
        {"N°": "10.0"},
        {"N°": "9"},
    ]


def test_prognosis_outside_top_composite_checks_all_runners_in_small_fields() -> None:
    analyzed = pd.DataFrame(
        [
            {"N°": "1", "Composite": 0.9},
            {"N°": "2", "Composite": 0.8},
            {"N°": "3", "Composite": 0.7},
            {"N°": "4", "Composite": 0.6},
            {"N°": "5", "Composite": 0.5},
        ]
    )

    assert races._prognosis_outside_top_composite([{"N°": "5"}], analyzed) == []


def test_prognosis_outside_top_composite_is_unavailable_without_composite_ranking() -> None:
    assert races._prognosis_outside_top_composite([{"N°": "5"}], pd.DataFrame({"N°": ["5"]})) is None
