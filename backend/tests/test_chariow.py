import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import chariow as chariow_api
from app.services import chariow as chariow_service
from app.services.subscription_plans import SubscriptionPlan


PRODUCT_IDS = {
    "weekly": "prd_czkpuc2g",
    "monthly": "prd_0hfy60zq",
    "annual": "prd_4f2ld5qj",
}


def _settings(**overrides):
    values = {
        "chariow_api_key": "",
        "chariow_pulse_secret": "test-pulse-secret",
        "chariow_product_id": PRODUCT_IDS["monthly"],
        "chariow_weekly_product_id": PRODUCT_IDS["weekly"],
        "chariow_annual_product_id": PRODUCT_IDS["annual"],
        "chariow_plan_product_ids": PRODUCT_IDS,
        "chariow_return_url": "https://racex.example/account?payment=complete",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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


def test_checkout_endpoint_uses_requested_plan_for_authenticated_user(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(auth_api.router, prefix="/api/v1")
    app.dependency_overrides[auth_api.current_profile] = lambda: {
        "id": "71bffbf1-46f4-4646-98fc-f92ea687f915",
        "email": "buyer@example.com",
        "role": "simple",
    }
    checkout_calls = []

    def fake_create_checkout(**kwargs):
        checkout_calls.append(kwargs)
        return "https://payment.chariow.com/checkout/123"

    monkeypatch.setattr(auth_api, "create_checkout", fake_create_checkout)

    response = TestClient(app).post(
        "/api/v1/auth/chariow/checkout",
        json={
            "first_name": "Awa",
            "last_name": "Traore",
            "phone_number": "70123456",
            "phone_country_code": "BF",
            "plan": "weekly",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://payment.chariow.com/checkout/123"}
    assert checkout_calls[0]["plan"] is SubscriptionPlan.WEEKLY


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


@pytest.mark.parametrize(
    ("plan", "product_id"),
    [
        ("weekly", PRODUCT_IDS["weekly"]),
        ("monthly", PRODUCT_IDS["monthly"]),
        ("annual", PRODUCT_IDS["annual"]),
    ],
)
def test_chariow_sale_activates_profile_using_verified_metadata(monkeypatch, plan, product_id) -> None:
    body = _payload(product_id=product_id)
    calls = []

    class FakeSupabase:
        def rpc(self, function, parameters):
            calls.append((function, parameters))
            return "activated"

    monkeypatch.setattr(
        chariow_api,
        "get_settings",
        lambda: _settings(),
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
                "p_plan": plan,
            },
        )
    ]


def test_chariow_rejects_invalid_signature(monkeypatch) -> None:
    body = _payload()
    monkeypatch.setattr(
        chariow_api,
        "get_settings",
        lambda: _settings(),
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
        lambda: _settings(),
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
        lambda: _settings(),
    )
    monkeypatch.setattr(chariow_api, "SupabaseClientWrapper", lambda: pytest.fail("Other products must not grant access"))

    response = _app().post(
        "/api/v1/webhooks/chariow",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


@pytest.mark.parametrize(
    ("plan", "expected_product_id"),
    [
        (SubscriptionPlan.WEEKLY, PRODUCT_IDS["weekly"]),
        (SubscriptionPlan.MONTHLY, PRODUCT_IDS["monthly"]),
        (SubscriptionPlan.ANNUAL, PRODUCT_IDS["annual"]),
    ],
)
def test_create_checkout_includes_account_metadata_and_return_url(
    monkeypatch, plan, expected_product_id
) -> None:
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
        lambda: _settings(chariow_api_key="test-api-key"),
    )
    monkeypatch.setattr(chariow_service.requests, "post", fake_post)

    checkout_url = chariow_service.create_checkout(
        user_id="71bffbf1-46f4-4646-98fc-f92ea687f915",
        email="buyer@example.com",
        first_name="Awa",
        last_name="Traore",
        phone_number="70123456",
        phone_country_code="BF",
        plan=plan,
    )

    assert checkout_url == "https://payment.chariow.com/checkout/123"
    assert request["url"] == chariow_service.CHARIOW_API_URL
    assert request["headers"] == {"Authorization": "Bearer test-api-key"}
    assert request["json"] == {
        "product_id": expected_product_id,
        "email": "buyer@example.com",
        "first_name": "Awa",
        "last_name": "Traore",
        "phone": {"number": "70123456", "country_code": "BF"},
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
        lambda: _settings(chariow_api_key="test-api-key"),
    )
    monkeypatch.setattr(chariow_service.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(chariow_service.ChariowCheckoutError):
        chariow_service.create_checkout(
            user_id="user-123",
            email="buyer@example.com",
            first_name="Awa",
            last_name="Traore",
            phone_number="70123456",
            phone_country_code="BF",
            plan=SubscriptionPlan.MONTHLY,
        )


def test_checkout_validation_error_reports_field_names_without_values(monkeypatch, caplog) -> None:
    class FakeResponse:
        ok = False
        status_code = 422

        @staticmethod
        def json():
            return {
                "errors": {
                    "first_name": ["The first name field is required."],
                    "phone.number": ["The phone number is invalid."],
                }
            }

    monkeypatch.setattr(
        chariow_service,
        "get_settings",
        lambda: _settings(chariow_api_key="test-api-key"),
    )
    monkeypatch.setattr(chariow_service.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(chariow_service.ChariowCheckoutError) as error:
        chariow_service.create_checkout(
            user_id="user-123",
            email="buyer@example.com",
            first_name="Awa",
            last_name="Traore",
            phone_number="70123456",
            phone_country_code="BF",
            plan=SubscriptionPlan.MONTHLY,
        )

    assert str(error.value) == "Chariow rejected checkout fields: first_name, phone.number"
    assert "buyer@example.com" not in caplog.text
    assert "Awa" not in caplog.text
    assert "70123456" not in caplog.text
