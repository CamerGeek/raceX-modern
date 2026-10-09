from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)
CHARIOW_API_URL = "https://api.chariow.com/v1/checkout"


class ChariowCheckoutError(Exception):
    pass


def create_checkout(*, user_id: str, email: str) -> str:
    settings = get_settings()
    api_key = settings.chariow_api_key.strip()
    if not api_key:
        raise ChariowCheckoutError("Chariow checkout is not configured")

    try:
        response = requests.post(
            CHARIOW_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "product_id": settings.chariow_product_id,
                "email": email,
                "custom_metadata": {"racex_user_id": user_id},
                "redirect_url": settings.chariow_return_url,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning("Chariow checkout request failed: %s", exc)
        raise ChariowCheckoutError("Chariow checkout is temporarily unavailable") from exc

    if not response.ok:
        logger.warning("Chariow checkout returned HTTP %s", response.status_code)
        raise ChariowCheckoutError("Chariow could not create a checkout")

    try:
        result: Any = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        logger.error("Chariow checkout returned invalid JSON")
        raise ChariowCheckoutError("Chariow returned an invalid checkout response") from exc

    if not isinstance(result, dict):
        raise ChariowCheckoutError("Chariow returned an invalid checkout response")

    data = result.get("data")
    payment = data.get("payment") if isinstance(data, dict) else None
    checkout_url = payment.get("checkout_url") if isinstance(payment, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("step") != "payment"
        or not isinstance(checkout_url, str)
    ):
        raise ChariowCheckoutError("Chariow did not return a payable checkout")

    parsed_url = urlparse(checkout_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        logger.error("Chariow returned a non-HTTPS checkout URL")
        raise ChariowCheckoutError("Chariow returned an invalid checkout URL")

    return checkout_url
