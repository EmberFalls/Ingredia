import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.db.models import BrandSource, CatalogReport, Ingredient, IngredientAlias, Product, ScanHistory, UserAccount, UserProfile, UserSensitivity
from app.schemas import (
    AccountOut, AnalyzeTextRequest, AnalyzeTextResponse, AuthOut, CompareRequest, CompareResponse, LoginRequest, RegisterRequest,
    BrandSourceOut, CatalogReportOut, CatalogReportRequest, HistoryItemOut, IngredientOut, PreferenceOut, PreferenceRequest, ProductAnalysisRequest, ProductOut,
    UserProfileOut, UserProfileRequest,
)
from app.services.analysis import AnalysisService
from app.services.auth import account_display_name, account_for_token, create_session, hash_password, normalize_email, revoke_session, verify_password
from app.services.normalizer import IngredientNormalizer, normalize_key
from app.services.product_discovery import ProductDiscoveryService

router = APIRouter()


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="A valid session is required")
    return token.strip()


def _account_out(db: Session, account: UserAccount) -> AccountOut:
    return AccountOut(id=account.id, email=account.email, display_name=account_display_name(db, account))


def _authorize_account_data(request: Request, db: Session, user_id: str | None) -> None:
    """Protect persisted account data while retaining anonymous/local analysis.

    Historical development identifiers such as ``local-demo`` do not represent
    account records. Once a real account ID is used, its bearer session must
    match before profile, preference, history, or personalized analysis access.
    """
    if not user_id or not db.get(UserAccount, user_id):
        return
    account = account_for_token(db, _bearer_token(request))
    if not account or account.id != user_id:
        raise HTTPException(status_code=403, detail="That account does not belong to this session")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> AuthOut:
    email = normalize_email(request.email)
    if db.scalar(select(UserAccount.id).where(UserAccount.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for that email")
    account = UserAccount(email=email, password_hash=hash_password(request.password))
    db.add(account)
    db.flush()
    db.add(UserProfile(user_id=account.id, display_name=request.display_name.strip()))
    db.commit()
    db.refresh(account)
    return AuthOut(access_token=create_session(db, account.id), account=_account_out(db, account))


@router.post("/auth/login", response_model=AuthOut)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> AuthOut:
    account = db.scalar(select(UserAccount).where(UserAccount.email == normalize_email(request.email)))
    if not account or not verify_password(request.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return AuthOut(access_token=create_session(db, account.id), account=_account_out(db, account))


@router.get("/auth/me", response_model=AccountOut)
def current_account(request: Request, db: Session = Depends(get_db)) -> AccountOut:
    account = account_for_token(db, _bearer_token(request))
    if not account:
        raise HTTPException(status_code=401, detail="Your session has expired")
    return _account_out(db, account)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    revoke_session(db, _bearer_token(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/analyses/text", response_model=AnalyzeTextResponse, status_code=status.HTTP_201_CREATED)
def analyze_text(payload: AnalyzeTextRequest, request: Request, db: Session = Depends(get_db)) -> AnalyzeTextResponse:
    _authorize_account_data(request, db, payload.user_id)
    return AnalysisService(db).analyze(payload)


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
    products, catalog_status = await ProductDiscoveryService(db).search(query=query, brand=brand, category=category, barcode=barcode, limit=min(max(limit, 1), 120))
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
def analyze_product(product_id: str, payload: ProductAnalysisRequest, request: Request, db: Session = Depends(get_db)) -> AnalyzeTextResponse:
    _authorize_account_data(request, db, payload.user_id)
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
        user_id=payload.user_id,
        save_to_history=payload.save_to_history,
    ))


@router.post("/products/{product_id}/reports", response_model=CatalogReportOut, status_code=status.HTTP_201_CREATED)
def report_product(product_id: str, payload: CatalogReportRequest, request: Request, db: Session = Depends(get_db)) -> CatalogReportOut:
    _authorize_account_data(request, db, payload.user_id)
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    report = CatalogReport(product_id=product_id, user_id=payload.user_id, reason=payload.reason, details=payload.details)
    db.add(report)
    db.commit()
    db.refresh(report)
    return CatalogReportOut(
        id=report.id, product_id=report.product_id, user_id=report.user_id, reason=report.reason,
        details=report.details, status=report.status, created_at=report.created_at,
    )


@router.put("/users/{user_id}/preferences", response_model=PreferenceOut)
def add_preference(user_id: str, payload: PreferenceRequest, request: Request, db: Session = Depends(get_db)) -> PreferenceOut:
    _authorize_account_data(request, db, user_id)
    resolved = IngredientNormalizer(db).normalize(payload.ingredient_query)
    ingredient = resolved.ingredient
    if not ingredient:
        canonical_name = " ".join(payload.ingredient_query.strip().split())
        ingredient = Ingredient(
            canonical_name=canonical_name,
            category="user_defined",
            description="Personal ingredient term added by the user.",
        )
        ingredient.aliases = [
            IngredientAlias(
                alias=canonical_name,
                normalized_alias=normalize_key(canonical_name),
            )
        ]
        db.add(ingredient)
        db.flush()
    existing = db.scalar(select(UserSensitivity).where(UserSensitivity.user_id == user_id, UserSensitivity.ingredient_id == ingredient.id))
    if existing:
        existing.preference_type = payload.preference_type
    else:
        db.add(UserSensitivity(user_id=user_id, ingredient_id=ingredient.id, preference_type=payload.preference_type))
    db.commit()
    return PreferenceOut(ingredient_id=ingredient.id, canonical_name=ingredient.canonical_name, preference_type=payload.preference_type)


@router.get("/users/{user_id}/preferences", response_model=list[PreferenceOut])
def get_preferences(user_id: str, request: Request, db: Session = Depends(get_db)) -> list[PreferenceOut]:
    _authorize_account_data(request, db, user_id)
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


@router.delete("/users/{user_id}/preferences/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preference(user_id: str, ingredient_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    _authorize_account_data(request, db, user_id)
    preference = db.scalar(
        select(UserSensitivity).where(
            UserSensitivity.user_id == user_id,
            UserSensitivity.ingredient_id == ingredient_id,
        )
    )
    if not preference:
        raise HTTPException(status_code=404, detail="Preference not found")
    db.delete(preference)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/profile", response_model=UserProfileOut)
def get_profile(user_id: str, request: Request, db: Session = Depends(get_db)) -> UserProfileOut:
    _authorize_account_data(request, db, user_id)
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    return _profile_out(profile, user_id)


@router.put("/users/{user_id}/profile", response_model=UserProfileOut)
def save_profile(user_id: str, payload: UserProfileRequest, request: Request, db: Session = Depends(get_db)) -> UserProfileOut:
    _authorize_account_data(request, db, user_id)
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    profile.display_name = payload.display_name
    profile.avatar_url = payload.avatar_url
    profile.dietary_preferences = json.dumps(payload.dietary_preferences)
    profile.cultural_considerations = json.dumps(payload.cultural_considerations)
    profile.additional_requirements = payload.additional_requirements
    db.commit()
    db.refresh(profile)
    return _profile_out(profile, user_id)


@router.get("/users/{user_id}/history", response_model=list[HistoryItemOut])
def get_history(user_id: str, request: Request, limit: int = 30, db: Session = Depends(get_db)) -> list[HistoryItemOut]:
    _authorize_account_data(request, db, user_id)
    rows = db.scalars(
        select(ScanHistory).where(ScanHistory.user_id == user_id).order_by(ScanHistory.created_at.desc()).limit(min(max(limit, 1), 100))
    ).all()
    return [_history_out(row) for row in rows]


@router.delete("/users/{user_id}/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_item(user_id: str, history_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    _authorize_account_data(request, db, user_id)
    item = db.scalar(select(ScanHistory).where(ScanHistory.id == history_id, ScanHistory.user_id == user_id))
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/users/{user_id}/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(user_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    _authorize_account_data(request, db, user_id)
    db.execute(delete(ScanHistory).where(ScanHistory.user_id == user_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/comparisons", response_model=CompareResponse)
def compare(payload: CompareRequest, request: Request, db: Session = Depends(get_db)) -> CompareResponse:
    _authorize_account_data(request, db, payload.product_a.user_id)
    _authorize_account_data(request, db, payload.product_b.user_id)
    service = AnalysisService(db)
    analysis_a = service.analyze(payload.product_a)
    analysis_b = service.analyze(payload.product_b)
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
