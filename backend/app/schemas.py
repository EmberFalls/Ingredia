from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceOut(BaseModel):
    concern_type: str
    severity: int
    confidence: float
    source_name: str
    source_url: str | None
    summary: str
    applicability: str
    limitations: str | None


class IngredientOut(BaseModel):
    id: str
    canonical_name: str
    category: str | None
    description: str | None
    aliases: list[str] = []
    evidence: list[EvidenceOut] = []


class AnalyzeTextRequest(BaseModel):
    ingredient_text: str = Field(min_length=1, max_length=20_000)
    product_name: str | None = Field(default=None, max_length=160)
    product_id: str | None = Field(default=None, max_length=36)
    product_brand: str | None = Field(default=None, max_length=160)
    product_category: str | None = Field(default=None, max_length=80)
    product_image_url: str | None = Field(default=None, max_length=2_500)
    product_source_name: str | None = Field(default=None, max_length=160)
    product_source_type: str | None = Field(default=None, max_length=40)
    user_id: str | None = Field(default=None, max_length=100)
    save_to_history: bool = False


class MatchOut(BaseModel):
    method: str
    confidence: float


class PersonalAlertOut(BaseModel):
    preference_type: str
    message: str


class IngredientAnalysisOut(BaseModel):
    position: int
    raw_token: str
    canonical_name: str | None
    match: MatchOut | None
    concern_score: int
    evidence: list[EvidenceOut]
    personal_alert: PersonalAlertOut | None


class AnalysisSummaryOut(BaseModel):
    concern_score: int
    score_band: str
    coverage: float
    parsed_ingredients: int
    unknown_ingredients: int
    personal_alerts: int
    high_confidence_flags: int


class AnalyzeTextResponse(BaseModel):
    analysis_id: str
    summary: AnalysisSummaryOut
    ingredients: list[IngredientAnalysisOut]
    unknowns: list[str]
    score_breakdown: dict[str, object]
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
    reason: str = Field(pattern="^(incorrect_ingredients|outdated_label|wrong_product|duplicate|other)$")
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
