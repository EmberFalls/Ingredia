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
    product_category: str | None = Field(default=None, max_length=80)
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
    ingredient_text: str
    image_url: str | None
    description: str | None


class ProductAnalysisRequest(BaseModel):
    user_id: str | None = Field(default=None, max_length=100)
    save_to_history: bool = True


class PreferenceRequest(BaseModel):
    ingredient_query: str = Field(min_length=1, max_length=160)
    preference_type: str = Field(default="avoid", pattern="^(allergen|sensitivity|avoid)$")


class PreferenceOut(BaseModel):
    ingredient_id: str
    canonical_name: str
    preference_type: str


class CompareRequest(BaseModel):
    product_a: AnalyzeTextRequest
    product_b: AnalyzeTextRequest


class CompareResponse(BaseModel):
    product_a: AnalyzeTextResponse
    product_b: AnalyzeTextResponse
    shared_ingredients: list[str]
    only_in_a: list[str]
    only_in_b: list[str]
