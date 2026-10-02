from datetime import date

import pandas as pd

from app.services.meeting_persistence import _normalize_integer_columns, _normalize_trot_row, persist_scraped_meeting


def test_normalize_grouped_meter_distance() -> None:
    payload = _normalize_integer_columns({"DIST.": "3\u00a0100m", "DIST": "2 700m"})

    assert payload["DIST."] == 3100
    assert payload["DIST"] == 2700


def test_normalize_numeric_dash_and_decimal_comma() -> None:
    payload = _normalize_integer_columns({"AGE": "-", "DIST.": "69,0", "DIST": "57,5", "POIDS": "61,0", "COTE": "-", "IF": "5,25"})

    assert payload["AGE"] is None
    assert payload["DIST."] == 69.0
    assert payload["DIST"] == 57.5
    assert payload["POIDS"] == 61.0
    assert payload["COTE"] is None
    assert payload["IF"] == 5.25


def test_normalize_trot_music_from_performance_column() -> None:
    row = _normalize_trot_row({"MUSIQUE": None, "SEXE": None, "SEX": "H", "DERNIÈRES PERF.": "1a 2a 3a"})

    assert row["SEXE"] == "H"
    assert row["MUSIQUE"] == "1a 2a 3a"


def test_normalize_trot_record_time() -> None:
    row = _normalize_trot_row({"REC.": '1\'12"1'})

    assert row["REC."] == 72


class _PersistenceClient:
    def __init__(self) -> None:
        self.upsert_conflicts: list[str | None] = []
        self.meeting_filters: list[list[tuple[str, str, object]]] = []
        self.race_filters: list[list[tuple[str, str, object]]] = []

    def select_one(self, table: str, *, filters: list[tuple[str, str, object]] | None = None, **_: object) -> dict | None:
        if table == "meetings":
            self.meeting_filters.append(filters or [])
        if table == "races":
            self.race_filters.append(filters or [])
        return None

    def insert(self, table: str, payload: dict) -> dict:
        return {"id": "meeting-1" if table == "meetings" else "race-1", **payload}

    def update(self, table: str, **_: object) -> dict:
        raise AssertionError(f"unexpected update for {table}")

    def upsert(self, table: str, *, key: str, key_value: object, payload: dict, on_conflict: str | None = None) -> dict:
        self.upsert_conflicts.append(on_conflict)
        return {"id": "runner-1", **payload}


def test_persist_uses_runner_unique_constraint_for_upsert() -> None:
    client = _PersistenceClient()
    frame = pd.DataFrame([{"REF_COURSE": "R1", "N°": "1", "CHEVAL": "Horse"}])

    result = persist_scraped_meeting(
        frame,
        meeting_date=date(2026, 9, 12),
        meeting_name="Test meeting",
        meeting_url="https://example.test/meeting",
        race_type="flat",
        client=client,
    )

    assert result["runner_count"] == 1
    assert client.meeting_filters == [[("source", "eq", "zone-turf"), ("meeting_date", "eq", "2026-09-12"), ("url", "eq", "https://example.test/meeting")]]
    assert client.upsert_conflicts == ['race_id,"N°"']
    assert client.race_filters == [[("meeting_id", "eq", "meeting-1"), ("race_key", "eq", "R1")]]