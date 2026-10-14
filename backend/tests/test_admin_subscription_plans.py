from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import auth as auth_api


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_api.router, prefix="/api/v1")
    app.dependency_overrides[auth_api.require_admin] = lambda: {
        "id": "admin-user",
        "role": "admin",
    }
    return TestClient(app)


@pytest.mark.parametrize("plan", ["weekly", "monthly", "annual"])
def test_admin_grants_selected_subscription_plan(monkeypatch, plan) -> None:
    calls = []
    user_id = "71bffbf1-46f4-4646-98fc-f92ea687f915"

    class FakeSupabase:
        def rpc(self, function, parameters):
            calls.append((function, parameters))
            return "activated"

    monkeypatch.setattr(auth_api, "SupabaseClientWrapper", FakeSupabase)

    response = _client().post(
        "/api/v1/auth/admin/promote",
        json={"user_id": user_id, "plan": plan},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "activated", "plan": plan}
    assert calls == [
        (
            "apply_admin_subscription_plan",
            {"p_user_id": user_id, "p_plan": plan},
        )
    ]


def test_admin_grant_defaults_to_monthly_for_existing_callers(monkeypatch) -> None:
    calls = []
    user_id = "71bffbf1-46f4-4646-98fc-f92ea687f915"

    class FakeSupabase:
        def rpc(self, function, parameters):
            calls.append(parameters)
            return "activated"

    monkeypatch.setattr(auth_api, "SupabaseClientWrapper", FakeSupabase)

    response = _client().post(
        "/api/v1/auth/admin/promote",
        json={"user_id": user_id},
    )

    assert response.status_code == 200
    assert calls == [{"p_user_id": user_id, "p_plan": "monthly"}]


def test_admin_grant_rejects_unknown_plan(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_api,
        "SupabaseClientWrapper",
        lambda: (_ for _ in ()).throw(AssertionError("Invalid plan must not call the database")),
    )

    response = _client().post(
        "/api/v1/auth/admin/promote",
        json={"user_id": "71bffbf1-46f4-4646-98fc-f92ea687f915", "plan": "lifetime"},
    )

    assert response.status_code == 422


def test_admin_grant_rejects_granting_to_an_admin(monkeypatch) -> None:
    class FakeSupabase:
        @staticmethod
        def rpc(function, parameters):
            return "admin"

    monkeypatch.setattr(auth_api, "SupabaseClientWrapper", FakeSupabase)

    response = _client().post(
        "/api/v1/auth/admin/promote",
        json={"user_id": "71bffbf1-46f4-4646-98fc-f92ea687f915", "plan": "weekly"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Admin accounts cannot be promoted as subscribers"
