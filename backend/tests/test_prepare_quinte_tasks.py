from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.races import TurfomaniaQuinteAnalysisResponse
from app.tasks import prepare_today_quinte, prepare_tomorrow_quinte

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")


def _response() -> TurfomaniaQuinteAnalysisResponse:
    return TurfomaniaQuinteAnalysisResponse(
        race_id="race-quinte",
        race_type="flat",
        source="turfomania",
        row_count=1,
        columns=["N°"],
        rows=[{"N°": "1"}],
        model_version="test",
        prognosis=[],
    )


@pytest.mark.parametrize(
    ("utc_now", "expected_date"),
    [
        (datetime(2026, 7, 1, 7, 0, tzinfo=UTC), "2026-07-01"),
        (datetime(2026, 12, 1, 8, 0, tzinfo=UTC), "2026-12-01"),
    ],
)
def test_prepare_today_runs_at_nine_paris_and_uses_shared_analysis(
    monkeypatch: pytest.MonkeyPatch,
    utc_now: datetime,
    expected_date: str,
) -> None:
    captured: dict[str, object] = {}

    def analyze(request):
        captured["request"] = request
        return _response()

    monkeypatch.setattr(prepare_today_quinte, "_analyze_today_turfomania_quinte", analyze)

    result = prepare_today_quinte.prepare_today_quinte(now=utc_now)

    assert captured["request"].meeting_date is None
    assert result == {
        "status": "cached",
        "meeting_date": expected_date,
        "race_id": "race-quinte",
    }


@pytest.mark.parametrize(
    ("utc_now", "expected_date"),
    [
        (datetime(2026, 7, 1, 7, 30, tzinfo=UTC), "2026-07-02"),
        (datetime(2026, 12, 1, 8, 30, tzinfo=UTC), "2026-12-02"),
    ],
)
def test_prepare_tomorrow_runs_at_nine_thirty_paris(
    monkeypatch: pytest.MonkeyPatch,
    utc_now: datetime,
    expected_date: str,
) -> None:
    captured: dict[str, object] = {}

    def analyze(request, *, allow_tomorrow_analysis: bool):
        captured["request"] = request
        captured["allow_tomorrow_analysis"] = allow_tomorrow_analysis
        return _response()

    monkeypatch.setattr(prepare_tomorrow_quinte, "_analyze_today_turfomania_quinte", analyze)

    result = prepare_tomorrow_quinte.prepare_tomorrow_quinte(now=utc_now)

    assert captured["request"].meeting_date.isoformat() == expected_date
    assert captured["allow_tomorrow_analysis"] is True
    assert result == {
        "status": "cached",
        "meeting_date": expected_date,
        "race_id": "race-quinte",
    }


@pytest.mark.parametrize(
    ("task", "now"),
    [
        (prepare_today_quinte.prepare_today_quinte, datetime(2026, 10, 2, 8, 59, tzinfo=PARIS)),
        (prepare_tomorrow_quinte.prepare_tomorrow_quinte, datetime(2026, 10, 2, 9, 29, tzinfo=PARIS)),
    ],
)
def test_quinte_tasks_skip_nonmatching_paris_times(
    monkeypatch: pytest.MonkeyPatch,
    task,
    now: datetime,
) -> None:
    monkeypatch.setattr(
        prepare_today_quinte,
        "_analyze_today_turfomania_quinte",
        lambda *_args, **_kwargs: pytest.fail("analysis should not run outside its scheduled time"),
    )
    monkeypatch.setattr(
        prepare_tomorrow_quinte,
        "_analyze_today_turfomania_quinte",
        lambda *_args, **_kwargs: pytest.fail("analysis should not run outside its scheduled time"),
    )

    assert task(now=now)["status"] == "not_scheduled"


@pytest.mark.parametrize(
    ("task", "now"),
    [
        (prepare_today_quinte.prepare_today_quinte, datetime(2026, 10, 2, 9, 0)),
        (prepare_tomorrow_quinte.prepare_tomorrow_quinte, datetime(2026, 10, 2, 9, 30)),
    ],
)
def test_quinte_tasks_reject_naive_datetime(task, now: datetime) -> None:
    with pytest.raises(ValueError, match="timezone"):
        task(now=now)
