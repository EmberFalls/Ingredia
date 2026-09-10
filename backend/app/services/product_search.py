from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Product


class ProductSearchService:
    """Search the internal catalog with deterministic, explainable ranking.

    External providers will be added behind this same service, leaving callers
    independent of any single product-data source.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(self, *, query: str | None = None, brand: str | None = None, category: str | None = None, barcode: str | None = None, limit: int = 20) -> list[Product]:
        query = self._clean(query)
        brand = self._clean(brand)
        category = self._clean(category)
        barcode = self._clean(barcode)
        if not any((query, brand, category, barcode)):
            return []

        filters = []
        if barcode:
            filters.append(Product.barcode == barcode)
        if category:
            filters.append(Product.category.ilike(f"%{category}%"))
        if brand:
            filters.append(Product.brand.ilike(f"%{brand}%"))
        if query:
            pattern = f"%{query}%"
            filters.append(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern), Product.category.ilike(pattern)))

        rows = self.db.scalars(select(Product).where(and_(*filters)).limit(100)).all()
        return sorted(rows, key=lambda product: self._rank(product, query=query, brand=brand, barcode=barcode), reverse=True)[:limit]

    @staticmethod
    def _clean(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _rank(product: Product, *, query: str | None, brand: str | None, barcode: str | None) -> tuple[int, str, str]:
        name = product.name.casefold()
        product_brand = product.brand.casefold()
        score = 0
        if barcode and product.barcode == barcode:
            score += 1000
        if query:
            term = query.casefold()
            if name == term:
                score += 500
            elif product_brand == term:
                score += 450
            elif name.startswith(term):
                score += 300
            elif product_brand.startswith(term):
                score += 260
            else:
                score += sum(token in name or token in product_brand for token in ProductSearchService._tokens(term)) * 60
        if brand:
            term = brand.casefold()
            score += 350 if product_brand == term else 180 if product_brand.startswith(term) else 80
        return score, product_brand, name

    @staticmethod
    def _tokens(value: str) -> Iterable[str]:
        return (token for token in value.split() if token)
