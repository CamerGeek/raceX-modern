from datetime import date, datetime, timedelta
import logging
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.races import (
    AnalysisRequest,
    AnalysisResponse,
    BettingRequest,
    RaceResponse,
    ScrapeRequest,
    TodayQuinteAnalysisRequest,
    TurfomaniaQuinteAnalysisRequest,
    TurfomaniaQuinteAnalysisResponse,
)
from app.services.betting_service import generate_combinations, simulate_race
from app.services.analysis_service import analyze_race
from app.services.model_prediction_service import predict_race as predict_model_race
from app.services.meeting_persistence import FLAT_TABLE, TROT_TABLE, persist_scraped_meeting
from app.services.quinte_odds_service import get_today_quinte_odds_history
from app.services.scraping_service import detect_race_type, detect_turfomania_race_type, scrape_race
from app.services.serialization import dataframe_records
from app.services.supabase_client import SupabaseClientWrapper
from app.services.auth_service import require_admin, require_subscriber_features
from app.services.turfomania_download import _infer_race_type, parse_turfomania_meeting_url
from app.services.turfomania_quinte import (
    QUINTE_TOMORROW_URL,
    find_turfomania_quinte_meeting,
    scrape_turfomania_quinte,
    turfomania_quinte_race_type,
)
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
logger = logging.getLogger(__name__)

TROT_DISPLAY_EXCLUDED_COLUMNS = {"POIDS", "IC", "HANDICAP_DISTANCE"}
HOMEPAGE_QUINTE_CACHE_VERSION = "daily-quinte-composite-v3"
RACE_ANALYSIS_CACHE_VERSION = "race-analysis-v2"
BETTING_CACHE_VERSION = "betting-analysis-v1"


def _saved_frame(client: SupabaseClientWrapper, race_id: str) -> tuple[pd.DataFrame, dict]:
    race = client.select_one("races", filters=[("id", "eq", race_id)])
    if not race:
        raise HTTPException(status_code=404, detail="Saved race not found")
    table = "trot_race_runners" if race["race_type"] == "trot" else "flat_race_runners"
    rows = client.list(table, filters=[("race_id", "eq", race_id)], limit=1000, order_by=("runner_number", "asc"))
    frame = pd.DataFrame([row.get("raw_data") if isinstance(row.get("raw_data"), dict) else row for row in rows])
    source_url = str(race.get("source_url") or "")
    is_turfomania_race_page = (
        race.get("source") == "turfomania"
        and "/pronostics/partants-" in source_url
        and "idcourse=" in source_url
    )
    if is_turfomania_race_page:
        inferred_type = detect_turfomania_race_type(source_url)
        if race.get("race_type") != inferred_type:
            race = {**race, "race_type": inferred_type}
            client.update("races", id_value=race_id, payload={"race_type": inferred_type})
    elif not frame.empty and race.get("source") == "turfomania" and race.get("race_type") in {None, "flat"}:
        inferred_type = _infer_race_type(frame)
        if inferred_type != race.get("race_type"):
            race = {**race, "race_type": inferred_type}
            client.update("races", id_value=race_id, payload={"race_type": inferred_type})
    if race["race_type"] == "trot":
        frame = frame.drop(columns=TROT_DISPLAY_EXCLUDED_COLUMNS, errors="ignore")
    return frame, race


def _runner_table_for_race(race_type: str) -> str | None:
    if race_type == "trot":
        return TROT_TABLE
    if race_type in {"flat", "obstacles"}:
        return FLAT_TABLE
    return None


def _cached_result(
    client: SupabaseClientWrapper,
    *,
    race_id: str,
    runner_table: str,
    cache_version: str,
    cache_kind: str,
    options: dict[str, Any],
) -> Any | None:
    runs = client.list(
        "analysis_runs",
        filters=[("race_id", "eq", race_id)],
        limit=100,
        order_by=("created_at", "desc"),
    )
    for run in runs:
        summary = run.get("summary") or {}
        cache = summary.get("racex_cache") if isinstance(summary, dict) else None
        if (
            not isinstance(cache, dict)
            or cache.get("version") != cache_version
            or cache.get("kind") != cache_kind
            or cache.get("options") != options
            or "result" not in cache
        ):
            continue
        latest_runner = client.select_one(
            runner_table,
            filters=[("race_id", "eq", race_id)],
            order_by=("updated_at", "desc"),
        )
        if _homepage_cache_is_fresh(run, latest_runner):
            return cache["result"]
    return None


