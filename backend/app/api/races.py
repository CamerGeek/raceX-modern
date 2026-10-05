from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.schemas.races import (
    AnalysisRequest,
    AnalysisResponse,
    BettingRequest,
    RaceResponse,
    ScrapeRequest,
    TurfomaniaQuinteAnalysisRequest,
    TurfomaniaQuinteAnalysisResponse,
)
from app.services.betting_service import generate_combinations, simulate_race
from app.services.analysis_service import analyze_race
from app.services.model_prediction_service import predict_race as predict_model_race
from app.services.meeting_persistence import persist_scraped_meeting
from app.services.scraping_service import detect_race_type, scrape_race
from app.services.serialization import dataframe_records
from app.services.supabase_client import SupabaseClientWrapper
from app.services.turfomania_download import parse_turfomania_meeting_url
from app.services.turfomania_quinte import scrape_turfomania_quinte, turfomania_quinte_race_type
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

TROT_DISPLAY_EXCLUDED_COLUMNS = {"POIDS", "IC", "HANDICAP_DISTANCE"}


def _saved_frame(client: SupabaseClientWrapper, race_id: str) -> tuple[pd.DataFrame, dict]:
    race = client.select_one("races", filters=[("id", "eq", race_id)])
    if not race:
        raise HTTPException(status_code=404, detail="Saved race not found")
    table = "flat_race_runners" if race["race_type"] == "flat" else "trot_race_runners"
    rows = client.list(table, filters=[("race_id", "eq", race_id)], limit=1000, order_by=("runner_number", "asc"))
    frame = pd.DataFrame([row.get("raw_data") if isinstance(row.get("raw_data"), dict) else row for row in rows])
    if race["race_type"] == "trot":
        frame = frame.drop(columns=TROT_DISPLAY_EXCLUDED_COLUMNS, errors="ignore")
    return frame, race


def _display_frame(source: pd.DataFrame, analyzed: pd.DataFrame, race_type: str) -> pd.DataFrame:
    display = analyzed if not analyzed.empty else source.copy()
    if not source.empty and not analyzed.empty:
        computed_columns = [column for column in analyzed.columns if column not in source.columns]
        if computed_columns:
            display = source.join(analyzed[computed_columns], how="left")
    if race_type == "trot":
        display = display.drop(columns=TROT_DISPLAY_EXCLUDED_COLUMNS, errors="ignore")
    return display


