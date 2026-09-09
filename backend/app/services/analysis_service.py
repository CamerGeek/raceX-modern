import pandas as pd

from handicap_mechanics import analyze_handicap_impact
from race_scraper_app import compute_prognosis, compute_composite_score, normalize_composite_columns


def analyze_race(frame: pd.DataFrame, race_type: str, include_handicap: bool = True, max_horses: int = 8) -> tuple[pd.DataFrame, pd.DataFrame, dict | None]:
    working = frame.copy()
    handicap = None
    if include_handicap and race_type == "trot" and "DIST." in working.columns:
        working = analyze_handicap_impact(working)
        handicap_distance = working.get("HANDICAP_DISTANCE", pd.Series(dtype=object)).dropna()
        penalized = working.get("IS_PENALIZED", pd.Series(dtype=bool))
        handicap = {
            "distance": handicap_distance.iloc[0] if not handicap_distance.empty else None,
            "penalized_count": int(penalized.sum()) if not penalized.empty else 0,
        }

    try:
        working = normalize_composite_columns(working)
        composite = compute_composite_score(working)
        prognosis = compute_prognosis(composite, max_len=max_horses)
    except Exception:
        composite = working
        prognosis = working.head(max_horses)

    if not isinstance(prognosis, pd.DataFrame):
        prognosis = pd.DataFrame(prognosis)
    return composite, prognosis, handicap
