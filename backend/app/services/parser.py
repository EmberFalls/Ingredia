from __future__ import annotations

import re


class IngredientParser:
    """Split label text while preserving parentheses that are part of one ingredient."""

    def parse(self, raw_text: str) -> list[str]:
        cleaned = re.sub(r"\bingredients?\s*:\s*", "", raw_text, flags=re.IGNORECASE).strip()
        if not cleaned:
            return []
        tokens: list[str] = []
        buffer: list[str] = []
        depth = 0
        for char in cleaned:
            if char in "([":
                depth += 1
            elif char in ")]" and depth:
                depth -= 1
            if char in ",;\n" and depth == 0:
                self._append_token(tokens, "".join(buffer))
                buffer = []
            else:
                buffer.append(char)
        self._append_token(tokens, "".join(buffer))
        return tokens

    @staticmethod
    def _append_token(tokens: list[str], candidate: str) -> None:
        token = re.sub(r"\s+", " ", candidate).strip(" .:-\t")
        if token:
            tokens.append(token)
