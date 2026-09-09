import pandas as pd
from typing import Any
from fastapi import APIRouter, HTTPException, Query

from app.schemas.races import AnalysisRequest, AnalysisResponse, BettingRequest, RaceResponse, ScrapeRequest
from app.services.betting_service import generate_combinations, simulate_race
from app.services.analysis_service import analyze_race
from app.services.scraping_service import detect_race_type, scrape_race
from app.services.serialization import dataframe_records
from app.services.supabase_client import SupabaseClientWrapper
from race_scraper_app import (
    analyze_class_ic,
    analyze_fitness_if,
    analyze_success_coeff,
    analyze_trotting_disqualification_risk,
    analyze_trotting_fitness,
    analyze_trotting_performance,
    analyze_trotting_shoeing,
    analyze_trotting_summary_prognosis,
    analyze_trotting_trend,
    analyze_consistency_score,
    analyze_odds_divergence,
)
from favorable_cordes import compute_favorable_corde_horses

router = APIRouter(prefix="/races", tags=["races"])


def _saved_frame(client: SupabaseClientWrapper, race_id: str) -> tuple[pd.DataFrame, dict]:
    race = client.select_one("races", filters=[("id", "eq", race_id)])
    if not race:
        raise HTTPException(status_code=404, detail="Saved race not found")
    table = "flat_race_runners" if race["race_type"] == "flat" else "trot_race_runners"
    rows = client.list(table, filters=[("race_id", "eq", race_id)], limit=1000, order_by=("runner_number", "asc"))
    frame = pd.DataFrame([row.get("raw_data") if isinstance(row.get("raw_data"), dict) else row for row in rows])
    return frame, race


@router.get("/detect-type")
def detect_type(url: str = Query(min_length=1)) -> dict[str, str]:
    try:
        return {"race_type": detect_race_type(url)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race type detection failed: {exc}") from exc


@router.post("/scrape", response_model=RaceResponse)
def scrape(request: ScrapeRequest) -> RaceResponse:
    try:
        frame = scrape_race(request.url, request.race_type, request.source)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race source request failed: {exc}") from exc
    return RaceResponse(
        race_type=request.race_type,
        source=request.source,
        row_count=len(frame),
        columns=[str(column) for column in frame.columns],
        rows=dataframe_records(frame),
    )


@router.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest) -> AnalysisResponse:
    try:
        race_type = request.race_type
        source = request.source
        if request.race_id:
            client = SupabaseClientWrapper()
            frame, race = _saved_frame(client, request.race_id)
            race_type = race["race_type"]
            source = race.get("source", source)
        else:
            frame = scrape_race(request.url, race_type, source)
        analyzed, prognosis, handicap = analyze_race(
            frame,
            race_type,
            include_handicap=request.include_handicap,
            max_horses=request.max_horses,
        )
        prognosis_rows = _prognosis_rows(prognosis, analyzed)
        sections = _legacy_sections(frame, analyzed, race_type, request.include_handicap)
        overview = _flat_overview(frame, analyzed, prognosis_rows) if race_type == "flat" else {}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race analysis failed: {exc}") from exc
    return AnalysisResponse(
        race_type=race_type,
        source=source,
        row_count=len(analyzed),
        columns=[str(column) for column in analyzed.columns],
        rows=dataframe_records(analyzed),
        model_version="initial-migration",
        prognosis=prognosis_rows,
        signals=_analysis_signals(analyzed),
        sections=sections,
        overview=overview,
        race_details=str(frame["DESCRIPTIF"].iloc[0]) if "DESCRIPTIF" in frame.columns and not frame.empty else "",
        handicap=handicap,
    )


