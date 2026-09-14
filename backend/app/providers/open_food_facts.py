from __future__ import annotations

import re
import asyncio

import httpx

from app.core.config import get_settings
from app.providers.products import ProviderProduct
from app.services.translation import CatalogTranslationService


class ProductProviderUnavailable(RuntimeError):
    """The public catalog could not be reached or returned a server error."""


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
        self.translator = CatalogTranslationService()
        self.translation_semaphore = asyncio.Semaphore(
            max(settings.catalog_translation_concurrency, 1)
        )

    async def search(self, query: str, *, brand: str | None = None, category: str | None = None, country: str | None = None, limit: int = 20) -> list[ProviderProduct]:
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": min(max(limit, 1), 20),
            "fields": "code,product_name,product_name_en,brands,categories,categories_en,image_front_url,ingredients_text,ingredients_text_en,url,lang",
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
        normalized = await asyncio.gather(*(
            self._normalize(item) for item in products if isinstance(item, dict)
        ))
        return [item for item in normalized if item]

    async def get_by_barcode(self, barcode: str) -> ProviderProduct | None:
        normalized = re.sub(r"\D", "", barcode)
        if not 8 <= len(normalized) <= 14:
            return None
        payload = await self._get_json(
            f"/api/v2/product/{normalized}.json",
            {"fields": "code,product_name,product_name_en,brands,categories,categories_en,image_front_url,ingredients_text,ingredients_text_en,url,lang"},
        )
        product = payload.get("product") if payload else None
        return await self._normalize(product) if isinstance(product, dict) else None

    async def get_product(self, external_id: str) -> ProviderProduct | None:
        return await self.get_by_barcode(external_id)

    async def popular_in_india(self, limit: int = 100) -> list[ProviderProduct]:
        """Return image-backed, analyzable popular products tagged for India.

        This is intentionally a public-catalog import, not a claim that the
        manufacturer has independently verified every imported record.
        """
        target = min(max(limit, 1), 120)
        # The current structured search API is served from the `.net` host.
        # Keep the existing legacy search host untouched for compatibility,
        # but use the documented v2 endpoint for this country-filtered import.
        results: list[ProviderProduct] = []
        seen: set[str] = set()
        # Some high-popularity records lack either a usable front image or a
        # declared ingredient list. Continue through a few pages so the local
        # set reaches the requested size without accepting incomplete records.
        for page in range(1, 6):
            payload = await self._get_json_from_base(
                "https://world.openfoodfacts.net",
                "/api/v2/search",
                {
                    "countries_tags_en": "india",
                    "sort_by": "popularity_key",
                    "page": page,
                    "page_size": target,
                    "fields": "code,product_name,product_name_en,brands,categories,categories_en,image_front_url,ingredients_text,ingredients_text_en,url,lang",
                },
            )
            products = payload.get("products") if payload else None
            if not isinstance(products, list) or not products:
                break
            normalized = await asyncio.gather(*(
                self._normalize(item) for item in products if isinstance(item, dict)
            ))
            for item in normalized:
                if not item or not item.barcode or not item.image_url or not item.ingredient_text:
                    continue
                if item.barcode in seen:
                    continue
                seen.add(item.barcode)
                item.country = "India"
                results.append(item)
                if len(results) == target:
                    return results
        return results

    async def _get_json(self, path: str, params: dict[str, object]) -> dict[str, object] | None:
        return await self._get_json_from_base(self.base_url, path, params)

    async def _get_json_from_base(self, base_url: str, path: str, params: dict[str, object]) -> dict[str, object] | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "IngredientIntelligence/0.1 (catalog lookup)"}) as client:
                response = await client.get(f"{base_url.rstrip('/')}{path}", params=params)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else None
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise ProductProviderUnavailable("Open Food Facts returned an unavailable response") from error
        except httpx.RequestError as error:
            raise ProductProviderUnavailable("Open Food Facts could not be reached") from error
        except ValueError:
            return None

    async def _normalize(self, item: dict[str, object]) -> ProviderProduct | None:
        language = self._text(item.get("lang"))
        english_name = self._text(item.get("product_name_en"))
        source_is_english = bool(language and language.casefold().startswith("en"))
        original_name = self._text(item.get("product_name"))
        name = english_name or (original_name if source_is_english else None)
        barcode = self._text(item.get("code"))
        if not barcode:
            return None
        # Only use provider fields which are explicitly English, or an entire
        # record explicitly marked English. This avoids silently putting
        # untranslated product, category, or ingredient copy into the UI.
        description = None
        if not name and original_name:
            # A broad catalog search can contain several non-English records.
            # Keep its optional presentation translations bounded so the
            # product lookup itself remains responsive and respectful of the
            # public translation endpoint.
            async with self.translation_semaphore:
                translated_name = await self.translator.to_english(
                    original_name, language
                )
            if not translated_name:
                return None
            name = translated_name
            description = (
                f"English translation of the provider’s {language or 'non-English'} product title. "
                f"Original catalog title: {original_name}."
            )
        if not name:
            return None
        ingredients = self._text(item.get("ingredients_text_en")) or (
            self._text(item.get("ingredients_text")) if source_is_english else None
        )
        image = self._text(item.get("image_front_url"))
        url = self._text(item.get("url")) or f"{self.base_url}/product/{barcode}"
        return ProviderProduct(
            external_id=barcode, provider=self.name, name=name, brand=self._text(item.get("brands")),
            category=self._text(item.get("categories_en")) or (
                self._text(item.get("categories")) if source_is_english else None
            ), barcode=barcode, image_url=image,
            product_url=url, ingredient_text=ingredients, description=description,
            language="en" if english_name or description else language,
            source_confidence=0.8 if ingredients else 0.45,
            raw_payload={"barcode": barcode, "language": language, "english_name": english_name},
        )

    @staticmethod
    def _text(value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None
