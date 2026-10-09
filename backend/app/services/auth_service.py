from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.services.supabase_client import SupabaseClientWrapper


bearer_scheme = HTTPBearer(auto_error=False)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def effective_role(profile: dict[str, Any], *, now: datetime | None = None) -> str:
    role = profile.get("role")
    if role == "admin":
        return "admin"
    current_time = now or datetime.now(timezone.utc)
    if role == "subscriber":
        expires_at = _parse_datetime(profile.get("subscriber_expires_at"))
        if expires_at and expires_at > current_time:
            return "subscriber"
    if role in {"demo", "subscriber"}:
        demo_expires_at = _parse_datetime(profile.get("demo_expires_at"))
        if demo_expires_at and demo_expires_at > current_time:
            return "demo"
    return "simple"


def current_profile(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(status_code=503, detail="Authentication service is not configured")
    try:
        response = requests.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_key,
                "Authorization": f"Bearer {credentials.credentials}",
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")
        auth_user = response.json()
        user_id = auth_user.get("id")
        if not isinstance(user_id, str):
            raise HTTPException(status_code=401, detail="Invalid authenticated user")
        profile = SupabaseClientWrapper().select_one(
            "user_profiles",
            filters=[("id", "eq", user_id)],
        )
        if not profile:
            raise HTTPException(status_code=403, detail="Account profile is not provisioned")
        return {
            "id": user_id,
            "email": auth_user.get("email") or profile.get("email") or "",
            "phone": profile.get("phone"),
            "role": effective_role(profile),
            "stored_role": profile.get("role", "simple"),
            "demo_expires_at": profile.get("demo_expires_at"),
            "subscriber_expires_at": profile.get("subscriber_expires_at"),
        }
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Authentication service is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load account profile") from exc


def require_roles(*roles: str):
    def dependency(profile: dict[str, Any] = Depends(current_profile)) -> dict[str, Any]:
        if profile["role"] not in roles:
            raise HTTPException(status_code=403, detail="This account does not have access to this feature")
        return profile

    return dependency


require_admin = require_roles("admin")
require_subscriber_features = require_roles("demo", "subscriber", "admin")
