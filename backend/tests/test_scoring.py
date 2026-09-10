from app.services.scoring import ScoringService, score_band


class Evidence:
    def __init__(self, concern_type: str, severity: int, confidence: float, applicability: str = "general") -> None:
        self.concern_type = concern_type
        self.severity = severity
        self.confidence = confidence
        self.applicability = applicability
        self.is_active = True


def test_duplicate_concern_sources_do_not_inflate_ingredient_score() -> None:
    service = ScoringService()
    one = service.ingredient_score([Evidence("restriction", 3, 0.8)], "personal_care")
    two = service.ingredient_score([Evidence("restriction", 3, 0.8), Evidence("restriction", 2, 0.9)], "personal_care")
    assert one == two


def test_score_is_bounded_and_categorized() -> None:
    service = ScoringService()
    result = service.score_product([("Example", [Evidence("a", 10, 1), Evidence("b", 10, 1)])], None)
    assert result.score == 100
    assert score_band(result.score) == "elevated"
