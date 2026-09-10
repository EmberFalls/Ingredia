from __future__ import annotations

import re

import httpx

from app.core.config import get_settings
from app.providers.products import ProviderProduct


class OpenFoodFactsProvider:
    """Read-only adapter for the Open Food Facts public catalog.

    Results are normalized before entering the application so provider-specific
    response shapes never leak into scoring or API routes.
    """

    name = "Open Food Facts"

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.open_food_facts_base_url.rstrip("/")
        self.timeout = settings.product_discovery_timeout_seconds

    async def search(self, query: str, *, brand: str | None = None, category: str | None = None, country: str | None = None, limit: int = 20) -> list[ProviderProduct]:
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": min(max(limit, 1), 20),
            "fields": "code,product_name,brands,categories,image_front_url,ingredients_text,ingredients_text_en,url,lang",
        }
        if brand:
            params["tagtype_0"] = "brands"
            params["tag_contains_0"] = "contains"
            params["tag_0"] = brand
        if category:
            params["tagtype_1"] = "categories"
            params["tag_contains_1"] = "contains"
            params["tag_1"] = category
        payload = await self._get_json("/cgi/search.pl", params)
        if not payload:
            return []
        products = payload.get("products")
        if not isinstance(products, list):
            return []
        return [result for item in products if isinstance(item, dict) if (result := self._normalize(item))]

    async def get_by_barcode(self, barcode: str) -> ProviderProduct | None:
        normalized = re.sub(r"\D", "", barcode)
        if not 8 <= len(normalized) <= 14:
            return None
        payload = await self._get_json(
            f"/api/v2/product/{normalized}.json",
            {"fields": "code,product_name,brands,categories,image_front_url,ingredients_text,ingredients_text_en,url,lang"},
        )
        product = payload.get("product") if payload else None
        return self._normalize(product) if isinstance(product, dict) else None

    async def get_product(self, external_id: str) -> ProviderProduct | None:
        return await self.get_by_barcode(external_id)

    async def _get_json(self, path: str, params: dict[str, object]) -> dict[str, object] | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "IngredientIntelligence/0.1 (catalog lookup)"}) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else None
        except (httpx.HTTPError, ValueError):
            return None

    def _normalize(self, item: dict[str, object]) -> ProviderProduct | None:
        name = self._text(item.get("product_name"))
        barcode = self._text(item.get("code"))
        if not name or not barcode:
            return None
        ingredients = self._text(item.get("ingredients_text_en")) or self._text(item.get("ingredients_text"))
        image = self._text(item.get("image_front_url"))
        url = self._text(item.get("url")) or f"{self.base_url}/product/{barcode}"
        return ProviderProduct(
            external_id=barcode, provider=self.name, name=name, brand=self._text(item.get("brands")),
            category=self._text(item.get("categories")), barcode=barcode, image_url=image,
            product_url=url, ingredient_text=ingredients, language=self._text(item.get("lang")),
            source_confidence=0.8 if ingredients else 0.45,
            raw_payload={"barcode": barcode, "language": self._text(item.get("lang"))},
        )

    @staticmethod
    def _text(value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None
