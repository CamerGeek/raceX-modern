from app.core.config import Settings


def test_chariow_api_key_is_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CHARIOW_API_KEY", "test-chariow-key")

    settings = Settings(_env_file=None)

    assert settings.chariow_api_key == "test-chariow-key"
