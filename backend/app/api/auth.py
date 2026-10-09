from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth_service import current_profile, require_admin
from app.services.chariow import ChariowCheckoutError, create_checkout
from app.services.supabase_client import SupabaseClientWrapper

router = APIRouter(prefix="/auth", tags=["auth"])


class PromoteSubscriberRequest(BaseModel):
    user_id: str = Field(min_length=1)


class ChariowCheckoutRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone_number: str = Field(pattern=r"^[0-9]{5,15}$")
    phone_country_code: str = Field(pattern=r"^[A-Z]{2}$")


def _add_month(value: datetime) -> datetime:
    month = value.month % 12 + 1
    year = value.year + (1 if value.month == 12 else 0)
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


@router.get("/profile")
def profile(current_user: dict[str, Any] = Depends(current_profile)) -> dict[str, Any]:
    return current_user


@router.post("/chariow/checkout")
def chariow_checkout(
    request: ChariowCheckoutRequest,
    current_user: dict[str, Any] = Depends(current_profile),
) -> dict[str, str]:
    if current_user["role"] == "admin":
        raise HTTPException(status_code=403, detail="Admin accounts cannot purchase a subscription")
    try:
        checkout_url = create_checkout(
            user_id=current_user["id"],
            email=current_user["email"],
            first_name=request.first_name.strip(),
            last_name=request.last_name.strip(),
            phone_number=request.phone_number,
            phone_country_code=request.phone_country_code,
        )
    except ChariowCheckoutError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"checkout_url": checkout_url}


@router.get("/admin/users")
def list_users(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        profiles = SupabaseClientWrapper().list(
            "user_profiles",
            limit=1000,
            order_by=("created_at", "desc"),
        )
        now = datetime.now(timezone.utc)
        for user in profiles:
            role = user.get("role")
            if role == "admin":
                effective = "admin"
            elif role == "subscriber" and _is_active(user.get("subscriber_expires_at"), now):
                effective = "subscriber"
            elif role in {"demo", "subscriber"} and _is_active(user.get("demo_expires_at"), now):
                effective = "demo"
            else:
                effective = "simple"
            user["effective_role"] = effective
        return {"users": profiles}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not load account list") from exc


def _is_active(value: Any, now: datetime) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


@router.post("/admin/promote")
def promote_subscriber(
    request: PromoteSubscriberRequest,
    _: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    client = SupabaseClientWrapper()
    try:
        user = client.select_one(
            "user_profiles",
            filters=[("id", "eq", request.user_id)],
        )
        if not user:
            raise HTTPException(status_code=404, detail="Account not found")
        if user.get("role") == "admin":
            raise HTTPException(status_code=409, detail="Admin accounts cannot be promoted as subscribers")

        now = datetime.now(timezone.utc)
        current_expiry = user.get("subscriber_expires_at")
        if user.get("role") == "subscriber" and _is_active(current_expiry, now):
            current_expiry_dt = datetime.fromisoformat(current_expiry.replace("Z", "+00:00"))
            base = max(now, current_expiry_dt)
        else:
            base = now
        expires_at = _add_month(base)
        updated = client.update(
            "user_profiles",
            id_value=request.user_id,
            payload={
                "role": "subscriber",
                "subscriber_expires_at": expires_at.isoformat(),
                "updated_at": now.isoformat(),
            },
        )
        if not updated:
            raise HTTPException(status_code=502, detail="Subscriber access could not be updated")
        updated["effective_role"] = "subscriber"
        return {"user": updated}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not promote account") from exc