@router.post("/simulate")
def simulate(request: BettingRequest) -> dict[str, Any]:
    try:
        frame, race = _saved_frame(SupabaseClientWrapper(), request.race_id)
        return {"race_id": request.race_id, "race_type": race["race_type"], "simulations": request.simulations, "rows": simulate_race(frame, race["race_type"], request.simulations)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race simulation failed: {exc}") from exc


@router.post("/combinations")
def combinations(request: BettingRequest) -> dict[str, Any]:
    try:
        frame, race = _saved_frame(SupabaseClientWrapper(), request.race_id)
        combos = generate_combinations(frame, race["race_type"], request.combination_size, request.max_combinations, request.mandatory, request.excluded)
        return {"race_id": request.race_id, "race_type": race["race_type"], "combination_size": request.combination_size, "combinations": combos}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Combination generation failed: {exc}") from exc
def _prognosis_rows(prognosis: pd.DataFrame, analyzed: pd.DataFrame) -> list[dict]:
    """Keep legacy prognosis order while returning the full horse records."""
    if prognosis is None or prognosis.empty or analyzed.empty:
        return []
    number_column = next((column for column in ("N°", "N", "Numero") if column in analyzed.columns), None)
    if not number_column:
        return dataframe_records(prognosis)
    values = prognosis.iloc[:, 0].tolist()
    indexed = {str(value).removesuffix(".0"): row for value, row in zip(analyzed[number_column], dataframe_records(analyzed))}
    rows = [indexed[str(value).removesuffix(".0")] for value in values if str(value).removesuffix(".0") in indexed]
    return sorted(rows, key=lambda row: float(row.get("Composite", -1) or -1), reverse=True)


def _analysis_signals(frame: pd.DataFrame) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    if frame.empty:
        return signals
    if "Composite" in frame.columns:
        scores = pd.to_numeric(frame["Composite"], errors="coerce").dropna()
        if not scores.empty:
            signals.append({"label": "COMPOSITE RANGE", "value": f"{scores.min():.2f} - {scores.max():.2f}", "detail": "Legacy normalized score"})
            signals.append({"label": "AVERAGE SCORE", "value": f"{scores.mean():.2f}", "detail": f"Across {len(scores)} runners"})
    if "COTE" in frame.columns:
        odds = pd.to_numeric(frame["COTE"], errors="coerce").dropna()
        if not odds.empty:
            signals.append({"label": "MARKET FAVOURITE", "value": f"{odds.min():.2f}", "detail": "Lowest listed odds"})
    if "CLASS_ADVANTAGE" in frame.columns:
        advantage = pd.to_numeric(frame["CLASS_ADVANTAGE"], errors="coerce").dropna()
        if not advantage.empty:
            signals.append({"label": "CLASS ADVANTAGE", "value": f"{advantage.max():.2f}", "detail": "Best legacy class differential"})
    return signals


def _legacy_sections(frame: pd.DataFrame, composite: pd.DataFrame, race_type: str, include_handicap: bool) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []

    def add(title: str, table: pd.DataFrame | list[str] | None) -> None:
        if isinstance(table, list):
            if table:
                sections.append({"title": title, "columns": ["N°"], "rows": [{"N°": value} for value in table]})
        elif isinstance(table, pd.DataFrame) and not table.empty:
            sections.append({"title": title, "columns": [str(column) for column in table.columns], "rows": dataframe_records(table)})

    if race_type == "trot":
        conditions = str(frame["RACE_CONDITIONS"].iloc[0]) if "RACE_CONDITIONS" in frame.columns and not frame.empty else ""
        distance = 2700
        if "DIST." in frame.columns and not frame.empty:
            digits = "".join(character for character in str(frame["DIST."].iloc[0]) if character.isdigit())
            if digits:
                distance = int(digits)
        add("Summary & Prognosis", analyze_trotting_summary_prognosis(frame, composite, conditions, distance))
        add("Fitness (FA/FM)", analyze_trotting_fitness(frame, conditions, distance))
        add("Performance (S_COEFF)", analyze_trotting_performance(frame, conditions, distance))
        add("Form Trend", analyze_trotting_trend(frame))
        add("Shoeing Strategy", analyze_trotting_shoeing(frame))
        if include_handicap:
            add("Disqualification Risk", analyze_trotting_disqualification_risk(frame, conditions, distance))
    else:
        add("Fitness / IF", analyze_fitness_if(frame))
        add("Class / IC", analyze_class_ic(frame))
        add("Success Coefficient", analyze_success_coeff(frame))
    return sections


def _flat_overview(frame: pd.DataFrame, composite: pd.DataFrame, prognosis: list[dict]) -> dict[str, object]:
    def horse_rows(table: pd.DataFrame | None) -> list[dict]:
        if table is None or table.empty:
            return []
        return dataframe_records(table.head(8))

    consistency = analyze_consistency_score(frame, composite)
    divergence = analyze_odds_divergence(frame, composite)
    hippodrome = str(frame["HIPPODROME"].iloc[0]) if "HIPPODROME" in frame.columns and not frame.empty else ""
    distance_text = ""
    for column in ("DISTANCE", "DIST.", "DIST"):
        if column in frame.columns and not frame.empty:
            distance_text = str(frame[column].iloc[0])
            break
    digits = "".join(character for character in distance_text if character.isdigit())
    distance = int(digits) if digits else 0
    best_posts: list[str] = []
    if hippodrome and distance:
        best_posts = [str(value) for value in compute_favorable_corde_horses(frame, hippodrome, distance, top_n=3)]
    prognosis_numbers = {str(row.get("N°")) for row in prognosis}
    prognosis_rows = [row for row in dataframe_records(composite) if str(row.get("N°")) in prognosis_numbers]
    return {
        "prognosis": prognosis_rows,
        "summary": horse_rows(composite),
        "upset_potential": horse_rows(consistency),
        "consistency_score": horse_rows(consistency),
        "odds_divergence": horse_rows(divergence),
        "best_starting_posts": best_posts,
        "track": hippodrome,
        "distance": distance,
        "race_details": str(frame["DESCRIPTIF"].iloc[0]) if "DESCRIPTIF" in frame.columns and not frame.empty else "",
    }
