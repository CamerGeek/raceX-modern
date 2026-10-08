from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

import app.services.quinte_odds_service as odds_service
from app.services.quinte_odds_service import (
    _odds_samples,
    collect_today_quinte_odds,
    get_today_quinte_odds_history,
)


def _quinte_frame(start_time: str = "15h30") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"N°": "1", "CHEVAL": "HORSE ONE", "COTE": 4.2, "START_TIME": start_time},
            {"N°": "2", "CHEVAL": "HORSE TWO", "COTE": "12,5", "START_TIME": start_time},
            {"N°": "3", "CHEVAL": "HORSE THREE", "COTE": None, "START_TIME": start_time},
        ]
    )


def test_odds_samples_only_include_valid_positive_odds() -> None:
    samples = _odds_samples(
        _quinte_frame(),
        race_id="race-1",
        captured_at="2026-10-08T08:00:00+00:00",
    )

    assert [sample["N°"] for sample in samples] == ["1", "2"]
    assert [sample["odds"] for sample in samples] == [4.2, 12.5]


def test_collect_saves_single_timestamp_and_runner_odds(monkeypatch) -> None:
    meeting = {"id": "meeting-1", "name": "Longchamp", "meeting_date": "2026-10-08"}
    captured: dict = {}

    class Client:
        def list(self, table: str, **_kwargs: object) -> list[dict]:
            assert table == "meetings"
            return [meeting]

        def upsert_many(self, table: str, rows: list[dict], *, on_conflict: str) -> list[dict]:
            captured.update(table=table, rows=rows, on_conflict=on_conflict)
            return rows

    monkeypatch.setattr(
        odds_service,
        "find_turfomania_quinte_meeting",
        lambda _meetings: (meeting, _quinte_frame()),
    )
    monkeypatch.setattr(
        odds_service,
        "persist_scraped_meeting",
        lambda *_args, **_kwargs: {"races": [{"id": "race-1", "race_key": "R1C1"}]},
    )

    result = collect_today_quinte_odds(
        Client(),
        now=datetime(2026, 10, 8, 10, 0, tzinfo=ZoneInfo("Europe/Paris")),
    )

    assert result["status"] == "saved"
    assert result["samples_saved"] == 2
    assert captured["table"] == "quinte_odds_snapshots"
    assert captured["on_conflict"] == 'race_id,captured_at,"N°"'
    assert {row["captured_at"] for row in captured["rows"]} == {"2026-10-08T08:00:00+00:00"}


def test_collect_stops_after_scheduled_start(monkeypatch) -> None:
    meeting = {"id": "meeting-1", "name": "Longchamp", "meeting_date": "2026-10-08"}
    monkeypatch.setattr(
        odds_service,
        "find_turfomania_quinte_meeting",
        lambda _meetings: (meeting, _quinte_frame("15h30")),
    )
    monkeypatch.setattr(
        odds_service,
        "persist_scraped_meeting",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not persist after start")),
    )

    class Client:
        def list(self, table: str, **_kwargs: object) -> list[dict]:
            assert table == "meetings"
            return [meeting]

    result = collect_today_quinte_odds(
        Client(),
        now=datetime(2026, 10, 8, 15, 31, tzinfo=ZoneInfo("Europe/Paris")),
    )

    assert result == {
        "status": "race_started",
        "date": "2026-10-08",
        "start_time": "15:30",
        "samples_saved": 0,
    }


def test_history_groups_odds_points_by_runner() -> None:
    class Client:
        def list(self, table: str, *, filters: list[tuple[str, str, object]], **_kwargs: object) -> list[dict]:
            if table == "meetings":
                return [{"id": "meeting-1"}]
            if table == "races":
                return [{"id": "race-1", "source": "turfomania", "race_key": "R1C1", "race_type": "flat", "summary": {"q_plus": True}}]
            if table == "quinte_odds_snapshots":
                return [
                    {"N°": "2", "CHEVAL": "HORSE TWO", "captured_at": "2026-10-08T08:30:00+00:00", "odds": 10},
                    {"N°": "1", "CHEVAL": "HORSE ONE", "captured_at": "2026-10-08T08:00:00+00:00", "odds": 4},
                    {"N°": "2", "CHEVAL": "HORSE TWO", "captured_at": "2026-10-08T08:00:00+00:00", "odds": 12},
                ]
            raise AssertionError(f"unexpected table: {table}")

    result = get_today_quinte_odds_history(
        Client(),
        meeting_date=date(2026, 10, 8),
    )

    assert result["race"]["id"] == "race-1"
    assert [runner["number"] for runner in result["series"]] == ["1", "2"]
    assert [point["odds"] for point in result["series"][1]["points"]] == [12, 10]
