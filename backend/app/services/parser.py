from __future__ import annotations

import re


class IngredientParser:
    """Split a label into both primary ingredients and nested constituents.

    Parentheses and brackets commonly contain allergen-relevant sub-ingredients
    (for example, milk chocolate ingredients or ``lecithins [soya]``). Flattening
    those groups makes each declared constituent available to the normalizer.
    """

    def parse(self, raw_text: str) -> list[str]:
        cleaned = re.sub(r"\bingredients?\s*:\s*", "", raw_text, flags=re.IGNORECASE).strip()
        if not cleaned:
            return []
        # Group boundaries become delimiters so nested declarations are not
        # hidden inside one otherwise-unresolvable compound token.
        flattened = re.sub(r"[()\[\]{}]", ",", cleaned)
        tokens: list[str] = []
        for candidate in re.split(r"[,;\n]", flattened):
            self._append_token(tokens, candidate)
        return tokens

    @staticmethod
    def _append_token(tokens: list[str], candidate: str) -> None:
        token = re.sub(r"\s+", " ", candidate).strip(" .:-\t")
        if token:
            tokens.append(token)
