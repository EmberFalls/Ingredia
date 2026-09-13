from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceOut(BaseModel):
    id: str
    concern_type: str
    severity: int
    confidence: float
    source_name: str
    source_url: str | None
    source_type: str | None = None
    evidence_quality: str | None = None
    jurisdiction: str | None = None
    exposure_route: str | None = None
    restriction_condition: str | None = None
    retrieved_at: datetime | None = None
    summary: str
    applicability: str
    applicability_status: str = "background"
    limitations: str | None


class AnalyzeTextRequest(BaseModel):
    ingredient_text: str = Field(min_length=1, max_length=20_000)
    product_name: str | None = Field(default=None, max_length=160)
    product_id: str | None = Field(default=None, max_length=36)
    product_brand: str | None = Field(default=None, max_length=160)
    product_category: str | None = Field(default=None, max_length=80)
    product_image_url: str | None = Field(default=None, max_length=2_500)
    product_source_name: str | None = Field(default=None, max_length=160)
    product_source_type: str | None = Field(default=None, max_length=40)
    product_source_url: str | None = Field(default=None, max_length=2_500)
    product_source_retrieved_at: datetime | None = None
    input_method: str = Field(default="user_pasted", pattern="^(user_pasted|ocr_confirmed|catalog)$")
    user_id: str | None = Field(default=None, max_length=100)
    save_to_history: bool = False


class MatchOut(BaseModel):
    method: str
    confidence: float
    status: str = "resolved"
    normalized_token: str
    matched_alias: str | None = None


class IngredientFamilyOut(BaseModel):
    name: str
    slug: str
    family_type: str
    relationship_type: str
    confidence: float
    source_name: str
    source_url: str
    notes: str | None = None


class IngredientOut(BaseModel):
    id: str
    canonical_name: str
    category: str | None
    description: str | None
    aliases: list[str] = []
    evidence: list[EvidenceOut] = []
    families: list[IngredientFamilyOut] = []


class PersonalAlertOut(BaseModel):
    ingredient_id: str | None = None
    canonical_name: str | None = None
    raw_label_term: str
    preference_type: str
    message: str


class IngredientAnalysisOut(BaseModel):
    position: int
    raw_token: str
    parent_context: str | None = None
    canonical_name: str | None
    ingredient_id: str | None = None
    match: MatchOut | None
    concern_score: int
    evidence: list[EvidenceOut]
    personal_alert: PersonalAlertOut | None
    families: list[IngredientFamilyOut] = []
    product_contribution: float = 0.0


class AnalysisSummaryOut(BaseModel):
    concern_score: int
    score_band: str
    coverage: float
    parsed_ingredients: int
    unknown_ingredients: int
    resolved_ingredients: int = 0
    uncertain_ingredients: int = 0
    personal_alerts: int
    high_confidence_flags: int


class AnalyzeTextResponse(BaseModel):
    analysis_id: str
    summary: AnalysisSummaryOut
    ingredients: list[IngredientAnalysisOut]
    unknowns: list[str]
    score_breakdown: dict[str, object]
    provenance: dict[str, object]
    limitations: list[str] = []
    disclaimer: str


class ProductOut(BaseModel):
    id: str
    name: str
    brand: str
    category: str | None
    barcode: str | None
    ingredient_text: str
    image_url: str | None
    description: str | None
    source_type: str
    source_name: str
    source_url: str | None
    source_confidence: float
    label_verified_at: datetime | None
    source_retrieved_at: datetime | None
    is_demo: bool
    ingredients_available: bool


class BrandSourceOut(BaseModel):
    id: str
    brand_name: str
    canonical_domain: str | None
    country: str | None
    search_strategy: str
    enabled: bool


class ProductAnalysisRequest(BaseModel):
    user_id: str | None = Field(default=None, max_length=100)
    save_to_history: bool = True


class CatalogReportRequest(BaseModel):
    user_id: str | None = Field(default=None, max_length=100)
    reason: str = Field(pattern="^(incorrect_ingredients|missing_ingredients|outdated_label|formulation_change|wrong_product|wrong_image|wrong_barcode|duplicate|other)$")
    details: str | None = Field(default=None, max_length=2_000)


class CatalogReportOut(CatalogReportRequest):
    id: str
    product_id: str
    status: str
    created_at: datetime | None


class PreferenceRequest(BaseModel):
    ingredient_query: str = Field(min_length=1, max_length=160)
    preference_type: str = Field(default="avoid", pattern="^(allergen|sensitivity|avoid)$")


class PreferenceOut(BaseModel):
    ingredient_id: str
    canonical_name: str
    preference_type: str


class UserProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    # Local mode accepts a small data URL so an avatar can persist without an upload service.
    avatar_url: str | None = Field(default=None, max_length=2_500_000)
    dietary_preferences: list[str] = Field(default_factory=list, max_length=30)
    cultural_considerations: list[str] = Field(default_factory=list, max_length=30)
    additional_requirements: str | None = Field(default=None, max_length=2_000)


class UserProfileOut(UserProfileRequest):
    user_id: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class AccountOut(BaseModel):
    id: str
    email: str
    display_name: str | None


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account: AccountOut


class HistoryItemOut(BaseModel):
    id: str
    product_id: str | None
    product_name: str | None
    product_brand: str | None
    product_category: str | None
    product_image_url: str | None
    product_source_name: str | None
    product_source_type: str | None
    raw_text: str
    concern_score: int
    coverage: float
    analysis_snapshot: dict[str, object] | None = None
    scoring_version: str | None = None
    evidence_version: str | None = None
    created_at: datetime | None


class CompareRequest(BaseModel):
    product_a: AnalyzeTextRequest
    product_b: AnalyzeTextRequest


class CompareResponse(BaseModel):
    product_a: AnalyzeTextResponse
    product_b: AnalyzeTextResponse
    shared_ingredients: list[str]
    only_in_a: list[str]
    only_in_b: list[str]
    score_delta: int
    coverage_delta: float
    personal_alert_difference: int
    unknown_difference: int
    uncertain_difference: int
    main_reasons: list[dict[str, object]]


class EncounterProductOut(BaseModel):
    id: str | None
    name: str
    brand: str | None = None
    history_id: str


class IngredientEncounterOut(BaseModel):
    ingredient_id: str
    canonical_name: str
    product_encounters: int
    last_seen_at: datetime | None
    products: list[EncounterProductOut]


class EncounterInsightsOut(BaseModel):
    window_days: int
    total_analyses: int
    ingredients: list[IngredientEncounterOut]
    disclaimer: str
