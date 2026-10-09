import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chariow as chariow_api
from app.services import chariow as chariow_service


def _signed_headers(body: bytes, *, delivery_id: str | None = "del_123") -> dict[str, str]:
    signature = hmac.new(b"test-pulse-secret", body, hashlib.sha256).hexdigest()
    headers = {
        "x-chariow-signature": f"sha256={signature}",
        "x-pulse-event": "successful.sale",
        "x-pulse-id": "pulse_123",
        "content-type": "application/json",
    }
    if delivery_id:
        headers["x-pulse-delivery-id"] = delivery_id
    return headers


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(chariow_api.router, prefix="/api/v1")
    return TestClient(app)


def _payload(*, product_id: str = "prd_0hfy60zq") -> bytes:
    return json.dumps(
        {
            "event": "successful.sale",
            "sale": {
                "id": "sal_123",
                "status": "completed",
                "custom_metadata": {"racex_user_id": "71bffbf1-46f4-4646-98fc-f92ea687f915"},
            },
            "product": {"id": product_id},
        },
        separators=(",", ":"),
    ).encode("utf-8")


def test_chariow_sale_activates_profile_using_verified_metadata(monkeypatch) -> None:
    body = _payload()
    calls = []

    class FakeSupabase:
        def rpc(self, function, parameters):
            calls.append((function, parameters))
            return "activated"

    monkeypatch.setattr(
        chariow_api,
        "get_settings",
        lambda: SimpleNamespace(
            chariow_pulse_secret="test-pulse-secret",
            chariow_product_id="prd_0hfy60zq",
        ),
    )
    monkeypatch.setattr(chariow_api, "SupabaseClientWrapper", FakeSupabase)

    response = _app().post(
        "/api/v1/webhooks/chariow",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "activated"}
    assert calls == [
        (
            "apply_chariow_sale",
            {
                "p_delivery_id": "del_123",
                "p_sale_id": "sal_123",
                "p_user_id": "71bffbf1-46f4-4646-98fc-f92ea687f915",
            },
        )
    ]


def test_chariow_rejects_invalid_signature(monkeypatch) -> None:
    body = _payload()
    monkeypatch.setattr(
        chariow_api,
        "get_settings",
        lambda: SimpleNamespace(
            chariow_pulse_secret="test-pulse-secret",
            chariow_product_id="prd_0hfy60zq",
        ),
    )
    headers = _signed_headers(body)
    headers["x-chariow-signature"] = "sha256=" + ("0" * 64)

    response = _app().post(
        "/api/v1/webhooks/chariow",
        content=body,
        headers=headers,
    )

    assert response.status_code == 401


def test_chariow_ignores_dashboard_test_event_without_delivery_id(monkeypatch) -> None:
    body = json.dumps(
        {
            "event": "successful.sale",
            "note": "Dashboard test event",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    monkeypatch.setattr(
        chariow_api,
        "get_settings",
        lambda: SimpleNamespace(
            chariow_pulse_secret="test-pulse-secret",
            chariow_product_id="prd_0hfy60zq",
        ),
    )
    monkeypatch.setattr(
        chariow_api,
        "SupabaseClientWrapper",
        lambda: pytest.fail("Test pulses must not grant access"),
    )

    response = _app().post(
        "/api/v1/webhooks/chariow",
        content=body,
        headers=_signed_headers(body, delivery_id=None),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "test_received"}


def test_chariow_ignores_sales_for_other_products(monkeypatch) -> None:
    body = _payload(product_id="prd_other")
    monkeypatch.setattr(
        chariow_api,
        "get_settings",
        lambda: SimpleNamespace(
            chariow_pulse_secret="test-pulse-secret",
            chariow_product_id="prd_0hfy60zq",
        ),
    )
    monkeypatch.setattr(chariow_api, "SupabaseClientWrapper", lambda: pytest.fail("Other products must not grant access"))

    response = _app().post(
        "/api/v1/webhooks/chariow",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_create_checkout_includes_account_metadata_and_return_url(monkeypatch) -> None:
    request = {}

    class FakeResponse:
        ok = True

        @staticmethod
        def json():
            return {
                "data": {
                    "step": "payment",
                    "payment": {"checkout_url": "https://payment.chariow.com/checkout/123"},
                }
            }

    def fake_post(url, *, headers, json, timeout):
        request.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(
        chariow_service,
        "get_settings",
        lambda: SimpleNamespace(
            chariow_api_key="test-api-key",
            chariow_product_id="prd_0hfy60zq",
            chariow_return_url="https://racex.example/account?payment=complete",
        ),
    )
    monkeypatch.setattr(chariow_service.requests, "post", fake_post)

    checkout_url = chariow_service.create_checkout(
        user_id="71bffbf1-46f4-4646-98fc-f92ea687f915",
        email="buyer@example.com",
    )

    assert checkout_url == "https://payment.chariow.com/checkout/123"
    assert request["url"] == chariow_service.CHARIOW_API_URL
    assert request["headers"] == {"Authorization": "Bearer test-api-key"}
    assert request["json"] == {
        "product_id": "prd_0hfy60zq",
        "email": "buyer@example.com",
        "custom_metadata": {"racex_user_id": "71bffbf1-46f4-4646-98fc-f92ea687f915"},
        "redirect_url": "https://racex.example/account?payment=complete",
    }
    assert request["timeout"] == 15


def test_create_checkout_rejects_non_https_checkout_url(monkeypatch) -> None:
    class FakeResponse:
        ok = True

        @staticmethod
        def json():
            return {
                "data": {
                    "step": "payment",
                    "payment": {"checkout_url": "http://payment.chariow.com/checkout/123"},
                }
            }

    monkeypatch.setattr(
        chariow_service,
        "get_settings",
        lambda: SimpleNamespace(
            chariow_api_key="test-api-key",
            chariow_product_id="prd_0hfy60zq",
            chariow_return_url="https://racex.example/account?payment=complete",
        ),
    )
    monkeypatch.setattr(chariow_service.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(chariow_service.ChariowCheckoutError):
        chariow_service.create_checkout(user_id="user-123", email="buyer@example.com")
