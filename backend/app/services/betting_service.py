from __future__ import annotations

from collections import Counter
from itertools import combinations
import random
from typing import Any

import pandas as pd

from app.services.analysis_service import analyze_race
from app.services.serialization import dataframe_records
from race_scraper_app import generate_trotting_bets, reducing_system


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


def generate_combinations(frame: pd.DataFrame, race_type: str, combination_size: int = 5, max_combinations: int = 50, mandatory: list[str] | None = None, excluded: list[str] | None = None) -> list[list[str]]:
    analyzed, prognosis, _ = analyze_race(frame, race_type, include_handicap=True, max_horses=8)
    if analyzed.empty:
        return []
    number_column = next((column for column in ("N°", "N", "Numero") if column in analyzed.columns), None)
    if not number_column:
        return []
    excluded_set = {str(value).removesuffix(".0") for value in (excluded or [])}
    all_horses = [str(value).removesuffix(".0") for value in analyzed[number_column] if str(value).removesuffix(".0") not in excluded_set]
    base = [str(value).removesuffix(".0") for value in (mandatory or []) if str(value).removesuffix(".0") in all_horses]
    associates = [horse for horse in all_horses if horse not in base]
    combination_size = max(1, min(combination_size, len(all_horses)))
    if race_type == "trot":
        combinations_result = generate_trotting_bets(analyzed, analyzed, base_horses=base, desired_size=combination_size, max_combos=max_combinations)
    else:
        combinations_result = reducing_system(base, associates, combination_size)
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
