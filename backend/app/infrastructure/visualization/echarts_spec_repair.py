import ast
import json
import re
from typing import Any


class EChartsSpecRepairer:
    """Defensively converts LLM output into a safe ECharts option object."""

    def repair_or_fallback(
        self,
        raw_spec: Any,
        data: list[dict[str, Any]] | None = None,
        title: str = "Top 10",
    ) -> dict[str, Any]:
        if isinstance(raw_spec, dict):
            return self._sanitize_option(raw_spec, data, title)

        if isinstance(raw_spec, str) and raw_spec.strip():
            for candidate in self._candidate_json_strings(raw_spec):
                parsed = self._parse_candidate(candidate)
                if isinstance(parsed, dict):
                    return self._sanitize_option(parsed, data, title)

        return self.fallback_bar_option(data or [], title)

    def parse_json_like(self, content: str) -> Any:
        """Parses messy LLM JSON without applying ECharts-specific validation."""
        for candidate in self._candidate_json_strings(content):
            parsed = self._parse_candidate(candidate)
            if parsed is not None:
                return parsed
        raise ValueError("LLM response did not contain repairable JSON")

    def fallback_bar_option(self, data: list[dict[str, Any]], title: str) -> dict[str, Any]:
        rows = sorted(
            [
                {
                    "label": str(item.get("label") or item.get("name") or ""),
                    "value": item.get("value"),
                }
                for item in data
            ],
            key=lambda item: float(item["value"] or 0),
            reverse=True,
        )[:10]
        return {
            "title": {"text": title, "left": "center", "textStyle": {"fontSize": 13}},
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 10, "right": 16, "top": 40, "bottom": 42, "containLabel": True},
            "xAxis": {"type": "category", "data": [item["label"] for item in rows]},
            "yAxis": {"type": "value"},
            "series": [
                {
                    "type": "bar",
                    "data": [float(item["value"] or 0) for item in rows],
                    "barMaxWidth": 34,
                }
            ],
        }

    def _candidate_json_strings(self, content: str) -> list[str]:
        stripped = self._strip_markdown_fence(content)
        candidates: list[str] = []
        balanced = self._extract_balanced_json(stripped)
        if balanced:
            candidates.append(balanced)
        candidates.append(stripped)
        return list(dict.fromkeys(candidates))

    def _parse_candidate(self, candidate: str) -> Any:
        repaired = self._repair_syntax(candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            # ast.literal_eval accepts Python-like single quotes/True/False/None safely.
            try:
                return ast.literal_eval(repaired)
            except (SyntaxError, ValueError):
                return None

    def _repair_syntax(self, content: str) -> str:
        repaired = content.strip()
        repaired = re.sub(r"//.*?$|/\*.*?\*/", "", repaired, flags=re.MULTILINE | re.DOTALL)
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        repaired = re.sub(r"\bTrue\b", "true", repaired)
        repaired = re.sub(r"\bFalse\b", "false", repaired)
        repaired = re.sub(r"\bNone\b", "null", repaired)
        # Quote simple unquoted keys: {xAxis: ...} -> {"xAxis": ...}
        return re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', repaired)

    def _strip_markdown_fence(self, content: str) -> str:
        stripped = content.strip()
        if not stripped.startswith("```"):
            return stripped
        stripped = re.sub(r"^```(?:json|javascript|js)?", "", stripped, flags=re.IGNORECASE)
        return re.sub(r"```$", "", stripped.strip()).strip()

    def _extract_balanced_json(self, content: str) -> str:
        start = min(
            [index for index in [content.find("{"), content.find("[")] if index >= 0],
            default=-1,
        )
        if start < 0:
            return ""

        stack: list[str] = []
        pairs = {"{": "}", "[": "]"}
        in_string = False
        quote = ""
        escaped = False
        for index, char in enumerate(content[start:], start=start):
            if in_string:
                escaped = char == "\\" and not escaped
                if char == quote and not escaped:
                    in_string = False
                elif char != "\\":
                    escaped = False
                continue
            if char in {"'", '"'}:
                in_string = True
                quote = char
                continue
            if char in pairs:
                stack.append(pairs[char])
                continue
            if stack and char == stack[-1]:
                stack.pop()
                if not stack:
                    return content[start : index + 1]
        return ""

    def _sanitize_option(
        self,
        option: dict[str, Any],
        data: list[dict[str, Any]] | None,
        title: str,
    ) -> dict[str, Any]:
        series = option.get("series")
        if not isinstance(series, list) or not series:
            return self.fallback_bar_option(data or [], title)

        sanitized = dict(option)
        sanitized.setdefault("tooltip", {"trigger": "axis"})
        sanitized.setdefault(
            "grid",
            {"left": 10, "right": 16, "top": 32, "bottom": 42, "containLabel": True},
        )
        return sanitized
