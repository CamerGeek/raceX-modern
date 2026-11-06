from types import SimpleNamespace

import pytest

from app.services import translation_service
from app.services.translation_service import translate_text


@pytest.fixture(autouse=True)
def clear_translation_cache():
    translation_service._cache.clear()
    yield
    translation_service._cache.clear()


def settings(**overrides):
    values = {
        "deepl_api_key": "test-key:fx",
        "deepl_api_url": "",
        "google_translate_url": translation_service.GOOGLE_TRANSLATE_URL,
        "translation_timeout_seconds": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._payload


def test_deepl_translation_is_cached_per_locale(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_post(url, data, timeout, **kwargs):
        calls.append((url, data["target_lang"], data["text"]))
        return FakeResponse({"translations": [{"text": f"{data['target_lang']} text"}]})

    monkeypatch.setattr(translation_service.requests, "post", fake_post)
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings())

    assert translate_text("Bonjour", "en") == "EN text"
    assert translate_text("Bonjour", "en") == "EN text"
    assert translate_text("Bonjour", "es") == "ES text"

    assert len(calls) == 2
    assert calls[0][0] == "https://api-free.deepl.com/v2/translate"


def test_french_text_is_returned_without_calling_provider(monkeypatch) -> None:
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings())
    monkeypatch.setattr(
        translation_service.requests,
        "post",
        lambda *args, **kwargs: pytest.fail("No provider should be called for French"),
    )

    assert translate_text("Texte français", "fr") == "Texte français"


def test_no_deepl_key_uses_free_google_endpoint(monkeypatch) -> None:
    calls = []

    def fake_post(url, params, data, timeout, **kwargs):
        calls.append((url, params, data["q"], kwargs["headers"]))
        return FakeResponse(["English text"])

    monkeypatch.setattr(translation_service.requests, "post", fake_post)
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings(deepl_api_key=""))

    assert translate_text("Bonjour", "en") == "English text"

    assert calls == [(
        translation_service.GOOGLE_TRANSLATE_URL,
        {"client": "dict-chrome-ex", "sl": "fr", "tl": "en"},
        "Bonjour",
        {"User-Agent": translation_service.GOOGLE_USER_AGENT},
    )]


def test_google_falls_back_to_secondary_host(monkeypatch) -> None:
    urls = []

    def fake_post(url, params, data, timeout, **kwargs):
        urls.append(url)
        if url == translation_service.GOOGLE_TRANSLATE_URL:
            raise translation_service.requests.RequestException("429 too many requests")
        return FakeResponse([[["English text", "Bonjour"]], None, "fr"])

    monkeypatch.setattr(translation_service.requests, "post", fake_post)
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings(deepl_api_key=""))

    assert translate_text("Bonjour", "en") == "English text"
    assert urls == [translation_service.GOOGLE_TRANSLATE_URL, translation_service.GOOGLE_TRANSLATE_FALLBACK_URL]


def test_google_translation_joins_all_segments(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return FakeResponse(["First line.", "\nSecond line."])

    monkeypatch.setattr(translation_service.requests, "post", fake_post)
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings(deepl_api_key=""))

    assert translate_text("Première ligne.\nDeuxième.", "en") == "First line.\nSecond line."


def test_deepl_failure_returns_source_text(monkeypatch) -> None:
    def failing_post(*args, **kwargs):
        raise translation_service.requests.RequestException("network down")

    monkeypatch.setattr(translation_service.requests, "post", failing_post)
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings())

    assert translate_text("Bonjour", "en") == "Bonjour"


def test_google_failure_returns_source_text(monkeypatch) -> None:
    def failing_post(*args, **kwargs):
        raise translation_service.requests.RequestException("blocked")

    monkeypatch.setattr(translation_service.requests, "post", failing_post)
    monkeypatch.setattr(translation_service, "get_settings", lambda: settings(deepl_api_key=""))

    assert translate_text("Bonjour", "en") == "Bonjour"


def test_localized_analysis_does_not_mutate_the_cached_response(monkeypatch) -> None:
    from app.api import races
    from app.schemas.races import TurfomaniaQuinteAnalysisResponse

    response = TurfomaniaQuinteAnalysisResponse(
        race_id="race-id",
        race_type="trot",
        source="turfomania",
        row_count=1,
        columns=["N°"],
        rows=[{"N°": "1"}],
        model_version="test",
        prognosis=[],
        expert_commentary="Commentaire en français",
    )
    monkeypatch.setattr(races, "translate_text", lambda text, locale: "English commentary")

    localized = races._localize_commentary(response, "en")

    assert localized.expert_commentary == "English commentary"
    assert response.expert_commentary == "Commentaire en français"
    assert localized is not response
    assert races._localize_commentary(response, "fr") is response
