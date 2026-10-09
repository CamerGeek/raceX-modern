from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)
CHARIOW_API_URL = "https://api.chariow.com/v1/checkout"


class ChariowCheckoutError(Exception):
    pass


def _validation_fields(response: requests.Response) -> list[str]:
    try:
        result = response.json()
    except requests.exceptions.JSONDecodeError:
        return []
    if not isinstance(result, dict):
        return []
    errors = result.get("errors")
    if not isinstance(errors, dict):
        return []
    return [
        re.sub(r"[^a-zA-Z0-9_.]", "", field)[:80]
        for field in errors
        if isinstance(field, str) and re.sub(r"[^a-zA-Z0-9_.]", "", field)
    ][:10]


def create_checkout(
    *,
    user_id: str,
    email: str,
    first_name: str,
    last_name: str,
    phone_number: str,
    phone_country_code: str,
) -> str:
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
                "first_name": first_name,
                "last_name": last_name,
                "phone": {
                    "number": phone_number,
                    "country_code": phone_country_code,
                },
                "custom_metadata": {"racex_user_id": user_id},
                "redirect_url": settings.chariow_return_url,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning("Chariow checkout request failed: %s", exc)
        raise ChariowCheckoutError("Chariow checkout is temporarily unavailable") from exc

    if not response.ok:
        if response.status_code == 422:
            fields = _validation_fields(response)
            logger.warning(
                "Chariow checkout validation failed for fields: %s",
                ", ".join(fields) if fields else "unknown",
            )
            if fields:
                raise ChariowCheckoutError(
                    f"Chariow rejected checkout fields: {', '.join(fields)}"
                )
            raise ChariowCheckoutError("Chariow rejected the checkout details")
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
