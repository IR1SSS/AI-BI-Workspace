import re
from typing import Any


class MicroSemanticLayerBuilder:
    """Builds the small semantic contract that is safe to send to agents."""

    def build(self, columns: list[dict[str, Any]]) -> dict[str, Any]:
        dimensions: list[dict[str, Any]] = []
        measures: list[dict[str, Any]] = []
        aliases: dict[str, str] = {}

        for column in columns:
            name = str(column["name"])
            alias = self._logical_alias(name)
            aliases[alias] = name

            if self._is_measure(column):
                measures.append(
                    {
                        "name": name,
                        "alias": alias,
                        "data_type": column["data_type"],
                        "default_aggregation": self._default_aggregation(name),
                    }
                )
                continue

            if self._is_dimension(column):
                dimensions.append(
                    {
                        "name": name,
                        "alias": alias,
                        "data_type": column["data_type"],
                        "role": "time" if column.get("is_datetime") else "category",
                    }
                )

        return {
            "logical_aliases": aliases,
            "dimensions": dimensions[:15],
            "measures": measures[:15],
            "aggregation_defaults": {
                measure["name"]: measure["default_aggregation"] for measure in measures[:15]
            },
        }

    def compact_columns(
        self,
        columns: list[dict[str, Any]],
        hard_column_limit: int = 20,
        selected_limit: int = 15,
    ) -> dict[str, Any]:
        """Keeps high-signal columns in prompt context and lists the rest by name only."""
        if len(columns) <= hard_column_limit:
            return {"analysis_columns": columns, "auxiliary_columns": []}

        ranked = sorted(columns, key=self._analysis_value_score, reverse=True)
        selected = ranked[:selected_limit]
        selected_names = {column["name"] for column in selected}
        auxiliary = [
            str(column["name"]) for column in columns if column["name"] not in selected_names
        ]
        return {"analysis_columns": selected, "auxiliary_columns": auxiliary}

    def _analysis_value_score(self, column: dict[str, Any]) -> float:
        non_null_ratio = 1 - float(column.get("null_ratio") or 0)
        cardinality_ratio = float(column.get("cardinality_ratio") or 0)
        unique_count = int(column.get("unique_count") or 0)
        score = non_null_ratio * 60

        # Useful analytical dimensions are neither constant nor row-level unique IDs.
        if column.get("is_numeric"):
            score += 18
        elif 2 <= unique_count <= 100:
            score += 22

        if column.get("is_datetime"):
            score += 16
        if column.get("is_constant"):
            score -= 40
        if column.get("is_probable_index") or column.get("is_probable_identifier"):
            score -= 35
        if cardinality_ratio > 0.9 and not column.get("is_numeric"):
            score -= 20
        return score

    def _is_measure(self, column: dict[str, Any]) -> bool:
        return bool(column.get("is_numeric")) and not bool(column.get("is_probable_identifier"))

    def _is_dimension(self, column: dict[str, Any]) -> bool:
        if column.get("is_probable_index") or column.get("is_constant"):
            return False
        if column.get("is_probable_identifier") and not column.get("is_datetime"):
            return False
        return not bool(column.get("is_numeric"))

    def _logical_alias(self, column_name: str) -> str:
        alias = re.sub(r"[^0-9a-zA-Z]+", "_", column_name.strip().lower()).strip("_")
        return alias or "column"

    def _default_aggregation(self, column_name: str) -> str:
        lowered = column_name.lower()
        additive_tokens = [
            "amount",
            "revenue",
            "sales",
            "quantity",
            "volume",
            "count",
            "total",
            "sum",
        ]
        return "sum" if any(token in lowered for token in additive_tokens) else "avg"
