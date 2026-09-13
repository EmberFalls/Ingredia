import json
from html import escape
from urllib.parse import unquote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.db.models import BrandSource, CatalogReport, Ingredient, IngredientAlias, IngredientEncounter, Product, ScanHistory, UserAccount, UserProfile, UserSensitivity
from app.schemas import (
    AccountOut, AnalyzeTextRequest, AnalyzeTextResponse, AuthOut, CompareRequest, CompareResponse, LoginRequest, RegisterRequest,
    BrandSourceOut, CatalogReportOut, CatalogReportRequest, HistoryItemOut, IngredientOut, PreferenceOut, PreferenceRequest, ProductAnalysisRequest, ProductOut,
    EncounterInsightsOut, EncounterProductOut, IngredientEncounterOut, UserProfileOut, UserProfileRequest,
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


@router.get("/ingredients/{ingredient_id}/products", response_model=list[ProductOut])
def ingredient_products(ingredient_id: str, limit: int = 12, db: Session = Depends(get_db)) -> list[ProductOut]:
    """Catalog products whose declared label contains this canonical term or alias.

    This is discovery, not a formulation claim: the detail page labels it as a
    text-label match and sends users to the individual product record.
    """
    ingredient = db.scalar(select(Ingredient).options(selectinload(Ingredient.aliases)).where(Ingredient.id == ingredient_id))
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    terms = [ingredient.canonical_name, *(alias.alias for alias in ingredient.aliases)]
    conditions = [Product.ingredient_text.ilike(f"%{term}%") for term in terms if term.strip()]
    if not conditions:
        return []
    products = db.scalars(
        select(Product).where(or_(*conditions)).order_by(Product.name).limit(min(max(limit, 1), 50))
    ).all()
    return [_product_out(product) for product in products]


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


@router.get("/products/{product_id}/image")
def product_image(product_id: str, db: Session = Depends(get_db)) -> Response:
    """Return a browser-safe catalog image with an always-available fallback.

    Verified package photos are proxied only from curated product-content
    hosts used by the checked-in catalog. If a source host is temporarily
    unavailable, the card still gets an accurate local label illustration
    instead of a broken-image icon.
    """
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    image_url = (product.image_url or "").strip()
    if image_url.startswith("data:image/svg+xml,"):
        return Response(
            content=unquote(image_url.split(",", 1)[1]),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    parsed = urlparse(image_url)
    trusted_product_image_hosts = {
        "images.salsify.com",
        "images.openfoodfacts.net",
        "images.openfoodfacts.org",
    }
    if parsed.scheme == "https" and parsed.hostname in trusted_product_image_hosts:
        try:
            source = httpx.get(image_url, timeout=4.0, follow_redirects=True)
            content_type = source.headers.get("content-type", "").split(";", 1)[0]
            if source.is_success and content_type.startswith("image/"):
                return Response(
                    content=source.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except httpx.HTTPError:
            pass

    return Response(
        content=_catalog_image_fallback(product),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
        product_source_url=product.source_url,
        product_source_retrieved_at=product.source_retrieved_at,
        input_method="catalog",
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


@router.get("/users/{user_id}/insights/ingredients", response_model=EncounterInsightsOut)
def ingredient_encounters(user_id: str, request: Request, days: int = 7, db: Session = Depends(get_db)) -> EncounterInsightsOut:
    from datetime import datetime, timedelta, timezone

    _authorize_account_data(request, db, user_id)
    window_days = 30 if days == 30 else 7
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    history_rows = db.scalars(select(ScanHistory).where(ScanHistory.user_id == user_id, ScanHistory.created_at >= since)).all()
    history_ids = {row.id for row in history_rows}
    if not history_ids:
        return EncounterInsightsOut(window_days=window_days, total_analyses=0, ingredients=[], disclaimer=_encounter_disclaimer())
    rows = db.execute(
        select(IngredientEncounter, Ingredient, ScanHistory)
        .join(Ingredient, IngredientEncounter.ingredient_id == Ingredient.id)
        .join(ScanHistory, IngredientEncounter.history_id == ScanHistory.id)
        .where(IngredientEncounter.history_id.in_(history_ids))
        .order_by(IngredientEncounter.encountered_at.desc())
    ).all()
    grouped: dict[str, dict[str, object]] = {}
    for encounter, ingredient, history in rows:
        item = grouped.setdefault(ingredient.id, {"ingredient": ingredient, "rows": []})
        item["rows"].append((encounter, history))
    output = []
    for ingredient_id, item in grouped.items():
        ingredient = item["ingredient"]
        encounter_rows = item["rows"]
        products = [EncounterProductOut(
            id=history.product_id, name=history.product_name or "Ingredient list analysis",
            brand=history.product_brand, history_id=history.id,
        ) for _, history in encounter_rows]
        output.append(IngredientEncounterOut(
            ingredient_id=ingredient_id, canonical_name=ingredient.canonical_name,
            product_encounters=len(encounter_rows), last_seen_at=encounter_rows[0][0].encountered_at,
            products=products,
        ))
    output.sort(key=lambda item: (-item.product_encounters, item.canonical_name))
    return EncounterInsightsOut(window_days=window_days, total_analyses=len(history_rows), ingredients=output, disclaimer=_encounter_disclaimer())


@router.delete("/users/{user_id}/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_item(user_id: str, history_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    _authorize_account_data(request, db, user_id)
    item = db.scalar(select(ScanHistory).where(ScanHistory.id == history_id, ScanHistory.user_id == user_id))
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    db.execute(delete(IngredientEncounter).where(IngredientEncounter.history_id == item.id))
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/users/{user_id}/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(user_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    _authorize_account_data(request, db, user_id)
    history_ids = select(ScanHistory.id).where(ScanHistory.user_id == user_id)
    db.execute(delete(IngredientEncounter).where(IngredientEncounter.history_id.in_(history_ids)))
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
    a = {item.canonical_name for item in analysis_a.ingredients if item.canonical_name and item.match and item.match.status == "resolved"}
    b = {item.canonical_name for item in analysis_b.ingredients if item.canonical_name and item.match and item.match.status == "resolved"}
    contributions_a = {item.canonical_name: item.product_contribution for item in analysis_a.ingredients if item.canonical_name and item.match and item.match.status == "resolved"}
    contributions_b = {item.canonical_name: item.product_contribution for item in analysis_b.ingredients if item.canonical_name and item.match and item.match.status == "resolved"}
    reasons = []
    for name in sorted(a | b):
        delta = round(contributions_a.get(name, 0) - contributions_b.get(name, 0), 2)
        if delta:
            reasons.append({
                "type": "ingredient_only_in_a" if name in a - b else "ingredient_only_in_b" if name in b - a else "evidence_contribution_difference",
                "ingredient": name, "contribution_delta": delta,
            })
    reasons.sort(key=lambda item: abs(float(item["contribution_delta"])), reverse=True)
    return CompareResponse(
        product_a=analysis_a, product_b=analysis_b, shared_ingredients=sorted(a & b),
        only_in_a=sorted(a - b), only_in_b=sorted(b - a),
        score_delta=analysis_a.summary.concern_score - analysis_b.summary.concern_score,
        coverage_delta=round(analysis_a.summary.coverage - analysis_b.summary.coverage, 3),
        personal_alert_difference=analysis_a.summary.personal_alerts - analysis_b.summary.personal_alerts,
        unknown_difference=analysis_a.summary.unknown_ingredients - analysis_b.summary.unknown_ingredients,
        uncertain_difference=analysis_a.summary.uncertain_ingredients - analysis_b.summary.uncertain_ingredients,
        main_reasons=reasons[:5],
    )


def _ingredient_out(item: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=item.id, canonical_name=item.canonical_name, category=item.category, description=item.description,
        aliases=[alias.alias for alias in item.aliases],
        evidence=[{
            "id": record.id,
            "concern_type": record.concern_type, "severity": record.severity, "confidence": record.confidence,
            "source_name": record.source_name, "source_url": record.source_url, "summary": record.summary,
            "applicability": record.applicability, "limitations": record.limitations,
            "applicability_status": "background",
            "source_type": record.source_type, "evidence_quality": record.evidence_quality,
            "jurisdiction": record.jurisdiction, "exposure_route": record.exposure_route,
            "restriction_condition": record.restriction_condition,
            "retrieved_at": record.retrieved_at,
        } for record in item.evidence_records if record.is_active and record.source_url],
        families=[{
            "name": membership.family.name, "slug": membership.family.slug,
            "family_type": membership.family.family_type,
            "relationship_type": membership.relationship_type,
            "confidence": membership.confidence, "source_name": membership.source_name,
            "source_url": membership.source_url, "notes": membership.notes,
        } for membership in item.family_memberships],
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


def _catalog_image_fallback(product: Product) -> str:
    """A local labelled image used only when a source package photo is unavailable."""
    brand = escape(product.brand or "IngredientIQ")
    name = escape(product.name or "Catalog product")
    category = escape((product.category or "product").replace("_", " ").title())
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">'
        '<rect width="640" height="480" fill="#edf7f3"/>'
        '<rect x="74" y="44" width="492" height="392" rx="34" fill="#ffffff" stroke="#cde4db" stroke-width="4"/>'
        '<circle cx="320" cy="164" r="68" fill="#176b5b"/>'
        '<path d="M289 164h62M320 133v62" stroke="#dff4ec" stroke-width="12" stroke-linecap="round"/>'
        f'<text x="320" y="280" text-anchor="middle" font-family="Arial, sans-serif" font-size="31" font-weight="700" fill="#173a32">{brand}</text>'
        f'<text x="320" y="322" text-anchor="middle" font-family="Arial, sans-serif" font-size="25" fill="#31594e">{name}</text>'
        f'<text x="320" y="374" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" letter-spacing="2" fill="#6b887e">{category} · CATALOG LABEL</text>'
        '</svg>'
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
    try:
        snapshot = json.loads(item.analysis_snapshot) if item.analysis_snapshot else None
    except (TypeError, json.JSONDecodeError):
        snapshot = None
    return HistoryItemOut(
        id=item.id, product_id=item.product_id, product_name=item.product_name, product_brand=item.product_brand,
        product_category=item.product_category, product_image_url=item.product_image_url,
        product_source_name=item.product_source_name, product_source_type=item.product_source_type,
        raw_text=item.raw_text, concern_score=item.concern_score, coverage=item.coverage,
        analysis_snapshot=snapshot, scoring_version=item.scoring_version, evidence_version=item.evidence_version,
        created_at=item.created_at,
    )


def _json_list(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _encounter_disclaimer() -> str:
    return "These counts represent appearances in products you analyzed. They do not represent absorbed dose or biological exposure."
