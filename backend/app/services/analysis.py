from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import Ingredient, ScanHistory, UserSensitivity
from app.schemas import (
    AnalysisSummaryOut, AnalyzeTextRequest, AnalyzeTextResponse, EvidenceOut,
    IngredientAnalysisOut, MatchOut, PersonalAlertOut,
)
from app.services.normalizer import IngredientNormalizer
from app.services.parser import IngredientParser
from app.services.personal_context import PersonalContextService
from app.services.scoring import ScoringService, score_band

DISCLAIMER = "The score reflects evidence-backed ingredient concerns in the configured data sources. It is not a diagnosis or a measure of actual absorbed dose."


class AnalysisService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.parser = IngredientParser()
        self.normalizer = IngredientNormalizer(db)
        self.scorer = ScoringService()

    def analyze(self, request: AnalyzeTextRequest) -> AnalyzeTextResponse:
        tokens = self.parser.parse(request.ingredient_text)
        normalized = [self.normalizer.normalize(token) for token in tokens]
        user_preferences = self._preferences(request.user_id)
        personal_context = PersonalContextService(self.db, request.user_id)
        output: list[IngredientAnalysisOut] = []
        unknowns: list[str] = []
        score_inputs = []
        scored_ingredient_ids: set[str] = set()
        high_confidence_flags = 0
        alerts = 0
        for position, (token, resolved) in enumerate(zip(tokens, normalized)):
            if not resolved.ingredient:
                unknowns.append(token)
                context_match = personal_context.match(token, None, None)
                personal_alert = None
                if context_match:
                    alerts += 1
                    personal_alert = PersonalAlertOut(
                        preference_type=context_match.preference_type,
                        message=context_match.message,
                    )
                output.append(IngredientAnalysisOut(position=position, raw_token=token, canonical_name=None, match=None, concern_score=0, evidence=[], personal_alert=personal_alert))
                continue
            ingredient = resolved.ingredient
            evidence = [record for record in ingredient.evidence_records if record.is_active]
            ingredient_score = self.scorer.ingredient_score(evidence, request.product_category)
            if any(record.confidence >= 0.8 for record in evidence) and ingredient_score:
                high_confidence_flags += 1
            preference = user_preferences.get(ingredient.id)
            personal_alert = None
            context_match = personal_context.match(token, ingredient.canonical_name, preference)
            if context_match:
                alerts += 1
                personal_alert = PersonalAlertOut(
                    preference_type=context_match.preference_type,
                    message=context_match.message,
                )
            # Keep the full parsed output, but score a canonical ingredient only once.
            # Duplicate label entries should not inflate a product-level concern score.
            if ingredient.id not in scored_ingredient_ids:
                score_inputs.append((ingredient.canonical_name, evidence))
                scored_ingredient_ids.add(ingredient.id)
            output.append(IngredientAnalysisOut(
                position=position,
                raw_token=token,
                canonical_name=ingredient.canonical_name,
                match=MatchOut(method=resolved.method, confidence=resolved.confidence),
                concern_score=ingredient_score,
                evidence=[self._evidence_out(record) for record in evidence],
                personal_alert=personal_alert,
            ))
        product_score = self.scorer.score_product(score_inputs, request.product_category)
        coverage = round((len(tokens) - len(unknowns)) / len(tokens), 3) if tokens else 0.0
        response = AnalyzeTextResponse(
            analysis_id=str(uuid4()),
            summary=AnalysisSummaryOut(
                concern_score=product_score.score,
                score_band=score_band(product_score.score),
                coverage=coverage,
                parsed_ingredients=len(tokens),
                unknown_ingredients=len(unknowns),
                personal_alerts=alerts,
                high_confidence_flags=high_confidence_flags,
            ),
            ingredients=output,
            unknowns=unknowns,
            score_breakdown={"top_contributors": product_score.contributors, "scoring_version": get_settings().scoring_version},
            disclaimer=DISCLAIMER,
        )
        if request.save_to_history:
            self.db.add(ScanHistory(
                user_id=request.user_id, product_id=request.product_id, product_name=request.product_name,
                product_brand=request.product_brand, product_category=request.product_category,
                product_image_url=request.product_image_url, product_source_name=request.product_source_name,
                product_source_type=request.product_source_type, raw_text=request.ingredient_text,
                concern_score=product_score.score, coverage=coverage,
            ))
            self.db.commit()
        return response

    def _preferences(self, user_id: str | None) -> dict[str, str]:
        if not user_id:
            return {}
        rows = self.db.scalars(select(UserSensitivity).where(UserSensitivity.user_id == user_id)).all()
        return {row.ingredient_id: row.preference_type for row in rows}

    @staticmethod
    def _evidence_out(record: object) -> EvidenceOut:
        return EvidenceOut(
            concern_type=record.concern_type, severity=record.severity, confidence=record.confidence,
            source_name=record.source_name, source_url=record.source_url, summary=record.summary,
            applicability=record.applicability, limitations=record.limitations,
        )
