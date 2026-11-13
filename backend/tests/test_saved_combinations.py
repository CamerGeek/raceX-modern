from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from fastapi import HTTPException

import app.api.races as races
from app.schemas.races import SavedCombinationRequest


USER = {"id": "user-1"}
PLAN = {
    "race_type": "trot",
    "combination_size": 3,
    "ready_tickets": [],
    "base": ["2"],
    "substitutes": [],
    "combinations": [["2", "4", "5"]],
}
RACE = {"race_type": "trot", "source": "turfomania", "summary": {"q_plus": True}}


class SavedCombinationClient:
    def __init__(self) -> None:
        self.inserted: dict[str, Any] | None = None
        self.list_filters: list[tuple[str, str, Any]] | None = None
        self.delete_filters: list[tuple[str, str, Any]] | None = None
        self.existing: dict[str, Any] | None = {"id": "saved-1"}

    def list(self, table: str, *, filters=None, **_kwargs: Any) -> list[dict[str, Any]]:
        assert table == "saved_combinations"
        self.list_filters = filters
        return [{"id": "saved-1"}]

    def insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert table == "saved_combinations"
        self.inserted = payload
        return {"id": "saved-1", **payload}

    def select_one(self, table: str, *, filters=None, **_kwargs: Any) -> dict[str, Any] | None:
        assert table == "saved_combinations"
        self.delete_filters = filters
        return self.existing

    def delete(self, table: str, *, filters) -> list[dict[str, Any]]:
        assert table == "saved_combinations"
        self.delete_filters = filters
        return [{"id": "saved-1"}]


def _client(monkeypatch: pytest.MonkeyPatch, client: SavedCombinationClient) -> None:
    monkeypatch.setattr(races, "SupabaseClientWrapper", lambda: client)
    monkeypatch.setattr(races, "_subscriber_quinte_frame", lambda *_args: (pd.DataFrame(), RACE))


def test_list_saved_combinations_scopes_results_to_user_and_race(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SavedCombinationClient()
    _client(monkeypatch, client)

    result = races.list_saved_subscriber_combinations("race-1", USER)

    assert result == {"saved_combinations": [{"id": "saved-1"}]}
    assert client.list_filters == [("user_id", "eq", "user-1"), ("race_id", "eq", "race-1")]


def test_save_combinations_records_account_owner_and_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SavedCombinationClient()
    _client(monkeypatch, client)

    result = races.save_subscriber_combinations(
        "race-1",
        SavedCombinationRequest(name="  My plan  ", plan=PLAN),
        USER,
    )

    assert result["saved_combination"]["id"] == "saved-1"
    assert client.inserted == {
        "user_id": "user-1",
        "race_id": "race-1",
        "name": "My plan",
        "plan": PLAN,
    }


def test_save_combinations_rejects_mismatched_ticket_size(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SavedCombinationClient()
    _client(monkeypatch, client)
    invalid_plan = {**PLAN, "combinations": [["2", "4"]]}

    with pytest.raises(HTTPException) as error:
        races.save_subscriber_combinations(
            "race-1",
            SavedCombinationRequest(name="My plan", plan=invalid_plan),
            USER,
        )

    assert error.value.status_code == 422
    assert client.inserted is None


def test_delete_saved_combinations_requires_matching_owner_and_race(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SavedCombinationClient()
    _client(monkeypatch, client)

    result = races.delete_saved_subscriber_combinations("race-1", "saved-1", USER)

    assert result == {"status": "deleted"}
    assert client.delete_filters == [
        ("id", "eq", "saved-1"),
        ("user_id", "eq", "user-1"),
        ("race_id", "eq", "race-1"),
    ]


def test_delete_saved_combinations_returns_not_found_for_other_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SavedCombinationClient()
    client.existing = None
    _client(monkeypatch, client)

    with pytest.raises(HTTPException) as error:
        races.delete_saved_subscriber_combinations("race-1", "saved-1", USER)

    assert error.value.status_code == 404
