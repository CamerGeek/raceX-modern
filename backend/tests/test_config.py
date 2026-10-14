from app.core.config import Settings


def test_chariow_api_key_is_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CHARIOW_API_KEY", "test-chariow-key")

    settings = Settings(_env_file=None)

    assert settings.chariow_api_key == "test-chariow-key"


def test_chariow_subscription_product_ids_are_configurable(monkeypatch) -> None:
    monkeypatch.setenv("CHARIOW_PRODUCT_ID", "monthly-product")
    monkeypatch.setenv("CHARIOW_WEEKLY_PRODUCT_ID", "weekly-product")
    monkeypatch.setenv("CHARIOW_ANNUAL_PRODUCT_ID", "annual-product")

    settings = Settings(_env_file=None)

    assert settings.chariow_plan_product_ids == {
        "weekly": "weekly-product",
        "monthly": "monthly-product",
        "annual": "annual-product",
    }


def test_chariow_subscription_product_ids_must_be_unique() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unique product ID"):
        Settings(
            _env_file=None,
            chariow_product_id="same-product",
            chariow_weekly_product_id="same-product",
            chariow_annual_product_id="annual-product",
        )
