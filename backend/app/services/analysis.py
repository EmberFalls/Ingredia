from __future__ import annotations

from uuid import uuid4
import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import Ingredient, IngredientEncounter, ScanHistory, UserSensitivity
from app.schemas import (
    AnalysisSummaryOut, AnalyzeTextRequest, AnalyzeTextResponse, EvidenceOut,
    IngredientAnalysisOut, IngredientFamilyOut, MatchOut, PersonalAlertOut,
)
from app.services.normalizer import IngredientNormalizer
from app.services.parser import IngredientParser
from app.services.personal_context import PersonalContextService
from app.services.scoring import ScoringService, score_band

DISCLAIMER = "The score reflects evidence-backed ingredient concerns in the configured data sources. It is not a diagnosis or a measure of actual absorbed dose."
LIMITATIONS = [
    "Ingredient presence does not establish concentration, absorbed dose, biological exposure, or individual outcome.",
    "Unknown and uncertain terms reduce analysis coverage and do not add concern points solely because they are unresolved.",
    "Personal alerts are separate from the general evidence-backed concern score.",
]


class AnalysisService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.parser = IngredientParser()
        self.normalizer = IngredientNormalizer(db)
        self.scorer = ScoringService()

    def analyze(self, request: AnalyzeTextRequest) -> AnalyzeTextResponse:
        analysis_id = str(uuid4())
        parsed_tokens = self.parser.parse_with_context(request.ingredient_text)
        tokens = [item.text for item in parsed_tokens]
        normalized = [self.normalizer.normalize(token) for token in tokens]
        user_preferences = self._preferences(request.user_id)
        personal_context = PersonalContextService(self.db, request.user_id)
        output: list[IngredientAnalysisOut] = []
        unknowns: list[str] = []
        uncertain_count = 0
        resolved_count = 0
        score_inputs = []
        scored_ingredient_ids: set[str] = set()
        high_confidence_flags = 0
        alerts = 0
        for position, (token, resolved, parsed) in enumerate(zip(tokens, normalized, parsed_tokens)):
            match = MatchOut(
                method=resolved.method,
                confidence=resolved.confidence,
                status=resolved.status,
                normalized_token=resolved.normalized_token,
                matched_alias=resolved.matched_alias,
            )
            if resolved.status == "unknown" or not resolved.ingredient:
                unknowns.append(token)
                output.append(IngredientAnalysisOut(position=position, raw_token=token, parent_context=parsed.parent_context, canonical_name=None, match=match, concern_score=0, evidence=[], personal_alert=None))
                continue
            if resolved.status == "uncertain":
                uncertain_count += 1
                output.append(IngredientAnalysisOut(
                    position=position, raw_token=token, parent_context=parsed.parent_context, ingredient_id=resolved.ingredient.id,
                    canonical_name=resolved.ingredient.canonical_name, match=match, concern_score=0,
                    evidence=[], personal_alert=None, families=[], product_contribution=0,
                ))
                continue
            ingredient = resolved.ingredient
            resolved_count += 1
            evidence = [record for record in ingredient.evidence_records if record.is_active and record.source_url]
            ingredient_score = self.scorer.ingredient_score(evidence, request.product_category)
            if any(record.confidence >= 0.8 for record in evidence) and ingredient_score:
                high_confidence_flags += 1
            preference = user_preferences.get(ingredient.id)
            personal_alert = None
            context_match = personal_context.match(token, ingredient.canonical_name, preference)
            if context_match:
                alerts += 1
                personal_alert = PersonalAlertOut(
                    ingredient_id=ingredient.id,
                    canonical_name=ingredient.canonical_name,
                    raw_label_term=token,
                    preference_type=context_match.preference_type,
                    message=context_match.message,
                )
            # Keep the full parsed output, but score a canonical ingredient only once.
            # Duplicate label entries should not inflate a product-level concern score.
            if ingredient.id not in scored_ingredient_ids:
                score_inputs.append((ingredient.id, ingredient.canonical_name, evidence))
                scored_ingredient_ids.add(ingredient.id)
            output.append(IngredientAnalysisOut(
                position=position,
                raw_token=token,
                parent_context=parsed.parent_context,
                ingredient_id=ingredient.id,
                canonical_name=ingredient.canonical_name,
                match=match,
                concern_score=ingredient_score,
                evidence=[self._evidence_out(record, request.product_category) for record in evidence],
                personal_alert=personal_alert,
                families=self._families_out(ingredient),
            ))
        product_score = self.scorer.score_product(score_inputs, request.product_category)
        contribution_by_id = {str(item["ingredient_id"]): float(item["contribution"]) for item in product_score.contributors}
        output = [item.model_copy(update={
            "product_contribution": contribution_by_id.get(item.ingredient_id or "", 0.0)
            if item.match and item.match.status == "resolved" else 0.0,
        }) for item in output]
        coverage = round(resolved_count / len(tokens), 3) if tokens else 0.0
        provenance = self._provenance(request)
        response = AnalyzeTextResponse(
            analysis_id=analysis_id,
            summary=AnalysisSummaryOut(
                concern_score=product_score.score,
                score_band=score_band(product_score.score),
                coverage=coverage,
                parsed_ingredients=len(tokens),
                unknown_ingredients=len(unknowns),
                resolved_ingredients=resolved_count,
                uncertain_ingredients=uncertain_count,
                personal_alerts=alerts,
                high_confidence_flags=high_confidence_flags,
            ),
            ingredients=output,
            unknowns=unknowns,
            score_breakdown={
                "top_contributors": product_score.contributors,
                "scoring_version": get_settings().scoring_version,
                "evidence_version": get_settings().evidence_version,
            },
            provenance=provenance,
            limitations=LIMITATIONS,
            disclaimer=DISCLAIMER,
        )
        if request.save_to_history:
            history = ScanHistory(
                user_id=request.user_id, product_id=request.product_id, product_name=request.product_name,
                product_brand=request.product_brand, product_category=request.product_category,
                product_image_url=request.product_image_url, product_source_name=request.product_source_name,
                product_source_type=request.product_source_type, raw_text=request.ingredient_text,
                concern_score=product_score.score, coverage=coverage,
                analysis_snapshot=json.dumps(response.model_dump(mode="json")),
                scoring_version=get_settings().scoring_version,
                evidence_version=get_settings().evidence_version,
            )
            self.db.add(history)
            self.db.flush()
            for ingredient_id in scored_ingredient_ids:
                self.db.add(IngredientEncounter(
                    history_id=history.id, user_id=request.user_id or "local-demo",
                    product_id=request.product_id, ingredient_id=ingredient_id,
                ))
            self.db.commit()
        return response

    def _preferences(self, user_id: str | None) -> dict[str, str]:
        if not user_id:
            return {}
        rows = self.db.scalars(select(UserSensitivity).where(UserSensitivity.user_id == user_id)).all()
        return {row.ingredient_id: row.preference_type for row in rows}

    @staticmethod
    def _evidence_out(record: object, product_category: str | None = None) -> EvidenceOut:
        return EvidenceOut(
            id=record.id,
            concern_type=record.concern_type, severity=record.severity, confidence=record.confidence,
            source_name=record.source_name, source_url=record.source_url, summary=record.summary,
            applicability=record.applicability, limitations=record.limitations,
            applicability_status=ScoringService.applicability_status(record, product_category),
            source_type=record.source_type, evidence_quality=record.evidence_quality,
            jurisdiction=record.jurisdiction, exposure_route=record.exposure_route,
            restriction_condition=record.restriction_condition,
            retrieved_at=record.retrieved_at,
        )

    @staticmethod
    def _families_out(ingredient: Ingredient) -> list[IngredientFamilyOut]:
        return [IngredientFamilyOut(
            name=membership.family.name, slug=membership.family.slug,
            family_type=membership.family.family_type,
            relationship_type=membership.relationship_type,
            confidence=membership.confidence, source_name=membership.source_name,
            source_url=membership.source_url, notes=membership.notes,
        ) for membership in ingredient.family_memberships]

    @staticmethod
    def _provenance(request: AnalyzeTextRequest) -> dict[str, object]:
        if request.input_method == "catalog":
            return {
                "input_type": "catalog",
                "label_source_type": request.product_source_type or "catalog",
                "source_name": request.product_source_name or "Product catalog",
                "source_url": request.product_source_url,
                "retrieved_at": request.product_source_retrieved_at.isoformat() if request.product_source_retrieved_at else None,
                "product_id": request.product_id,
            }
        if request.input_method == "ocr_confirmed":
            return {"input_type": "ocr_confirmed", "label_source_type": "user_uploaded_label", "source_name": "User-uploaded label; OCR text reviewed by user", "source_url": None, "retrieved_at": None}
        return {"input_type": "user_pasted", "label_source_type": "user_input", "source_name": "User-pasted ingredient list", "source_url": None, "retrieved_at": None}
