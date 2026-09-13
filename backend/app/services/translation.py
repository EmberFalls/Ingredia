"""Small, bounded translation adapter for public product-catalog copy.

Only public provider metadata is sent to this service—never user labels,
profiles, preferences, history, or analysis results. Translation is used for
presentation and keeps the original name in the product description.
"""

from __future__ import annotations

from html import unescape

import httpx

from app.core.config import get_settings


class CatalogTranslationService:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.catalog_translation_enabled
        self.base_url = settings.catalog_translation_base_url.rstrip("/")
        self.timeout = settings.catalog_translation_timeout_seconds

    async def to_english(self, text: str, source_language: str | None) -> str | None:
        if not self.enabled or not text.strip() or not source_language:
            return None
        # The public endpoint accepts at most 500 bytes per request. Product
        # titles are intentionally capped to a conservative value.
        encoded = text.strip().encode("utf-8")[:450]
        source = source_language.split("-", 1)[0].casefold()
        if not source or source == "en":
            return text.strip()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "Ingredia/0.1 catalog translation"}) as client:
                response = await client.get(
                    self.base_url,
                    params={"q": encoded.decode("utf-8", errors="ignore"), "langpair": f"{source}|en"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        translated = payload.get("responseData", {}).get("translatedText") if isinstance(payload, dict) else None
        if not isinstance(translated, str):
            return None
        result = unescape(translated).strip()
        return result or None
