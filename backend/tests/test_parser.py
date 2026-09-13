from app.services.parser import IngredientParser


def test_parser_exposes_parenthetical_constituents() -> None:
    assert IngredientParser().parse("Ingredients: Aqua (Water), Parfum/Fragrance; CI 19140") == ["Aqua", "Water", "Parfum/Fragrance", "CI 19140"]


def test_parser_retains_parent_context_for_nested_constituents() -> None:
    parsed = IngredientParser().parse_with_context("Milk chocolate (sugar, cocoa mass, skimmed milk powder)")
    assert [(item.text, item.parent_context) for item in parsed] == [
        ("Milk chocolate", None),
        ("sugar", "Milk chocolate"),
        ("cocoa mass", "Milk chocolate"),
        ("skimmed milk powder", "Milk chocolate"),
    ]


def test_parser_handles_newlines_and_empty_values() -> None:
    assert IngredientParser().parse("Water,\n\n Glycerin; ") == ["Water", "Glycerin"]
