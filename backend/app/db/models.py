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


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
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
    ingredient_text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
