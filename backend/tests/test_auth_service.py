from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.auth import _add_month, _is_active
from app.services import auth_service
from app.services.auth_service import effective_role
from fastapi.security import HTTPAuthorizationCredentials


def test_admin_role_never_expires() -> None:
    profile = {
        "role": "admin",
        "subscriber_expires_at": "2020-01-01T00:00:00Z",
        "demo_expires_at": "2020-01-01T00:00:00Z",
    }

    assert effective_role(profile, now=datetime(2026, 10, 8, tzinfo=timezone.utc)) == "admin"


def test_demo_expires_to_simple_access() -> None:
    profile = {"role": "demo", "demo_expires_at": "2026-10-07T00:00:00Z"}

    assert effective_role(profile, now=datetime(2026, 10, 8, tzinfo=timezone.utc)) == "simple"


def test_active_subscriber_keeps_access_until_expiry() -> None:
    profile = {
        "role": "subscriber",
        "subscriber_expires_at": "2026-11-08T00:00:00Z",
        "demo_expires_at": "2026-10-01T00:00:00Z",
    }

    assert effective_role(profile, now=datetime(2026, 10, 8, tzinfo=timezone.utc)) == "subscriber"
    assert effective_role(profile, now=datetime(2026, 11, 9, tzinfo=timezone.utc)) == "simple"


def test_calendar_month_extension_handles_month_end() -> None:
    assert _add_month(datetime(2026, 1, 31, 12, tzinfo=timezone.utc)) == datetime(
        2026, 2, 28, 12, tzinfo=timezone.utc
    )


def test_active_expiry_comparison_is_timezone_aware() -> None:
    assert _is_active("2026-10-09T00:00:00Z", datetime(2026, 10, 8, tzinfo=timezone.utc))
    assert not _is_active("2026-10-07T00:00:00Z", datetime(2026, 10, 8, tzinfo=timezone.utc))


def test_current_profile_includes_saved_phone(monkeypatch) -> None:
    class AuthResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, str]:
            return {"id": "user-id", "email": "user@example.com"}

    class ProfileClient:
        @staticmethod
        def select_one(*args, **kwargs) -> dict[str, str]:
            return {
                "id": "user-id",
                "email": "user@example.com",
                "phone": "+226 70 00 00 00",
                "role": "demo",
                "demo_expires_at": "2099-01-01T00:00:00Z",
            }

    monkeypatch.setattr(
        auth_service,
        "get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_key="test-key"),
    )
    monkeypatch.setattr(auth_service.requests, "get", lambda *args, **kwargs: AuthResponse())
    monkeypatch.setattr(auth_service, "SupabaseClientWrapper", ProfileClient)

    profile = auth_service.current_profile(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")
    )

    assert profile["phone"] == "+226 70 00 00 00"
