from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TARGET_LANGUAGES = {"en": "EN", "es": "ES"}
MAX_TEXT_LENGTH = 100_000
CACHE_LIMIT = 512
GOOGLE_TRANSLATE_URL = "https://clients5.google.com/translate_a/t"
GOOGLE_TRANSLATE_FALLBACK_URL = "https://translate.google.com/translate_a/single"
GOOGLE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_cache: OrderedDict[tuple[str, str], str] = OrderedDict()
_cache_lock = threading.Lock()


def translate_text(text: str, locale: str) -> str:
    """Translate French source text, or return the source unchanged."""
    normalized = locale.strip().lower()[:2]
    if not text.strip() or normalized == "fr" or len(text) > MAX_TEXT_LENGTH:
        return text

    target_language = TARGET_LANGUAGES.get(normalized)
    if target_language is None:
        return text

    settings = get_settings()
    cache_key = (hashlib.sha256(text.encode("utf-8")).hexdigest(), normalized)
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached is not None:
            _cache.move_to_end(cache_key)
            return cached

    try:
        if settings.deepl_api_key.strip():
            translated = _translate_with_deepl(text, target_language, settings)
        else:
            translated = _translate_with_google(text, normalized, settings)
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Translation to %s failed: %s", normalized, exc)
        return text

    if not translated:
        return text

    with _cache_lock:
        _cache[cache_key] = translated
        _cache.move_to_end(cache_key)
        while len(_cache) > CACHE_LIMIT:
            _cache.popitem(last=False)
    return translated


def _translate_with_deepl(text: str, target_language: str, settings) -> str:
    api_key = settings.deepl_api_key.strip()
    response = requests.post(
        _deepl_endpoint(api_key, settings.deepl_api_url),
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
        data={
            "text": text,
            "source_lang": "FR",
            "target_lang": target_language,
            "preserve_formatting": "1",
        },
        timeout=settings.translation_timeout_seconds,
    )
    response.raise_for_status()
    return str(response.json()["translations"][0]["text"]).strip()


def _translate_with_google(text: str, locale: str, settings) -> str:
    # Unofficial keyless endpoints: used only until a DeepL key is configured.
    errors: list[Exception] = []
    for url in _google_endpoints(settings):
        try:
            return _request_google_translation(url, text, locale, settings)
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            errors.append(exc)
            logger.warning("Google translation via %s failed: %s", url, exc)
    raise errors[-1]


def _google_endpoints(settings) -> list[str]:
    primary = settings.google_translate_url.strip() or GOOGLE_TRANSLATE_URL
    if primary == GOOGLE_TRANSLATE_FALLBACK_URL:
        return [primary]
    return [primary, GOOGLE_TRANSLATE_FALLBACK_URL]


def _request_google_translation(url: str, text: str, locale: str, settings) -> str:
    headers = {"User-Agent": GOOGLE_USER_AGENT}
    timeout = settings.translation_timeout_seconds
    if url == GOOGLE_TRANSLATE_FALLBACK_URL:
        response = requests.post(
            url,
            params={"client": "gtx", "sl": "fr", "tl": locale, "dt": "t"},
            data={"q": text},
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        segments = response.json()[0] or []
        return "".join(str(segment[0]) for segment in segments if segment and segment[0]).strip()

    response = requests.post(
        url,
        params={"client": "dict-chrome-ex", "sl": "fr", "tl": locale},
        data={"q": text},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return "".join(str(part) for part in payload if part).strip()


def _deepl_endpoint(api_key: str, configured_url: str) -> str:
    if configured_url.strip():
        return configured_url.strip()
    # DeepL free keys end with ":fx" and use a separate host.
    return "https://api-free.deepl.com/v2/translate" if api_key.endswith(":fx") else "https://api.deepl.com/v2/translate"
