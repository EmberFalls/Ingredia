from app.services.parser import IngredientParser


def test_parser_exposes_parenthetical_constituents() -> None:
    assert IngredientParser().parse("Ingredients: Aqua (Water), Parfum/Fragrance; CI 19140") == ["Aqua", "Water", "Parfum/Fragrance", "CI 19140"]


def test_parser_handles_newlines_and_empty_values() -> None:
    assert IngredientParser().parse("Water,\n\n Glycerin; ") == ["Water", "Glycerin"]
