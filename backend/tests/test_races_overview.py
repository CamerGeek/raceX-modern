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