def _store_cached_result(
    client: SupabaseClientWrapper,
    *,
    race_id: str,
    runner_table: str,
    model_version: str,
    cache_version: str,
    cache_kind: str,
    options: dict[str, Any],
    result: Any,
) -> None:
    latest_runner = client.select_one(
        runner_table,
        filters=[("race_id", "eq", race_id)],
        order_by=("updated_at", "desc"),
    )
    if not latest_runner:
        raise ValueError(f"Cannot cache analysis without stored runners for race {race_id}")
    serialized_result = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    client.insert(
        "analysis_runs",
        {
            "race_id": race_id,
            "model_version": model_version,
            "summary": {
                "racex_cache": {
                    "version": cache_version,
                    "kind": cache_kind,
                    "options": options,
                    "result": serialized_result,
                }
            },
            "prognosis": serialized_result.get("prognosis", []) if isinstance(serialized_result, dict) else [],
            "handicap": serialized_result.get("handicap") or {} if isinstance(serialized_result, dict) else {},
            "raw_rows": serialized_result.get("rows", []) if isinstance(serialized_result, dict) else [],
        },
    )


def _display_frame(source: pd.DataFrame, analyzed: pd.DataFrame, race_type: str) -> pd.DataFrame:
    display = analyzed if not analyzed.empty else source.copy()
    if not source.empty and not analyzed.empty:
        computed_columns = [column for column in analyzed.columns if column not in source.columns]
        if computed_columns:
            number_column = next(
                (
                    column
                    for column in ("N°", "N", "Numero", "NUMERO", "NUM")
                    if column in source.columns and column in analyzed.columns
                ),
                None,
            )
            if number_column:
                def horse_number_key(value: Any) -> str:
                    if pd.isna(value):
                        return ""
                    return str(value).strip().removesuffix(".0")

                computed_by_number: dict[str, dict[str, Any]] = {}
                for _, row in analyzed[[number_column, *computed_columns]].iterrows():
                    number = horse_number_key(row[number_column])
                    if number:
                        computed_by_number[number] = row[computed_columns].to_dict()
                display = source.copy()
                for column in computed_columns:
                    display[column] = source[number_column].map(
                        lambda value: computed_by_number.get(horse_number_key(value), {}).get(column)
                    )
            else:
                display = source.join(analyzed[computed_columns], how="left")
    if race_type == "trot":
        display = display.drop(columns=TROT_DISPLAY_EXCLUDED_COLUMNS, errors="ignore")
    return display


