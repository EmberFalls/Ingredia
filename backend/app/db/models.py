from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def new_id() -> str:
    return str(uuid4())


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    canonical_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[IngredientAlias]] = relationship(back_populates="ingredient", cascade="all, delete-orphan")
    evidence_records: Mapped[list[EvidenceRecord]] = relationship(back_populates="ingredient", cascade="all, delete-orphan")


class IngredientAlias(Base):
    __tablename__ = "ingredient_aliases"
    __table_args__ = (UniqueConstraint("normalized_alias", name="uq_normalized_alias"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), index=True)
    alias: Mapped[str] = mapped_column(String(160))
    normalized_alias: Mapped[str] = mapped_column(String(160), index=True)
    ingredient: Mapped[Ingredient] = relationship(back_populates="aliases")


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), index=True)
    concern_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    applicability: Mapped[str] = mapped_column(String(80), default="general")
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ingredient: Mapped[Ingredient] = relationship(back_populates="evidence_records")


class UserSensitivity(Base):
    __tablename__ = "user_sensitivities"
    __table_args__ = (UniqueConstraint("user_id", "ingredient_id", name="uq_user_sensitivity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), index=True)
    preference_type: Mapped[str] = mapped_column(String(32), default="avoid")
    ingredient: Mapped[Ingredient] = relationship()


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    dietary_preferences: Mapped[str] = mapped_column(Text, default="[]")
    cultural_considerations: Mapped[str] = mapped_column(Text, default="[]")
    additional_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    product_brand: Mapped[str | None] = mapped_column(String(160), nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_source_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    product_source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    concern_score: Mapped[int] = mapped_column(Integer)
    coverage: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """A catalog entry with the label ingredients needed for analysis.

    The catalog deliberately stores the exact ingredient label supplied for the
    product. It does not infer formulation details or concentrations.
    """

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("name", "brand", name="uq_product_name_brand"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    brand: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ingredient_text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="demo")
    source_name: Mapped[str] = mapped_column(String(160), default="Local development catalog")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    label_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogReport(Base):
    """User-submitted data-quality report for a catalog record."""

    __tablename__ = "catalog_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(40))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product: Mapped[Product] = relationship()


class BrandSource(Base):
    """A registered brand source for future provider and official-site adapters."""

    __tablename__ = "brand_sources"
    __table_args__ = (UniqueConstraint("brand_name", "canonical_domain", name="uq_brand_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    brand_name: Mapped[str] = mapped_column(String(160), index=True)
    canonical_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    search_strategy: Mapped[str] = mapped_column(String(40), default="MANUAL_ONLY")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