@router.get("/detect-type")
def detect_type(url: str = Query(min_length=1)) -> dict[str, str]:
    try:
        turfomania_id = parse_turfomania_meeting_url(url)
        if turfomania_id:
            race_type = _turfomania_race_type(turfomania_id)
            if race_type:
                return {"race_type": race_type}
            raise ValueError(f"No races found for Turfomania meeting {turfomania_id}")
        return {"race_type": detect_race_type(url)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race type detection failed: {exc}") from exc


def _turfomania_race_type(meeting_id: str) -> str | None:
    client = SupabaseClientWrapper()
    races = client.list("races", filters=[("meeting_id", "eq", meeting_id)], limit=500, order_by=("race_key", "asc"))
    return next((race.get("race_type") for race in races if race.get("race_type") in {"flat", "trot"}), None)


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
        return _analysis_response(
            frame,
            race_type=race_type,
            source=source,
            include_handicap=request.include_handicap,
            max_horses=request.max_horses,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race analysis failed: {exc}") from exc


def _analysis_response(
    frame: pd.DataFrame,
    *,
    race_type: str,
    source: str,
    include_handicap: bool,
    max_horses: int,
) -> AnalysisResponse:
    analyzed, prognosis, handicap = analyze_race(
        frame,
        race_type,
        include_handicap=include_handicap,
        max_horses=max_horses,
    )
    display_frame = _display_frame(frame, analyzed, race_type)
    prognosis_rows = _prognosis_rows(prognosis, analyzed, race_type)
    prognosis_outside_top_three = _prognosis_outside_top_three(prognosis_rows, analyzed)
    sections = _legacy_sections(display_frame, analyzed, race_type, include_handicap)
    overview = _flat_overview(frame, analyzed, prognosis_rows) if race_type == "flat" else {}
    model_predictions = predict_model_race(frame, race_type, source)
    return AnalysisResponse(
        race_type=race_type,
        source=source,
        row_count=len(display_frame),
        columns=[str(column) for column in display_frame.columns],
        rows=dataframe_records(display_frame),
        model_version="initial-migration",
        prognosis=prognosis_rows,
        prognosis_outside_top_three=prognosis_outside_top_three,
        signals=_analysis_signals(analyzed),
        sections=sections,
        overview=overview,
        race_details=str(frame["DESCRIPTIF"].iloc[0]) if "DESCRIPTIF" in frame.columns and not frame.empty else "",
        handicap=handicap,
        model_predictions=model_predictions,
    )


@router.post("/turfomania/quinte/analyze", response_model=TurfomaniaQuinteAnalysisResponse)
def analyze_turfomania_quinte(
    request: TurfomaniaQuinteAnalysisRequest,
) -> TurfomaniaQuinteAnalysisResponse:
    client = SupabaseClientWrapper()
    meeting = client.select_one("meetings", filters=[("id", "eq", request.meeting_id)])
    if not meeting:
        raise HTTPException(status_code=404, detail="Selected Turfomania meeting not found")
    if meeting.get("source") != "turfomania":
        raise HTTPException(status_code=422, detail="Selected meeting is not a Turfomania meeting")

    try:
        frame = scrape_turfomania_quinte(meeting)
        race_type = turfomania_quinte_race_type(frame)
        persisted = persist_scraped_meeting(
            frame,
            meeting_date=date.fromisoformat(str(meeting["meeting_date"])),
            meeting_name=meeting.get("name"),
            meeting_url=None,
            race_type=race_type,
            source="turfomania",
            client=client,
            meeting=meeting,
        )
        if not persisted["races"]:
            raise ValueError("No Quinté race was persisted")
        response = _analysis_response(
            frame,
            race_type=race_type,
            source="turfomania",
            include_handicap=request.include_handicap,
            max_horses=request.max_horses,
        )
        return TurfomaniaQuinteAnalysisResponse(**response.model_dump(), race_id=persisted["races"][0]["id"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Turfomania Quinté analysis failed: {exc}") from exc


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
def _prognosis_rows(prognosis: pd.DataFrame, analyzed: pd.DataFrame, race_type: str = "flat") -> list[dict]:
    """Keep legacy prognosis order while returning the full horse records."""
    if prognosis is None or prognosis.empty or analyzed.empty:
        return []
    number_column = next((column for column in ("N°", "N", "Numero") if column in analyzed.columns), None)
    if not number_column:
        return dataframe_records(prognosis)
    values = prognosis.iloc[:, 0].tolist()
    indexed = {str(value).removesuffix(".0"): row for value, row in zip(analyzed[number_column], dataframe_records(analyzed))}
    rows = [indexed[str(value).removesuffix(".0")] for value in values if str(value).removesuffix(".0") in indexed]
    if race_type == "trot":
        return rows
    return sorted(rows, key=lambda row: float(row.get("Composite", -1) or -1), reverse=True)


def _prognosis_outside_top_three(
    prognosis: list[dict], analyzed: pd.DataFrame
) -> list[dict] | None:
    """Return prognosis horses outside the top three composite-ranked runners."""
    if analyzed.empty or "Composite" not in analyzed.columns:
        return None

    number_column = next(
        (column for column in ("N°", "N", "Numero", "N?", "NUMERO") if column in analyzed.columns),
        None,
    )
    if number_column is None:
        return None

    def horse_number(value: Any) -> str:
        return "" if pd.isna(value) else str(value).strip().removesuffix(".0")

    ranked = analyzed.assign(_composite_score=pd.to_numeric(analyzed["Composite"], errors="coerce"))
    ranked = ranked.dropna(subset=["_composite_score"]).sort_values(
        "_composite_score", ascending=False, kind="mergesort"
    )
    top_three = {
        horse_number(value)
        for value in ranked.head(3)[number_column]
        if horse_number(value)
    }
    if not top_three:
        return None

    number_columns = ("N°", "N", "Numero", "N?", "NUMERO")
    outside_top_three = []
    for horse in prognosis:
        number = horse_number(next((horse[column] for column in number_columns if column in horse), None))
        if number and number not in top_three:
            outside_top_three.append(horse)
    return outside_top_three


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
        "upset_potential": horse_rows(divergence),
        "consistency_score": horse_rows(consistency),
        "odds_divergence": horse_rows(divergence),
        "best_starting_posts": best_posts,
        "track": hippodrome,
        "distance": distance,
        "race_details": str(frame["DESCRIPTIF"].iloc[0]) if "DESCRIPTIF" in frame.columns and not frame.empty else "",
    }
