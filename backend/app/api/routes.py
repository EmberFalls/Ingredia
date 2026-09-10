from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.db.models import Ingredient, IngredientAlias, Product, UserSensitivity
from app.schemas import (
    AnalyzeTextRequest, AnalyzeTextResponse, CompareRequest, CompareResponse,
    IngredientOut, PreferenceOut, PreferenceRequest, ProductAnalysisRequest, ProductOut,
)
from app.services.analysis import AnalysisService
from app.services.normalizer import IngredientNormalizer

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyses/text", response_model=AnalyzeTextResponse, status_code=status.HTTP_201_CREATED)
def analyze_text(request: AnalyzeTextRequest, db: Session = Depends(get_db)) -> AnalyzeTextResponse:
    return AnalysisService(db).analyze(request)


@router.get("/ingredients", response_model=list[IngredientOut])
def search_ingredients(query: str, db: Session = Depends(get_db)) -> list[IngredientOut]:
    if not query.strip():
        return []
    term = f"%{query.strip()}%"
    rows = db.scalars(
        select(Ingredient).options(selectinload(Ingredient.aliases), selectinload(Ingredient.evidence_records)).where(
            or_(Ingredient.canonical_name.ilike(term), Ingredient.aliases.any(IngredientAlias.alias.ilike(term)))
        ).limit(20)
    ).unique().all()
    return [_ingredient_out(row) for row in rows]


@router.get("/ingredients/{ingredient_id}", response_model=IngredientOut)
def ingredient_detail(ingredient_id: str, db: Session = Depends(get_db)) -> IngredientOut:
    item = db.scalar(select(Ingredient).options(selectinload(Ingredient.aliases), selectinload(Ingredient.evidence_records)).where(Ingredient.id == ingredient_id))
    if not item:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return _ingredient_out(item)


@router.get("/products", response_model=list[ProductOut])
def search_products(query: str, db: Session = Depends(get_db)) -> list[ProductOut]:
    """Find local catalog products by either product name or company/brand."""
    if not query.strip():
        return []
    term = f"%{query.strip()}%"
    products = db.scalars(
        select(Product).where(or_(Product.name.ilike(term), Product.brand.ilike(term))).order_by(Product.brand, Product.name).limit(20)
    ).all()
    return [_product_out(product) for product in products]


@router.get("/products/{product_id}", response_model=ProductOut)
def product_detail(product_id: str, db: Session = Depends(get_db)) -> ProductOut:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_out(product)


@router.post("/products/{product_id}/analyze", response_model=AnalyzeTextResponse, status_code=status.HTTP_201_CREATED)
def analyze_product(product_id: str, request: ProductAnalysisRequest, db: Session = Depends(get_db)) -> AnalyzeTextResponse:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return AnalysisService(db).analyze(AnalyzeTextRequest(
        ingredient_text=product.ingredient_text,
        product_name=f"{product.brand} {product.name}",
        product_category=product.category,
        user_id=request.user_id,
        save_to_history=request.save_to_history,
    ))


@router.put("/users/{user_id}/preferences", response_model=PreferenceOut)
def add_preference(user_id: str, request: PreferenceRequest, db: Session = Depends(get_db)) -> PreferenceOut:
    resolved = IngredientNormalizer(db).normalize(request.ingredient_query)
    if not resolved.ingredient:
        raise HTTPException(status_code=404, detail="Ingredient could not be reliably identified")
    existing = db.scalar(select(UserSensitivity).where(UserSensitivity.user_id == user_id, UserSensitivity.ingredient_id == resolved.ingredient.id))
    if existing:
        existing.preference_type = request.preference_type
    else:
        db.add(UserSensitivity(user_id=user_id, ingredient_id=resolved.ingredient.id, preference_type=request.preference_type))
    db.commit()
    return PreferenceOut(ingredient_id=resolved.ingredient.id, canonical_name=resolved.ingredient.canonical_name, preference_type=request.preference_type)


@router.post("/comparisons", response_model=CompareResponse)
def compare(request: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    service = AnalysisService(db)
    analysis_a = service.analyze(request.product_a)
    analysis_b = service.analyze(request.product_b)
    a = {item.canonical_name for item in analysis_a.ingredients if item.canonical_name}
    b = {item.canonical_name for item in analysis_b.ingredients if item.canonical_name}
    return CompareResponse(product_a=analysis_a, product_b=analysis_b, shared_ingredients=sorted(a & b), only_in_a=sorted(a - b), only_in_b=sorted(b - a))


def _ingredient_out(item: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=item.id, canonical_name=item.canonical_name, category=item.category, description=item.description,
        aliases=[alias.alias for alias in item.aliases],
        evidence=[{
            "concern_type": record.concern_type, "severity": record.severity, "confidence": record.confidence,
            "source_name": record.source_name, "source_url": record.source_url, "summary": record.summary,
            "applicability": record.applicability, "limitations": record.limitations,
        } for record in item.evidence_records if record.is_active],
    )


def _product_out(item: Product) -> ProductOut:
    return ProductOut(
        id=item.id, name=item.name, brand=item.brand, category=item.category,
        ingredient_text=item.ingredient_text, image_url=item.image_url, description=item.description,
    )
