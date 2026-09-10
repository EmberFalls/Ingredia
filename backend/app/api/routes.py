import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.db.models import BrandSource, CatalogReport, Ingredient, IngredientAlias, Product, ScanHistory, UserProfile, UserSensitivity
from app.schemas import (
    AnalyzeTextRequest, AnalyzeTextResponse, CompareRequest, CompareResponse,
    BrandSourceOut, CatalogReportOut, CatalogReportRequest, HistoryItemOut, IngredientOut, PreferenceOut, PreferenceRequest, ProductAnalysisRequest, ProductOut,
    UserProfileOut, UserProfileRequest,
)
from app.services.analysis import AnalysisService
from app.services.normalizer import IngredientNormalizer
from app.services.product_discovery import ProductDiscoveryService

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
async def search_products(
    response: Response,
    query: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    barcode: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    """Search the internal catalog by product, brand, category, or barcode."""
    products, catalog_status = await ProductDiscoveryService(db).search(query=query, brand=brand, category=category, barcode=barcode, limit=min(max(limit, 1), 50))
    response.headers["X-Catalog-Result"] = catalog_status
    return [_product_out(product) for product in products]


@router.get("/brands", response_model=list[BrandSourceOut])
def search_brands(query: str | None = None, db: Session = Depends(get_db)) -> list[BrandSourceOut]:
    statement = select(BrandSource).order_by(BrandSource.brand_name).limit(20)
    if query and query.strip():
        statement = statement.where(BrandSource.brand_name.ilike(f"%{query.strip()}%"))
    brands = db.scalars(statement).all()
    return [_brand_out(brand) for brand in brands]


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
    if not product.ingredient_text.strip():
        raise HTTPException(status_code=409, detail="Product identified, but its ingredient label is unavailable. Paste or upload the label to continue.")
    return AnalysisService(db).analyze(AnalyzeTextRequest(
        ingredient_text=product.ingredient_text,
        product_id=product.id,
        product_name=product.name,
        product_brand=product.brand,
        product_category=product.category,
        product_image_url=product.image_url,
        product_source_name=product.source_name,
        product_source_type=product.source_type,
        user_id=request.user_id,
        save_to_history=request.save_to_history,
    ))


@router.post("/products/{product_id}/reports", response_model=CatalogReportOut, status_code=status.HTTP_201_CREATED)
def report_product(product_id: str, request: CatalogReportRequest, db: Session = Depends(get_db)) -> CatalogReportOut:
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    report = CatalogReport(product_id=product_id, user_id=request.user_id, reason=request.reason, details=request.details)
    db.add(report)
    db.commit()
    db.refresh(report)
    return CatalogReportOut(
        id=report.id, product_id=report.product_id, user_id=report.user_id, reason=report.reason,
        details=report.details, status=report.status, created_at=report.created_at,
    )


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


@router.get("/users/{user_id}/preferences", response_model=list[PreferenceOut])
def get_preferences(user_id: str, db: Session = Depends(get_db)) -> list[PreferenceOut]:
    rows = db.execute(
        select(UserSensitivity, Ingredient)
        .join(Ingredient, UserSensitivity.ingredient_id == Ingredient.id)
        .where(UserSensitivity.user_id == user_id)
        .order_by(Ingredient.canonical_name)
    ).all()
    return [
        PreferenceOut(ingredient_id=ingredient.id, canonical_name=ingredient.canonical_name, preference_type=sensitivity.preference_type)
        for sensitivity, ingredient in rows
    ]


@router.get("/users/{user_id}/profile", response_model=UserProfileOut)
def get_profile(user_id: str, db: Session = Depends(get_db)) -> UserProfileOut:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    return _profile_out(profile, user_id)


@router.put("/users/{user_id}/profile", response_model=UserProfileOut)
def save_profile(user_id: str, request: UserProfileRequest, db: Session = Depends(get_db)) -> UserProfileOut:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    profile.display_name = request.display_name
    profile.avatar_url = request.avatar_url
    profile.dietary_preferences = json.dumps(request.dietary_preferences)
    profile.cultural_considerations = json.dumps(request.cultural_considerations)
    profile.additional_requirements = request.additional_requirements
    db.commit()
    db.refresh(profile)
    return _profile_out(profile, user_id)


@router.get("/users/{user_id}/history", response_model=list[HistoryItemOut])
def get_history(user_id: str, limit: int = 30, db: Session = Depends(get_db)) -> list[HistoryItemOut]:
    rows = db.scalars(
        select(ScanHistory).where(ScanHistory.user_id == user_id).order_by(ScanHistory.created_at.desc()).limit(min(max(limit, 1), 100))
    ).all()
    return [_history_out(row) for row in rows]


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
        barcode=item.barcode, ingredient_text=item.ingredient_text, image_url=item.image_url, description=item.description,
        source_type=item.source_type, source_name=item.source_name, source_url=item.source_url,
        source_confidence=item.source_confidence, label_verified_at=item.label_verified_at,
        source_retrieved_at=item.source_retrieved_at, is_demo=item.is_demo,
        ingredients_available=bool(item.ingredient_text.strip()),
    )


def _brand_out(item: BrandSource) -> BrandSourceOut:
    return BrandSourceOut(
        id=item.id, brand_name=item.brand_name, canonical_domain=item.canonical_domain, country=item.country,
        search_strategy=item.search_strategy, enabled=item.enabled,
    )


def _profile_out(item: UserProfile | None, user_id: str) -> UserProfileOut:
    if not item:
        return UserProfileOut(user_id=user_id)
    return UserProfileOut(
        user_id=user_id, display_name=item.display_name, avatar_url=item.avatar_url,
        dietary_preferences=_json_list(item.dietary_preferences),
        cultural_considerations=_json_list(item.cultural_considerations),
        additional_requirements=item.additional_requirements,
    )


def _history_out(item: ScanHistory) -> HistoryItemOut:
    return HistoryItemOut(
        id=item.id, product_id=item.product_id, product_name=item.product_name, product_brand=item.product_brand,
        product_category=item.product_category, product_image_url=item.product_image_url,
        product_source_name=item.product_source_name, product_source_type=item.product_source_type,
        raw_text=item.raw_text, concern_score=item.concern_score, coverage=item.coverage, created_at=item.created_at,
    )


def _json_list(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded) else []
    except (TypeError, json.JSONDecodeError):
        return []
