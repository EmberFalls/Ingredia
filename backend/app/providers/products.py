from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, HttpUrl


class ProviderProduct(BaseModel):
    """Normalized result returned by a catalog or official-brand provider."""

    external_id: str | None = None
    provider: str
    name: str
    brand: str | None = None
    category: str | None = None
    barcode: str | None = None
    image_url: HttpUrl | None = None
    product_url: HttpUrl | None = None
    ingredient_text: str | None = None
    country: str | None = None
    language: str | None = None
    source_confidence: float
    raw_payload: dict[str, object] | None = None


class ProductProvider(Protocol):
    """Contract used before a provider can be connected to discovery."""

    name: str

    async def search(self, query: str, *, brand: str | None = None, category: str | None = None, country: str | None = None, limit: int = 20) -> list[ProviderProduct]: ...

    async def get_by_barcode(self, barcode: str) -> ProviderProduct | None: ...

    async def get_product(self, external_id: str) -> ProviderProduct | None: ...
