from __future__ import annotations

from collections import Counter
import re
import random
from typing import Any

import pandas as pd

from app.services.analysis_service import analyze_race
from app.services.model_prediction_service import predict_race as predict_model_race
from race_scraper_app import reducing_system

NUMBER_COLUMNS = ("N°", "N", "Numero", "NUMERO", "N?", "NUM")
DEEP_SCORE_COLUMNS = ("place_prob_deep", "DEEP_SCORE", "Deep score", "Deep Score")
WIN_SCORE_COLUMNS = ("p_win", "P_WIN")
COMPOSITE_COLUMNS = ("Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score")
SHORTLIST_SIZE = 8
BASE_SIZE = 3
PLOT_TWIST_LIMIT = 4
PLOT_TWIST_SCORE_WINDOW = 0.05
READY_TICKET_SIZES = (("winner", 1), ("quinella", 2), ("trio", 4))


def simulate_race(frame: pd.DataFrame, race_type: str, simulations: int = 5000, seed: int | None = 42) -> list[dict[str, Any]]:
    simulations = max(100, min(simulations, 50000))
    analyzed, _, _ = analyze_race(frame, race_type, include_handicap=True, max_horses=8)
    if analyzed.empty:
        return []
    number_column = next((column for column in ("N°", "N", "Numero") if column in analyzed.columns), None)
    if not number_column:
        return []
    horses = analyzed.copy().reset_index(drop=True)
    numbers = [str(value).removesuffix(".0") for value in horses[number_column]]
    scores = pd.to_numeric(horses.get("Composite", pd.Series(0.5, index=horses.index)), errors="coerce").fillna(0.5).clip(0.01, 1.0)
    odds = pd.to_numeric(horses.get("COTE", pd.Series(0.0, index=horses.index)), errors="coerce").fillna(0.0)
    weights = (scores * 0.75 + (1 / odds.replace(0, pd.NA)).fillna(scores) * 0.25).astype(float)
    weights = weights.clip(lower=0.001)
    rng = random.Random(seed)
    wins = Counter()
    podiums = Counter()
    rank_totals = Counter()
    for _ in range(simulations):
        remaining = list(range(len(numbers)))
        ranking: list[int] = []
        while remaining:
            total = sum(float(weights.iloc[index]) for index in remaining)
            pick = rng.random() * total
            for position, index in enumerate(remaining):
                pick -= float(weights.iloc[index])
                if pick <= 0:
                    ranking.append(index)
                    remaining.pop(position)
                    break
        for rank, index in enumerate(ranking, 1):
            horse = numbers[index]
            rank_totals[horse] += rank
            if rank == 1:
                wins[horse] += 1
            if rank <= 3:
                podiums[horse] += 1
    rows = []
    for index, horse in enumerate(numbers):
        row = horses.iloc[index].to_dict()
        row.update({
            "win_probability": round(wins[horse] / simulations, 4),
            "podium_probability": round(podiums[horse] / simulations, 4),
            "average_simulated_rank": round(rank_totals[horse] / simulations, 2),
        })
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["win_probability"], -row["podium_probability"], row["average_simulated_rank"]))


