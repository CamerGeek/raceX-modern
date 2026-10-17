from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.races import TurfomaniaQuinteAnalysisResponse
from app.tasks import prepare_tomorrow_quinte as prepare_task

PARIS = ZoneInfo("Europe/Paris")
MIDNIGHT_PREP_TIME = datetime(2026, 10, 17, 23, 0, tzinfo=PARIS)


def test_prepare_task_only_runs_at_23_paris(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prepare_task,
        "_analyze_today_turfomania_quinte",
        lambda *_args, **_kwargs: pytest.fail("analysis should not run outside preparation hour"),
    )

    result = prepare_task.prepare_tomorrow_quinte(
        now=datetime(2026, 10, 17, 22, 59, tzinfo=PARIS),
    )

    assert result["status"] == "not_scheduled"


def test_prepare_task_analyzes_next_day_for_midnight_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    response = TurfomaniaQuinteAnalysisResponse(
        race_id="race-tomorrow",
        race_type="flat",
        source="turfomania",
        row_count=1,
        columns=["N°"],
        rows=[{"N°": "1"}],
        model_version="test",
        prognosis=[],
    )

    def analyze(request, *, allow_tomorrow_analysis: bool):
        captured["date"] = request.meeting_date
        captured["allow_tomorrow_analysis"] = allow_tomorrow_analysis
        return response

    monkeypatch.setattr(prepare_task, "_analyze_today_turfomania_quinte", analyze)
    monkeypatch.setattr(prepare_task, "SupabaseClientWrapper", lambda: object())
    monkeypatch.setattr(prepare_task, "_cached_homepage_quinte_for_date", lambda *_args: None)
    result = prepare_task.prepare_tomorrow_quinte(now=MIDNIGHT_PREP_TIME)

    assert captured["date"].isoformat() == "2026-10-18"
    assert captured["allow_tomorrow_analysis"] is True
    assert result == {
        "status": "cached",
        "meeting_date": "2026-10-18",
        "race_id": "race-tomorrow",
    }


def test_prepare_task_skips_analysis_when_tomorrow_is_already_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached = TurfomaniaQuinteAnalysisResponse(
        race_id="race-tomorrow",
        race_type="flat",
        source="turfomania",
        row_count=1,
        columns=["N°"],
        rows=[{"N°": "1"}],
        model_version="test",
        prognosis=[],
    )
    monkeypatch.setattr(prepare_task, "SupabaseClientWrapper", lambda: object())
    monkeypatch.setattr(prepare_task, "_cached_homepage_quinte_for_date", lambda *_args: cached)
    monkeypatch.setattr(
        prepare_task,
        "_analyze_today_turfomania_quinte",
        lambda *_args, **_kwargs: pytest.fail("cached races must not be analyzed again"),
    )

    result = prepare_task.prepare_tomorrow_quinte(now=MIDNIGHT_PREP_TIME)

    assert result == {
        "status": "already_cached",
        "meeting_date": "2026-10-18",
        "race_id": "race-tomorrow",
    }


def test_prepare_task_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        prepare_task.prepare_tomorrow_quinte(now=datetime(2026, 10, 17, 23, 0))