@router.get("/detect-type")
def detect_type(url: str = Query(min_length=1), _: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    if parse_turfomania_meeting_url(url):
        raise HTTPException(
            status_code=422,
            detail="Race type is specific to each race. Select a race instead of a meeting.",
        )
    try:
        parsed_url = urlparse(url)
        if (
            parsed_url.hostname
            and parsed_url.hostname.lower() in {"turfomania.fr", "www.turfomania.fr"}
            and parsed_url.path.startswith("/pronostics/partants-")
            and "idcourse" in parse_qs(parsed_url.query)
        ):
            return {"race_type": detect_turfomania_race_type(url)}
        return {"race_type": detect_race_type(url)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race type detection failed: {exc}") from exc


@router.post("/scrape", response_model=RaceResponse)
def scrape(request: ScrapeRequest, _: dict[str, Any] = Depends(require_admin)) -> RaceResponse:
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
def analyze(request: AnalysisRequest, _: dict[str, Any] = Depends(require_admin)) -> AnalysisResponse:
    try:
        race_type = request.race_type
        source = request.source
        client: SupabaseClientWrapper | None = None
        if request.race_id:
            client = SupabaseClientWrapper()
            frame, race = _saved_frame(client, request.race_id)
            race_type = race["race_type"]
            source = race.get("source", source)
            runner_table = _runner_table_for_race(race_type)
            options = {
                "race_type": race_type,
                "source": source,
                "include_handicap": request.include_handicap,
                "max_horses": request.max_horses,
            }
            cached = (
                _cached_result(
                    client,
                    race_id=request.race_id,
                    runner_table=runner_table,
                    cache_version=RACE_ANALYSIS_CACHE_VERSION,
                    cache_kind="race-analysis",
                    options=options,
                )
                if runner_table and not request.force_refresh
                else None
            )
            if cached is not None:
                return AnalysisResponse.model_validate(cached)
        else:
            frame = scrape_race(request.url, race_type, source)
        result = _analysis_response(
            frame,
            race_type=race_type,
            source=source,
            include_handicap=request.include_handicap,
            max_horses=request.max_horses,
        )
        if client and request.race_id and runner_table:
            _store_cached_result(
                client,
                race_id=request.race_id,
                runner_table=runner_table,
                model_version=result.model_version,
                cache_version=RACE_ANALYSIS_CACHE_VERSION,
                cache_kind="race-analysis",
                options=options,
                result=result,
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Race analysis failed")
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
    sections = _legacy_sections(display_frame, analyzed, race_type, include_handicap)
    overview = _flat_overview(frame, analyzed, prognosis_rows) if race_type == "flat" else {}
    model_predictions = predict_model_race(frame, race_type, source)
    model_check = _model_check_disagreements(
        prognosis_rows, display_frame, model_predictions, len(frame)
    )
    return AnalysisResponse(
        race_type=race_type,
        source=source,
        row_count=len(display_frame),
        columns=[str(column) for column in display_frame.columns],
        rows=dataframe_records(display_frame),
        model_version="initial-migration",
        prognosis=prognosis_rows,
        model_check=model_check,
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
    _: dict[str, Any] = Depends(require_admin),
) -> TurfomaniaQuinteAnalysisResponse:
    client = SupabaseClientWrapper()
    meeting = client.select_one("meetings", filters=[("id", "eq", request.meeting_id)])
    if not meeting:
        raise HTTPException(status_code=404, detail="Selected Turfomania meeting not found")
    if meeting.get("source") != "turfomania":
        raise HTTPException(status_code=422, detail="Selected meeting is not a Turfomania meeting")

    try:
        options = {
            "race_type": None,
            "source": "turfomania",
            "include_handicap": request.include_handicap,
            "max_horses": request.max_horses,
        }
        if not request.force_refresh:
            for race in client.list(
                "races",
                filters=[("meeting_id", "eq", request.meeting_id)],
                limit=500,
            ):
                summary = race.get("summary") or {}
                if race.get("source") != "turfomania" or not summary.get("q_plus"):
                    continue
                race_type = race.get("race_type")
                runner_table = _runner_table_for_race(race_type)
                if not runner_table:
                    continue
                cache_options = {**options, "race_type": race_type}
                if request.include_handicap and request.max_horses == 8:
                    cached_homepage = _cached_homepage_quinte_analysis(
                        client,
                        race["id"],
                        race_type,
                    )
                    if cached_homepage:
                        return cached_homepage
                cached = _cached_result(
                    client,
                    race_id=race["id"],
                    runner_table=runner_table,
                    cache_version=RACE_ANALYSIS_CACHE_VERSION,
                    cache_kind="turfomania-quinte",
                    options=cache_options,
                )
                if cached is not None:
                    return TurfomaniaQuinteAnalysisResponse.model_validate(cached)

        frame = scrape_turfomania_quinte(meeting)
        race_type = turfomania_quinte_race_type(frame)
        runner_table = _runner_table_for_race(race_type)
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
        race_id = persisted["races"][0]["id"]
        response = _analysis_response(
            frame,
            race_type=race_type,
            source="turfomania",
            include_handicap=request.include_handicap,
            max_horses=request.max_horses,
        )
        result = TurfomaniaQuinteAnalysisResponse(**response.model_dump(), race_id=race_id)
        if request.include_handicap and request.max_horses == 8:
            _store_homepage_quinte_analysis(client, result)
        elif runner_table:
            _store_cached_result(
                client,
                race_id=race_id,
                runner_table=runner_table,
                model_version=result.model_version,
                cache_version=RACE_ANALYSIS_CACHE_VERSION,
                cache_kind="turfomania-quinte",
                options={**options, "race_type": race_type},
                result=result,
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Turfomania Quinté analysis failed: {exc}") from exc


@router.post(
    "/turfomania/quinte/today/analyze",
    response_model=TurfomaniaQuinteAnalysisResponse,
)
def analyze_today_turfomania_quinte(
    request: TodayQuinteAnalysisRequest,
    _: dict[str, Any] = Depends(require_subscriber_features),
) -> TurfomaniaQuinteAnalysisResponse:
    return _analyze_today_turfomania_quinte(request)


@router.post(
    "/turfomania/quinte/tomorrow/analyze",
    response_model=TurfomaniaQuinteAnalysisResponse,
)
def analyze_tomorrow_turfomania_quinte(
    _: dict[str, Any] = Depends(require_admin),
) -> TurfomaniaQuinteAnalysisResponse:
    return _analyze_today_turfomania_quinte(
        TodayQuinteAnalysisRequest(date=_paris_today() + timedelta(days=1)),
        allow_tomorrow_analysis=True,
    )


@router.post("/turfomania/quinte/today/public")
def public_today_turfomania_quinte(request: TodayQuinteAnalysisRequest) -> dict[str, Any]:
    analysis = _analyze_today_turfomania_quinte(request)

    def numeric_score(value: Any, fallback: float = -1.0) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return fallback
        return score if pd.notna(score) else fallback

    ranked = sorted(
        analysis.rows,
        key=lambda row: numeric_score(row.get("Composite")),
        reverse=True,
    )[:8]

    def number_from(row: dict[str, Any]) -> str:
        for key in ("N°", "N", "Numero", "NUMERO", "NUM"):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip().removesuffix(".0")
        return ""

    public_rows: list[dict[str, Any]] = []
    for horse in ranked:
        number = number_from(horse)
        if number:
            public_rows.append({"N°": number, "Composite": horse.get("Composite")})

    return {
        "race_type": analysis.race_type,
        "row_count": analysis.row_count,
        "rows": public_rows,
    }


def _paris_today() -> date:
    return datetime.now(ZoneInfo("Europe/Paris")).date()


def _analyze_today_turfomania_quinte(
    request: TodayQuinteAnalysisRequest,
    *,
    allow_tomorrow_analysis: bool = False,
) -> TurfomaniaQuinteAnalysisResponse:
    client = SupabaseClientWrapper()
    paris_today = _paris_today()
    meeting_date = request.meeting_date or paris_today
    try:
        meetings = client.list(
            "meetings",
            filters=[
                ("source", "eq", "turfomania"),
                ("meeting_date", "eq", meeting_date.isoformat()),
            ],
            limit=100,
        )

        cached = _cached_homepage_quinte_for_date(
            client,
            meeting_date,
            meetings=meetings,
            created_on=paris_today if meeting_date == paris_today else None,
        )
        if cached:
            return cached

        if (
            meeting_date == paris_today + timedelta(days=1)
            and not allow_tomorrow_analysis
        ):
            raise HTTPException(
                status_code=404,
                detail="Tomorrow's Quinté+ analysis is not available yet. Please check back after an administrator prepares it.",
            )

        if meeting_date == paris_today:
            meeting, frame = find_turfomania_quinte_meeting(meetings)
            race_type = turfomania_quinte_race_type(frame)
            persisted = persist_scraped_meeting(
                frame,
                meeting_date=meeting_date,
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
                include_handicap=True,
                max_horses=8,
            )
            result = TurfomaniaQuinteAnalysisResponse(
                **response.model_dump(),
                race_id=persisted["races"][0]["id"],
            )
            _store_homepage_quinte_analysis(client, result)
            return result

        if meetings:
            refreshed = _reanalyze_saved_homepage_quinte(client, meetings)
            if refreshed:
                return refreshed

        if allow_tomorrow_analysis and meeting_date == paris_today + timedelta(days=1):
            meeting_ref = {
                "source": "turfomania",
                "meeting_date": meeting_date.isoformat(),
            }
            frame = scrape_turfomania_quinte(meeting_ref, url=QUINTE_TOMORROW_URL)
            race_type = turfomania_quinte_race_type(frame)
            meeting_name = str(frame["HIPPODROME"].iloc[0] or "") or None
            persisted = persist_scraped_meeting(
                frame,
                meeting_date=meeting_date,
                meeting_name=meeting_name,
                meeting_url=QUINTE_TOMORROW_URL,
                race_type=race_type,
                source="turfomania",
                client=client,
            )
            if not persisted["races"]:
                raise ValueError("No Quinté race was persisted")
            response = _analysis_response(
                frame,
                race_type=race_type,
                source="turfomania",
                include_handicap=True,
                max_horses=8,
            )
            result = TurfomaniaQuinteAnalysisResponse(
                **response.model_dump(),
                race_id=persisted["races"][0]["id"],
            )
            _store_homepage_quinte_analysis(client, result)
            return result

        if not meetings:
            raise HTTPException(
                status_code=404,
                detail=f"No prepared Turfomania Quinté analysis found for {meeting_date.isoformat()}",
            )
        raise HTTPException(
            status_code=404,
            detail=f"No prepared Quinté analysis found for {meeting_date.isoformat()}; ask an admin to run it.",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Turfomania Quinté analysis failed: {exc}",
        ) from exc


def _reanalyze_saved_homepage_quinte(
    client: SupabaseClientWrapper,
    meetings: list[dict[str, Any]],
) -> TurfomaniaQuinteAnalysisResponse | None:
    for meeting in meetings:
        races = client.list(
            "races",
            filters=[("meeting_id", "eq", meeting["id"])],
            limit=500,
        )
        for race in races:
            summary = race.get("summary") or {}
            if race.get("source") != "turfomania" or not summary.get("q_plus"):
                continue
            race_type = race.get("race_type")
            if not _runner_table_for_race(race_type):
                continue

            frame, saved_race = _saved_frame(client, race["id"])
            response = _analysis_response(
                frame,
                race_type=saved_race["race_type"],
                source="turfomania",
                include_handicap=True,
                max_horses=8,
            )
            result = TurfomaniaQuinteAnalysisResponse(
                **response.model_dump(),
                race_id=race["id"],
            )
            _store_homepage_quinte_analysis(client, result)
            return result
    return None


def _cached_homepage_quinte_for_date(
    client: SupabaseClientWrapper,
    meeting_date: date,
    *,
    meetings: list[dict[str, Any]] | None = None,
    created_on: date | None = None,
) -> TurfomaniaQuinteAnalysisResponse | None:
    meeting_rows = meetings if meetings is not None else client.list(
        "meetings",
        filters=[
            ("source", "eq", "turfomania"),
            ("meeting_date", "eq", meeting_date.isoformat()),
        ],
        limit=100,
    )
    for meeting in meeting_rows:
        for race in client.list(
            "races",
            filters=[("meeting_id", "eq", meeting["id"])],
            limit=500,
        ):
            summary = race.get("summary") or {}
            if race.get("source") == "turfomania" and summary.get("q_plus"):
                cached = _cached_homepage_quinte_analysis(
                    client,
                    race["id"],
                    race.get("race_type"),
                    require_fresh=False,
                    created_on=created_on,
                )
                if cached:
                    return cached
    return None


@router.get("/turfomania/quinte/today/odds")
def today_turfomania_quinte_odds(
    meeting_date: date | None = Query(default=None, alias="date"),
) -> dict[str, Any]:
    try:
        return get_today_quinte_odds_history(
            meeting_date=meeting_date or datetime.now(ZoneInfo("Europe/Paris")).date(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Today's Quinté odds history could not be loaded: {exc}",
        ) from exc


def _cached_homepage_quinte_analysis(
    client: SupabaseClientWrapper,
    race_id: str,
    race_type: str,
    *,
    require_fresh: bool = True,
    created_on: date | None = None,
) -> TurfomaniaQuinteAnalysisResponse | None:
    cached_runs = client.list(
        "analysis_runs",
        filters=[("race_id", "eq", race_id)],
        limit=100,
        order_by=("created_at", "desc"),
    )
    runner_table = _runner_table_for_race(race_type)
    if runner_table is None:
        return None
    latest_runner = client.select_one(
        runner_table,
        filters=[("race_id", "eq", race_id)],
        order_by=("updated_at", "desc"),
    )
    for cached_run in cached_runs:
        summary = cached_run.get("summary") or {}
        if summary.get("homepage_cache_version") != HOMEPAGE_QUINTE_CACHE_VERSION:
            continue
        cached_at = _parse_cache_timestamp(cached_run.get("created_at"))
        if created_on and (
            cached_at is None
            or cached_at.astimezone(ZoneInfo("Europe/Paris")).date() != created_on
        ):
            continue
        if require_fresh and not _homepage_cache_is_fresh(cached_run, latest_runner):
            continue
        cached_response = summary.get("homepage_analysis")
        if isinstance(cached_response, dict):
            return TurfomaniaQuinteAnalysisResponse.model_validate(cached_response)
    return None


def _homepage_cache_is_fresh(
    cached_run: dict[str, Any],
    latest_runner: dict[str, Any] | None,
) -> bool:
    cached_at = _parse_cache_timestamp(cached_run.get("created_at"))
    runner_updated_at = _parse_cache_timestamp((latest_runner or {}).get("updated_at"))
    return cached_at is not None and runner_updated_at is not None and cached_at >= runner_updated_at


def _parse_cache_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("UTC"))


def _store_homepage_quinte_analysis(
    client: SupabaseClientWrapper,
    response: TurfomaniaQuinteAnalysisResponse,
) -> None:
    if not response.race_id:
        raise ValueError("Cannot cache a Quinté analysis without a race ID")
    client.insert(
        "analysis_runs",
        {
            "race_id": response.race_id,
            "model_version": response.model_version,
            "summary": {
                "homepage_cache_version": HOMEPAGE_QUINTE_CACHE_VERSION,
                "homepage_analysis": response.model_dump(mode="json"),
            },
            "prognosis": response.prognosis,
            "handicap": response.handicap or {},
            "raw_rows": response.rows,
        },
    )


@router.post("/simulate")
def simulate(request: BettingRequest, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        client = SupabaseClientWrapper()
        frame, race = _saved_frame(client, request.race_id)
        options = {"race_type": race["race_type"], "simulations": request.simulations}
        runner_table = _runner_table_for_race(race["race_type"])
        cached = (
            _cached_result(
                client,
                race_id=request.race_id,
                runner_table=runner_table,
                cache_version=BETTING_CACHE_VERSION,
                cache_kind="simulation",
                options=options,
            )
            if runner_table and not request.force_refresh
            else None
        )
        if cached is not None:
            return cached
        result = {
            "race_id": request.race_id,
            "race_type": race["race_type"],
            "simulations": request.simulations,
            "rows": simulate_race(frame, race["race_type"], request.simulations),
        }
        if runner_table:
            _store_cached_result(
                client,
                race_id=request.race_id,
                runner_table=runner_table,
                model_version=BETTING_CACHE_VERSION,
                cache_version=BETTING_CACHE_VERSION,
                cache_kind="simulation",
                options=options,
                result=result,
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Race simulation failed: {exc}") from exc


@router.post("/combinations")
def combinations(request: BettingRequest, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        client = SupabaseClientWrapper()
        frame, race = _saved_frame(client, request.race_id)
        options = {
            "race_type": race["race_type"],
            "combination_size": request.combination_size,
            "max_combinations": request.max_combinations,
            "mandatory": request.mandatory,
            "excluded": request.excluded,
        }
        runner_table = _runner_table_for_race(race["race_type"])
        cached = (
            _cached_result(
                client,
                race_id=request.race_id,
                runner_table=runner_table,
                cache_version=BETTING_CACHE_VERSION,
                cache_kind="combinations",
                options=options,
            )
            if runner_table and not request.force_refresh
            else None
        )
        if cached is not None:
            return cached
        combos = generate_combinations(frame, race["race_type"], request.combination_size, request.max_combinations, request.mandatory, request.excluded)
        result = {"race_id": request.race_id, "race_type": race["race_type"], "combination_size": request.combination_size, "combinations": combos}
        if runner_table:
            _store_cached_result(
                client,
                race_id=request.race_id,
                runner_table=runner_table,
                model_version=BETTING_CACHE_VERSION,
                cache_version=BETTING_CACHE_VERSION,
                cache_kind="combinations",
                options=options,
                result=result,
            )
        return result
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


def _model_check_disagreements(
    prognosis: list[dict],
    composite: pd.DataFrame,
    model_predictions: dict[str, Any],
    starter_count: int,
) -> list[dict] | None:
    """Return horses not shared by prognosis and the deep-score/composite top eights."""
    if model_predictions.get("status") != "ready" or starter_count <= 0 or composite.empty:
        return None

    model_rows = model_predictions.get("rows")
    if not isinstance(model_rows, list) or not model_rows:
        return None

    number_columns = ("NUMERO", "N°", "N", "Numero", "N?", "NUM")

    def horse_number(value: Any) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip().removesuffix(".0")

    model_number_column = next(
        (column for column in number_columns if any(column in row for row in model_rows)),
        None,
    )
    deep_score_column = next(
        (column for column in ("place_prob_deep", "DEEP_SCORE", "Deep score", "Deep Score")
         if any(column in row for row in model_rows)),
        None,
    )
    composite_number_column = next(
        (column for column in number_columns if column in composite.columns),
        None,
    )
    if model_number_column is None or deep_score_column is None or composite_number_column is None:
        return None
    composite_score_column = next(
        (column for column in ("Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score")
         if column in composite.columns),
        None,
    )
    if composite_score_column is None:
        return None

    ranked_deep: list[tuple[str, float, dict]] = []
    for row in model_rows:
        number = horse_number(row.get(model_number_column))
        score = pd.to_numeric(row.get(deep_score_column), errors="coerce")
        if number and pd.notna(score):
            ranked_deep.append((number, float(score), row))
    ranked_composite: list[tuple[str, float, dict]] = []
    for _, row in composite.iterrows():
        number = horse_number(row.get(composite_number_column))
        score = pd.to_numeric(row.get(composite_score_column), errors="coerce")
        if number and pd.notna(score):
            ranked_composite.append((number, float(score), row.to_dict()))
    if not ranked_deep or not ranked_composite:
        return None

    tier_size = min(8, starter_count)
    top_deep = sorted(ranked_deep, key=lambda item: item[1], reverse=True)[:tier_size]
    top_composite = sorted(ranked_composite, key=lambda item: item[1], reverse=True)[:tier_size]
    candidates: dict[str, dict] = {}
    memberships: dict[str, set[str]] = {}

    def add_candidates(rows: list[tuple[str, dict]], source: str) -> None:
        for number, row in rows:
            candidates.setdefault(number, row)
            memberships.setdefault(number, set()).add(source)

    add_candidates(
        [
            (number, horse)
            for horse in prognosis
            if (number := horse_number(
                next((horse[column] for column in number_columns if column in horse), None)
            ))
        ],
        "Prognosis",
    )
    add_candidates([(number, row) for number, _, row in top_deep], "Deep score top 8")
    add_candidates([(number, row) for number, _, row in top_composite], "Composite top 8")

    for horse in prognosis:
        number = horse_number(next((horse[column] for column in number_columns if column in horse), None))
        if number in candidates:
            candidates[number] = {**candidates[number], **horse}

    all_sources = ("Prognosis", "Deep score top 8", "Composite top 8")
    return [
        {
            **candidates[number],
            "missing_from": ", ".join(
                source for source in all_sources if source not in memberships[number]
            ),
        }
        for number in candidates
        if len(memberships[number]) < len(all_sources)
    ]


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
