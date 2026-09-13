from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedIngredient:
    text: str
    parent_context: str | None = None


class IngredientParser:
    """Split a label into both primary ingredients and nested constituents.

    Parentheses and brackets commonly contain allergen-relevant sub-ingredients
    (for example, milk chocolate ingredients or ``lecithins [soya]``). Flattening
    those groups makes each declared constituent available to the normalizer.
    """

    def parse(self, raw_text: str) -> list[str]:
        return [item.text for item in self.parse_with_context(raw_text)]

    def parse_with_context(self, raw_text: str) -> list[ParsedIngredient]:
        cleaned = re.sub(r"\bingredients?\s*:\s*", "", raw_text, flags=re.IGNORECASE).strip()
        if not cleaned:
            return []
        # Keep the same conservative flattened matching behaviour while also
        # recording which declared compound a nested constituent came from.
        # This is provenance for display; it never changes normalization or
        # scoring.
        tokens: list[ParsedIngredient] = []
        stack: list[str | None] = []
        buffer = ""

        def flush() -> str | None:
            nonlocal buffer
            value = self._clean_token(buffer)
            buffer = ""
            if value:
                tokens.append(ParsedIngredient(value, stack[-1] if stack else None))
            return value

        for character in cleaned:
            if character in "([{":
                parent = flush()
                stack.append(parent or (stack[-1] if stack else None))
            elif character in ")]}":
                flush()
                if stack:
                    stack.pop()
            elif character in ",;\n":
                flush()
            else:
                buffer += character
        flush()
        return tokens

    @staticmethod
    def _append_token(tokens: list[str], candidate: str) -> None:
        token = IngredientParser._clean_token(candidate)
        if token:
            tokens.append(token)

    @staticmethod
    def _clean_token(candidate: str) -> str:
        return re.sub(r"\s+", " ", candidate).strip(" .:-\t")