def _number(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text.removesuffix(".0")


def _row_number(row: dict[str, Any]) -> str:
    for column in NUMBER_COLUMNS:
        if column in row:
            number = _number(row[column])
            if number:
                return number
    return ""


def _row_score(row: dict[str, Any], columns: tuple[str, ...]) -> float | None:
    for column in columns:
        if column in row:
            score = pd.to_numeric(row[column], errors="coerce")
            if pd.notna(score):
                return float(score)
    return None


def _ranked_numbers(
    model_predictions: dict[str, Any] | None,
    columns: tuple[str, ...],
    fallback_columns: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> list[str]:
    if not model_predictions or model_predictions.get("status") != "ready":
        return []
    ranked: list[tuple[str, float, int]] = []
    for index, row in enumerate(model_predictions.get("rows") or []):
        number = _row_number(row)
        score = _row_score(row, columns)
        if score is None and fallback_columns:
            score = _row_score(row, fallback_columns)
        if number and score is not None:
            ranked.append((number, score, index))
    ranked.sort(key=lambda item: (-item[1], item[2]))
    numbers: list[str] = []
    for number, _, _ in ranked:
        if number not in numbers:
            numbers.append(number)
        if limit is not None and len(numbers) >= limit:
            break
    return numbers


def model_shortlist_numbers(model_predictions: dict[str, Any] | None) -> list[str]:
    """Top model rows by deep score, matching the frontend Model Shortlist."""
    return _ranked_numbers(model_predictions, DEEP_SCORE_COLUMNS, limit=SHORTLIST_SIZE)


def model_win_ranked_numbers(model_predictions: dict[str, Any] | None, limit: int | None = None) -> list[str]:
    """Horses ordered by model win score, falling back to the deep score when it is missing."""
    return _ranked_numbers(model_predictions, WIN_SCORE_COLUMNS, DEEP_SCORE_COLUMNS, limit)


def model_place_ranked_numbers(model_predictions: dict[str, Any] | None, limit: int | None = None) -> list[str]:
    """Horses ordered by model place score."""
    return _ranked_numbers(model_predictions, DEEP_SCORE_COLUMNS, limit=limit)


def ready_tickets_for(model_predictions: dict[str, Any] | None, all_horses: list[str]) -> list[dict[str, Any]]:
    """Model straight picks shown before the generated combinations.

    Winner and quinella follow the win score. The trio follows the place score and
    keeps four horses so bettors can cover every three-horse combination.
    """
    eligible = set(all_horses)
    win_ranked = [number for number in model_win_ranked_numbers(model_predictions) if number in eligible]
    place_ranked = [number for number in model_place_ranked_numbers(model_predictions) if number in eligible]
    pools = {"winner": win_ranked, "quinella": win_ranked, "trio": place_ranked}
    return [
        {"type": kind, "numbers": pools[kind][:size]}
        for kind, size in READY_TICKET_SIZES
        if len(pools[kind]) >= size
    ]


def plot_twist_numbers(analyzed: pd.DataFrame) -> list[str]:
    """Horses ranked outside the composite top eight and sitting near the mean or median."""
    number_column = next((column for column in NUMBER_COLUMNS if column in analyzed.columns), None)
    score_column = next((column for column in COMPOSITE_COLUMNS if column in analyzed.columns), None)
    if number_column is None or score_column is None:
        return []
    ranked: list[tuple[str, float, int]] = []
    for index, row in enumerate(analyzed.to_dict("records")):
        number = _number(row.get(number_column))
        score = _row_score(row, (score_column,))
        if number and score is not None:
            ranked.append((number, score, index))
    if len(ranked) <= SHORTLIST_SIZE:
        return []
    ranked.sort(key=lambda item: (-item[1], item[2]))
    scores = [score for _, score, _ in ranked]
    ordered = sorted(scores)
    middle = len(ordered) // 2
    median = (ordered[middle - 1] + ordered[middle]) / 2 if len(ordered) % 2 == 0 else ordered[middle]
    mean = sum(scores) / len(scores)
    twists: list[str] = []
    for rank, (number, score, _) in enumerate(ranked, 1):
        if rank > SHORTLIST_SIZE and (
            abs(score - mean) <= PLOT_TWIST_SCORE_WINDOW
            or abs(score - median) <= PLOT_TWIST_SCORE_WINDOW
        ):
            twists.append(number)
            if len(twists) >= PLOT_TWIST_LIMIT:
                break
    return twists


def _is_non_partant(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(re.search(r"\bnon[\s-]*partant(?:e)?\b", str(value), re.IGNORECASE))


def _non_partant_numbers(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "NON_PARTANT" not in frame.columns:
        return set()
    number_column = next((column for column in NUMBER_COLUMNS if column in frame.columns), None)
    if number_column is None:
        return set()
    return {
        _number(number)
        for number, flag in zip(frame[number_column], frame["NON_PARTANT"])
        if _is_non_partant(flag)
    }


def _derived_base(
    shortlist: list[str],
    substitutes: list[str],
    all_horses: list[str],
    combination_size: int,
) -> list[str]:
    """Mandatory horses come from the model shortlist; plot twist horses replace any that are unavailable."""
    target = min(BASE_SIZE, max(0, combination_size - 1))
    eligible = set(all_horses)
    intended = shortlist[:target]
    base = [number for number in dict.fromkeys(intended) if number in eligible]
    filler = [*substitutes, *shortlist[target:], *all_horses] if intended else all_horses
    for number in filler:
        if len(base) >= target:
            break
        if number in eligible and number not in base:
            base.append(number)
    return base[:target]


def _shortlist_pool(
    shortlist: list[str],
    substitutes: list[str],
    all_horses: list[str],
    combination_size: int,
) -> list[str]:
    """Play the whole model shortlist, topping up from Plot Twist and starters only when it is too small."""
    eligible = set(all_horses)
    pool = [number for number in dict.fromkeys(shortlist) if number in eligible]
    if not pool:
        return list(all_horses)
    for number in [*substitutes, *all_horses]:
        if len(pool) >= combination_size:
            break
        if number in eligible and number not in pool:
            pool.append(number)
    return pool


def _unique_combinations(
    combinations_result: list[tuple] | list[list],
    combination_size: int,
    max_combinations: int,
) -> list[list[str]]:
    unique: list[list[str]] = []
    seen = set()
    for combination in combinations_result:
        normalized = tuple(sorted(str(value) for value in combination))
        if len(normalized) == combination_size and normalized not in seen:
            seen.add(normalized)
            unique.append(list(combination))
        if len(unique) >= max_combinations:
            break
    return unique


def generate_combination_plan(
    frame: pd.DataFrame,
    race_type: str,
    combination_size: int = 5,
    max_combinations: int = 56,
    mandatory: list[str] | None = None,
    excluded: list[str] | None = None,
    source: str = "turfomania",
) -> dict[str, Any]:
    analyzed, _, _ = analyze_race(frame, race_type, include_handicap=True, max_horses=8)
    if analyzed.empty:
        return {"ready_tickets": [], "combinations": [], "base": [], "substitutes": []}
    number_column = next((column for column in ("N°", "N", "Numero") if column in analyzed.columns), None)
    if not number_column:
        return {"ready_tickets": [], "combinations": [], "base": [], "substitutes": []}
    blocked = {_number(value) for value in (excluded or [])} | _non_partant_numbers(frame)
    all_horses = list(dict.fromkeys(
        number
        for number in (_number(value) for value in analyzed[number_column])
        if number and number not in blocked
    ))
    if not all_horses:
        return {"ready_tickets": [], "combinations": [], "base": [], "substitutes": []}

    twists = [number for number in plot_twist_numbers(analyzed) if number in all_horses]
    combination_size = max(1, min(combination_size, len(all_horses)))
    shortlist: list[str] = []
    ready_tickets: list[dict[str, Any]] = []
    if mandatory:
        base = [number for number in dict.fromkeys(_number(value) for value in mandatory) if number in all_horses]
    else:
        prediction = predict_model_race(frame, race_type, source)
        shortlist = model_shortlist_numbers(prediction)
        ready_tickets = ready_tickets_for(prediction, all_horses)
        base = _derived_base(shortlist, twists, all_horses, combination_size)
    substitutes = [number for number in twists if number not in base]

    if mandatory:
        associates = [horse for horse in all_horses if horse not in base]
        combinations_result = reducing_system(base, associates, combination_size)
    else:
        pool = _shortlist_pool(shortlist, substitutes, all_horses, combination_size)
        combinations_result = reducing_system([], pool, combination_size)
    return {
        "ready_tickets": ready_tickets,
        "combinations": _unique_combinations(combinations_result, combination_size, max_combinations),
        "base": base,
        "substitutes": substitutes,
    }


def generate_custom_combinations(
    frame: pd.DataFrame,
    race_type: str,
    base: list[str],
    associates: list[str] | None = None,
    combination_size: int = 5,
    max_combinations: int = 50,
) -> dict[str, Any]:
    """Build subscriber-chosen tickets with the built-in reducing system."""
    analyzed, _, _ = analyze_race(frame, race_type, include_handicap=True, max_horses=8)
    if analyzed.empty:
        raise ValueError("No starters are available for this race")
    number_column = next((column for column in ("N°", "N", "Numero") if column in analyzed.columns), None)
    if not number_column:
        raise ValueError("Could not identify the horse number column for this race")
    blocked = _non_partant_numbers(frame)
    all_horses = list(dict.fromkeys(
        number
        for number in (_number(value) for value in analyzed[number_column])
        if number and number not in blocked
    ))
    base_numbers = [number for number in dict.fromkeys(_number(value) for value in base) if number]
    unknown_base = [number for number in base_numbers if number not in all_horses]
    if unknown_base:
        raise ValueError(f"Base horses are not starters: {', '.join(unknown_base)}")
    if not base_numbers:
        raise ValueError("Select at least one base horse")

    if associates:
        associate_numbers = [
            number
            for number in dict.fromkeys(_number(value) for value in associates)
            if number and number not in base_numbers
        ]
        unknown_associates = [number for number in associate_numbers if number not in all_horses]
        if unknown_associates:
            raise ValueError(f"Associate horses are not starters: {', '.join(unknown_associates)}")
    else:
        associate_numbers = [horse for horse in all_horses if horse not in base_numbers]

    needed = combination_size - len(base_numbers)
    if needed < 0:
        raise ValueError("The combination size must be at least the number of base horses")
    if needed == 0:
        return {"combinations": [list(base_numbers)], "base": base_numbers, "associates": []}
    if len(associate_numbers) < needed:
        raise ValueError(f"Select at least {needed} associate horse(s) to complete the combination")
    combinations_result = reducing_system(base_numbers, associate_numbers, combination_size)
    return {
        "combinations": _unique_combinations(combinations_result, combination_size, max_combinations),
        "base": base_numbers,
        "associates": associate_numbers,
    }
