from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.services.supabase_client import SupabaseClientWrapper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
MAX_PULSE_BODY_BYTES = 1_000_000


async def _read_limited_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PULSE_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook payload is too large")
    return bytes(body)


def _valid_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/chariow")
async def chariow_pulse(request: Request) -> dict[str, str]:
    settings = get_settings()
    pulse_secret = settings.chariow_pulse_secret.strip()
    if not pulse_secret:
        logger.error("Chariow Pulse signing secret is not configured")
        raise HTTPException(status_code=503, detail="Chariow webhook is not configured")

    raw_body = await _read_limited_body(request)
    signature = request.headers.get("x-chariow-signature", "")
    if not _valid_signature(raw_body, signature, pulse_secret):
        raise HTTPException(status_code=401, detail="Invalid Chariow signature")

    try:
        payload: Any = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Chariow event")

    event = request.headers.get("x-pulse-event")
    if not event or payload.get("event") != event:
        raise HTTPException(status_code=400, detail="Chariow event header does not match payload")
    if event != "successful.sale":
        return {"status": "ignored"}

    delivery_id = request.headers.get("x-pulse-delivery-id")
    if not delivery_id:
        if "note" in payload:
            return {"status": "test_received"}
        raise HTTPException(status_code=400, detail="Missing Chariow delivery ID")
    if len(delivery_id) > 255:
        raise HTTPException(status_code=400, detail="Invalid Chariow delivery ID")

    sale = payload.get("sale")
    product = payload.get("product")
    metadata = sale.get("custom_metadata") if isinstance(sale, dict) else None
    if (
        not isinstance(sale, dict)
        or not isinstance(product, dict)
        or sale.get("status") != "completed"
        or product.get("id") != settings.chariow_product_id
        or not isinstance(metadata, dict)
    ):
        logger.error("Ignoring Chariow sale event with unexpected sale or product data")
        return {"status": "ignored"}

    sale_id = sale.get("id")
    user_id = metadata.get("racex_user_id")
    if not isinstance(sale_id, str) or not sale_id or len(sale_id) > 255:
        logger.error("Ignoring Chariow sale event without a valid sale ID")
        return {"status": "ignored"}
    if not isinstance(user_id, str):
        logger.error("Ignoring Chariow sale %s without RaceX account metadata", sale_id)
        return {"status": "ignored"}
    try:
        normalized_user_id = str(UUID(user_id))
    except ValueError:
        logger.error("Ignoring Chariow sale %s with invalid RaceX account metadata", sale_id)
        return {"status": "ignored"}

    try:
        result = SupabaseClientWrapper().rpc(
            "apply_chariow_sale",
            {
                "p_delivery_id": delivery_id,
                "p_sale_id": sale_id,
                "p_user_id": normalized_user_id,
            },
        )
    except Exception as exc:
        logger.exception("Could not apply Chariow sale %s", sale_id)
        raise HTTPException(status_code=503, detail="Could not apply Chariow sale") from exc

    if result not in {"activated", "duplicate"}:
        logger.error("Chariow sale %s returned an unexpected processing result", sale_id)
        raise HTTPException(status_code=503, detail="Could not apply Chariow sale")
    return {"status": result}
