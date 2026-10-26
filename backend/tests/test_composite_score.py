import pandas as pd

from race_scraper_app import compute_composite_score, normalize_composite_columns
from model_functions import compute_trot_composite_score


def _scores(frame: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    normalized = normalize_composite_columns(frame)
    composite = compute_composite_score(normalized, weights=weights)
    return composite.set_index("N°")["Composite"].sort_index()


def test_flat_composite_keeps_ic_but_ignores_standalone_odds() -> None:
    runners = pd.DataFrame(
        {
            "N°": ["1", "2", "3"],
            "S_COEFF": [0.9, 0.5, 0.2],
            "IF": [1, 3, 2],
            "n_weight": [-1, 0, 1],
            "VALEUR": [20, 25, 30],
            "Corde": [1, 2, 3],
            "COTE": [2.0, 5.0, 10.0],
            "IC": [18.0, 20.0, 20.0],
        }
    )
    changed_odds = runners.assign(COTE=[25.0, 1.2, 3.0])
    changed_ic = runners.assign(IC=[20.0, 18.0, 20.0])

    normalized = normalize_composite_columns(runners)

    assert "_norm_IC" in normalized.columns
    assert "_norm_COTE" not in normalized.columns
    pd.testing.assert_series_equal(_scores(runners), _scores(changed_odds))
    assert not _scores(runners).equals(_scores(changed_ic))
    custom_weights = {"S_COEFF": 0.3, "IF": 0.2, "IC": 0.3, "COTE": 0.2}
    pd.testing.assert_series_equal(
        _scores(runners, custom_weights),
        _scores(changed_odds, custom_weights),
    )


def test_trotting_composite_is_independent_of_odds_and_ic() -> None:
    runners = pd.DataFrame(
        {
            "N°": ["1", "2", "3"],
            "S_COEFF": [0.9, 0.5, 0.2],
            "FA": [1, 2, 3],
            "REC.": [30, 45, 40],
            "trend_rank_slope": [-2, 1, 0],
            "shoeing_aggressiveness": [4, 0, 2],
            "DQ_Risk": [10, 80, 40],
            "COTE": [2.0, 5.0, 10.0],
            "IC": [18.0, 20.0, 20.0],
        }
    )
    changed_market = runners.assign(
        COTE=[25.0, 1.2, 3.0],
        IC=[-5.0, 23.8, 27.0],
    )

    pd.testing.assert_series_equal(_scores(runners), _scores(changed_market))


def test_legacy_trotting_composite_ignores_odds() -> None:
    runner = pd.Series(
        {
            "FA": 2,
            "REC.": 90,
            "avg_rank": 2.5,
            "recent_avg_rank": 3,
            "trend_rank_slope": -0.5,
            "disq_harness_rate": 0.1,
            "disq_mounted_rate": 0.2,
            "aggressiveness": 2,
            "S_COEFF_norm": 0.7,
            "COTE": 4.0,
        }
    )

    changed_odds = runner.copy()
    changed_odds["COTE"] = 100.0

    assert compute_trot_composite_score(runner) == compute_trot_composite_score(changed_odds)
    custom_weights = {"fitness": 0.1, "cote": 0.9}
    assert compute_trot_composite_score(
        runner,
        trot_weights=custom_weights,
    ) == compute_trot_composite_score(
        changed_odds,
        trot_weights=custom_weights,
    )
