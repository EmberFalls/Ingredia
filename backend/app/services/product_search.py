from __future__ import annotations

from collections.abc import Iterable
import re

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

    def search(self, *, query: str | None = None, brand: str | None = None, category: str | None = None, market: str | None = None, barcode: str | None = None, limit: int = 20) -> list[Product]:
        query = self._clean(query)
        brand = self._clean(brand)
        category = self._clean(category)
        market = self._clean(market)
        barcode = self._clean(barcode)
        if not any((query, brand, category, market, barcode)):
            return list(
                self.db.scalars(
                    select(Product)
                    .order_by(Product.brand.asc(), Product.name.asc())
                    .limit(limit)
                ).all()
            )

        filters = []
        if barcode:
            filters.append(Product.barcode == barcode)
        if category:
            filters.append(Product.category.ilike(f"%{category}%"))
        if market:
            filters.append(Product.catalog_market.ilike(f"%{market}%"))
        if brand:
            filters.append(Product.brand.ilike(f"%{brand}%"))
        if query:
            pattern = f"%{query}%"
            filters.append(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern), Product.category.ilike(pattern)))

        rows = self.db.scalars(select(Product).where(and_(*filters)).limit(100)).all()
        return self.rank_and_deduplicate(
            rows, query=query, brand=brand, barcode=barcode, limit=limit,
        )

    @classmethod
    def rank_and_deduplicate(
        cls,
        products: Iterable[Product],
        *,
        query: str | None = None,
        brand: str | None = None,
        barcode: str | None = None,
        limit: int = 20,
    ) -> list[Product]:
        """Return one best catalog record for each likely product identity.

        Public catalogues frequently contain the same food in multiple package
        sizes, translations, or source revisions. A barcode remains distinct
        in storage, but search should show the clearest representative instead
        of presenting a user with near-identical choices.
        """
        # Descend on relevance and record quality, but use ascending brand/name
        # as a stable final tie-breaker.  Reversing the entire tuple would make
        # otherwise equal results appear in reverse alphabetical order.
        ordered = sorted(
            products,
            key=lambda product: cls._sort_key(product, query=query, brand=brand, barcode=barcode),
        )
        selected: list[Product] = []
        identities: set[str] = set()
        for product in ordered:
            identity = cls._identity(product)
            if identity in identities:
                continue
            identities.add(identity)
            selected.append(product)
            if len(selected) >= limit:
                break
        return selected

    @classmethod
    def _sort_key(
        cls,
        product: Product,
        *,
        query: str | None,
        brand: str | None,
        barcode: str | None,
    ) -> tuple[float, float, float, str, str]:
        score, completeness, confidence, product_brand, name = cls._rank(
            product, query=query, brand=brand, barcode=barcode,
        )
        return -score, -completeness, -confidence, product_brand, name

    @staticmethod
    def _clean(value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _rank(product: Product, *, query: str | None, brand: str | None, barcode: str | None) -> tuple[float, float, float, str, str]:
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
        # Relevance decides the group ordering. Within an otherwise similar
        # group, source and label quality decide which representative survives.
        source_quality = {
            "first_party_record": 5,
            "official_brand": 4,
            "public_catalog": 3,
            "saved_analysis": 2,
            "demo": 0,
        }.get(product.source_type, 1)
        image_quality = {
            "first_party_record": 3,
            "provider_barcode_match": 2,
            "needs_review": 1,
            "unavailable": 0,
        }.get(product.image_verification_status, 0)
        completeness = (
            (2 if product.ingredient_text.strip() else 0)
            + image_quality
            + source_quality
            + (1 if product.label_verified_at else 0)
        )
        return score, completeness, product.source_confidence, product_brand, name

    @classmethod
    def _identity(cls, product: Product) -> str:
        """Create a display-level identity without collapsing different flavours."""
        return f"{cls._identity_text(product.brand)}|{cls._identity_text(product.name)}"

    @staticmethod
    def _identity_text(value: str) -> str:
        # Package quantities distinguish barcodes, not what a person means by
        # a product search. Keep flavour words intact while removing size-only
        # suffixes such as 150 g, 500ml, 12-pack, or 6 ct.
        normalized = value.casefold()
        normalized = re.sub(
            r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|l|ml|cl|oz|lb|fl\s*oz|ct|count|pack|pk|pcs?|pieces?)\b",
            " ",
            normalized,
        )
        return " ".join(re.findall(r"[a-z0-9]+", normalized))

    @staticmethod
    def _tokens(value: str) -> Iterable[str]:
        return (token for token in value.split() if token)
