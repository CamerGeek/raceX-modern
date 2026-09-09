import pandas as pd

from handicap_mechanics import analyze_handicap_impact
from model_functions import clean_distance, compute_d_perf, parse_performance_string, success_coefficient
from race_scraper_app import (
    analyze_trotting_disqualification_risk,
    compute_composite_score,
    compute_prognosis,
    generate_trotting_prognosis,
    normalize_composite_columns,
)


def _compute_trotting_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    performance_column = next(
        (column for column in ("DERNIÈRES PERF.", "DERNIÈRES PERF", "DERNIERES PERF.", "MUSIQUE") if column in working.columns),
        None,
    )
    if not performance_column:
        return working

    performance = working[performance_column]
    if "DERNIÈRES PERF." not in working.columns:
        working["DERNIÈRES PERF."] = performance
    working["FA"] = performance.map(lambda value: compute_d_perf(value).get("a") if pd.notna(value) else None)
    working["FM"] = performance.map(lambda value: compute_d_perf(value).get("m") if pd.notna(value) else None)
    working["S_COEFF"] = performance.map(lambda value: success_coefficient(value, "a") if pd.notna(value) else 0.0)
    working["IF"] = working["FA"].where(working["FA"].fillna(0) > 0, working["FM"])

    parsed = performance.map(lambda value: parse_performance_string(str(value)) if pd.notna(value) else pd.Series(dtype=object))
    parsed_frame = pd.DataFrame(parsed.tolist(), index=working.index)
    for column in parsed_frame.columns:
        working[column] = parsed_frame[column]
    return working


def analyze_race(frame: pd.DataFrame, race_type: str, include_handicap: bool = True, max_horses: int = 8) -> tuple[pd.DataFrame, pd.DataFrame, dict | None]:
    working = frame.copy()
    handicap = None
    if race_type == "trot":
        working = _compute_trotting_metrics(working)
        if "DIST." in working.columns:
            working["DIST."] = working["DIST."].map(clean_distance)
    if include_handicap and race_type == "trot" and "DIST." in working.columns:
        working = analyze_handicap_impact(working)
        handicap_distance = working.get("HANDICAP_DISTANCE", pd.Series(dtype=object)).dropna()
        penalized = working.get("IS_PENALIZED", pd.Series(dtype=bool))
        handicap = {
            "distance": int(handicap_distance.iloc[0]) if not handicap_distance.empty else None,
            "penalized_count": int(penalized.sum()) if not penalized.empty else 0,
        }
    if race_type == "trot":
        disqualification = analyze_trotting_disqualification_risk(
            working,
            str(working["RACE_CONDITIONS"].iloc[0]) if "RACE_CONDITIONS" in working.columns and not working.empty else "",
            int(working["DIST."].iloc[0]) if "DIST." in working.columns and not working.empty and pd.notna(working["DIST."].iloc[0]) else 2700,
        ) if not working.empty else pd.DataFrame()
        if not disqualification.empty:
            disqualification_columns = [
                column for column in ("DQ_Risk", "DQ_Risk_Amplified", "DQ_Increase", "Is_Penalized", "Mean_Disq_Rate")
                if column in disqualification.columns
            ]
            if disqualification_columns:
                merge_key = "N°" if "N°" in working.columns and "N°" in disqualification.columns else "CHEVAL"
                if merge_key in working.columns and merge_key in disqualification.columns:
                    working = working.merge(disqualification[[merge_key, *disqualification_columns]], on=merge_key, how="left")

    try:
        working = normalize_composite_columns(working)
        composite = compute_composite_score(working)
        if race_type == "trot" and not working.empty and not composite.empty:
            merge_key = "N°" if "N°" in working.columns and "N°" in composite.columns else "CHEVAL"
            metric_columns = [
                column for column in (
                    "S_COEFF", "IF", "FA", "FM", "disq_count", "disq_harness_rate",
                    "disq_mounted_rate", "recent_disq_count", "recent_disq_rate", "DQ_Risk",
                    "DQ_Risk_Amplified", "DQ_Increase", "Is_Penalized", "Mean_Disq_Rate",
                )
                if column in working.columns and column not in composite.columns
            ]
            if merge_key in working.columns and merge_key in composite.columns and metric_columns:
                composite = composite.merge(working[[merge_key, *metric_columns]], on=merge_key, how="left")
        if race_type == "trot":
            race_conditions = str(working["RACE_CONDITIONS"].iloc[0]) if "RACE_CONDITIONS" in working.columns and not working.empty else ""
            race_distance = int(working["DIST."].iloc[0]) if "DIST." in working.columns and not working.empty else 2700
            trot_numbers = generate_trotting_prognosis(
                working,
                max_len=max_horses,
                race_conditions=race_conditions,
                race_distance=race_distance,
            )
            prognosis = pd.DataFrame({"N°": trot_numbers})
        else:
            prognosis = compute_prognosis(composite, max_len=max_horses)
    except Exception:
        composite = working
        prognosis = working.head(max_horses)

    if not isinstance(prognosis, pd.DataFrame):
        prognosis = pd.DataFrame(prognosis)
    return composite, prognosis, handicap
