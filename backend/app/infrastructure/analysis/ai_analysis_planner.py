import json
import re
from typing import Any

from app.infrastructure.llm.agent_skills import AgentSkill
from app.infrastructure.llm.llm_client import LLMMessage, OpenAICompatibleClient

SUPPORTED_CHART_TYPES = {
    "area",
    "bar",
    "boxplot",
    "bullet",
    "heatmap",
    "histogram",
    "line",
    "pie",
    "scatter",
    "treemap",
}


class AIAnalysisPlanner:
    def __init__(self) -> None:
        self.llm_client = OpenAICompatibleClient()

    async def plan(self, profile: dict[str, Any]) -> dict[str, Any]:
        try:
            content = await self.llm_client.chat(self._messages(profile))
            plan = self._parse_json(content)
            return self._normalize_plan(plan, profile, source="llm")
        except Exception as exc:
            fallback = self._fallback_plan(profile)
            fallback["source"] = "fallback"
            fallback["error"] = str(exc)
            return fallback

    def _messages(self, profile: dict[str, Any]) -> list[LLMMessage]:
        compact_profile = {
            "row_count": profile["row_count"],
            "column_count": profile["column_count"],
            "quality_issues": profile["quality_issues"],
            "columns": [
                {
                    "name": column["name"],
                    "data_type": column["data_type"],
                    "null_count": column["null_count"],
                    "unique_count": column["unique_count"],
                    "sample_values": column["sample_values"][:3],
                    "is_numeric": column["is_numeric"],
                    "is_datetime": column["is_datetime"],
                    "is_probable_index": column["is_probable_index"],
                }
                for column in profile["columns"]
            ],
        }
        schema = {
            "cleaning_suggestions": [
                {
                    "title": "string",
                    "rationale": "string",
                    "operation": "string",
                    "column": "string|null",
                }
            ],
            "feature_suggestions": [
                {"title": "string", "rationale": "string", "formula": "string"}
            ],
            "insights": [{"title": "string", "detail": "string", "evidence": "string"}],
            "chart_plan": [
                {
                    "chart_type": (
                        "histogram|bar|pie|scatter|line|area|heatmap|treemap|"
                        "bullet|boxplot"
                    ),
                    "title": "string",
                    "x": "column name",
                    "y": "column name|null",
                    "z": "column name|null",
                    "aggregation": "none|count|sum|avg|median",
                    "layout": "compact|standard|wide|tall|hero",
                    "rationale": "string",
                }
            ],
        }
        skill = AgentSkill(
            name="VisualizationPlanner",
            mission=(
                "Choose reliable, varied BI charts from a dataset profile and its "
                "computable derived fields."
            ),
            rules=[
                "Return only valid JSON matching the requested schema.",
                "Do not invent columns; use only columns present in the profile.",
                "Never use identifiers such as order numbers, document numbers, codes, "
                "SKUs, URLs, or names as numeric measures.",
                "Prefer useful variety: distributions, comparisons, relationships, "
                "time patterns, composition, and density.",
                "Use heatmap for two dimensions, treemap for categorical composition, "
                "bullet for KPI vs computed benchmark, and boxplot for numeric spread.",
                "For heatmap, use x and y as dimensions and z only when a numeric "
                "measure is required.",
                "Datetime columns are temporal dimensions, never plain categorical dimensions.",
                "For additive business measures such as sales, revenue, amount, energy, "
                "quantity, current value, or cumulative value, prefer sum over avg.",
                "Set layout based on reading needs: heatmap and long time series are "
                "wide/tall, KPI or small distribution charts are compact/standard.",
                "Do not force exotic charts; use heatmap, bullet, treemap, or boxplot "
                "only when they add clear value.",
                "Avoid identifier, URL, name/title, or free-text columns as chart "
                "dimensions unless no better option exists.",
                "Titles should use the dataset language when column names are non-English.",
                "Every chart must be explainable from the profile and executable by "
                "deterministic backend code.",
            ],
            output_contract=(
                "A single JSON object with cleaning_suggestions, feature_suggestions, "
                "insights, and chart_plan."
            ),
        )
        return [
            LLMMessage(
                role="system",
                content=skill.render(),
            ),
            LLMMessage(
                role="user",
                content=(
                    "Analyze this dataset profile. Produce cleaning suggestions, feature "
                    "engineering suggestions, insight summary, and a visualization plan. "
                    "The response must match this JSON shape exactly:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n\n"
                    "Dataset profile:\n"
                    f"{json.dumps(compact_profile, ensure_ascii=False)}"
                ),
            ),
        ]

    def _parse_json(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
            stripped = re.sub(r"```$", "", stripped).strip()

        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise ValueError("LLM response did not contain a JSON object")

        return json.loads(match.group(0))

    def _normalize_plan(
        self, plan: dict[str, Any], profile: dict[str, Any], source: str
    ) -> dict[str, Any]:
        valid_columns = {column["name"] for column in profile["columns"]}
        normalized_charts: list[dict[str, Any]] = []
        for chart in plan.get("chart_plan", []):
            chart_type = chart.get("chart_type")
            x_column = chart.get("x")
            y_column = chart.get("y")
            z_column = chart.get("z")
            if chart_type not in SUPPORTED_CHART_TYPES or x_column not in valid_columns:
                continue
            if y_column and y_column not in valid_columns:
                y_column = None
            if z_column and z_column not in valid_columns:
                z_column = None
            if not self._is_semantically_valid_chart(
                chart_type, x_column, y_column, z_column, chart.get("aggregation")
            ):
                continue
            normalized_charts.append(
                {
                    "chart_type": chart_type,
                    "title": str(chart.get("title") or f"{x_column} {chart_type}"),
                    "x": x_column,
                    "y": y_column,
                    "z": z_column,
                    "aggregation": chart.get("aggregation") or "none",
                    "layout": self._normalize_layout(chart.get("layout"), chart_type),
                    "rationale": str(chart.get("rationale") or ""),
                }
            )

        if not normalized_charts:
            normalized_charts = self._fallback_plan(profile)["chart_plan"]

        return {
            "source": source,
            "cleaning_suggestions": self._list_of_dicts(plan.get("cleaning_suggestions")),
            "feature_suggestions": self._list_of_dicts(plan.get("feature_suggestions")),
            "insights": self._list_of_dicts(plan.get("insights")),
            "chart_plan": self._dedupe_charts(normalized_charts)[:10],
        }

    def _fallback_plan(self, profile: dict[str, Any]) -> dict[str, Any]:
        row_count = max(int(profile.get("row_count") or 0), 1)
        numeric_columns = self._rank_columns(
            [
                column
                for column in profile["columns"]
                if column["is_numeric"]
                and not column["is_probable_index"]
                and (
                    not self._is_temporal_column(column["name"])
                    or self._looks_duration_metric(column["name"])
                )
                and not self._looks_identifier_or_free_text(column["name"])
            ]
        )
        temporal_columns = self._rank_columns(
            [
                column
                for column in profile["columns"]
                if not column["is_probable_index"]
                and (column.get("is_datetime") or self._is_temporal_column(column["name"]))
                and not self._looks_duration_metric(column["name"])
            ]
        )
        category_columns = self._rank_columns(
            [
                column
                for column in profile["columns"]
                if self._is_usable_category_column(column, row_count)
            ]
        )
        charts: list[dict[str, Any]] = []

        for numeric_column in numeric_columns[:2]:
            self._append_chart(
                charts,
                "histogram",
                f"{numeric_column['name']} Distribution",
                numeric_column["name"],
                layout="standard",
                rationale="Show the distribution of a key numeric field.",
            )

        if numeric_columns and self._has_high_variation(numeric_columns[0]):
            self._append_chart(
                charts,
                "boxplot",
                f"{numeric_columns[0]['name']} Spread",
                numeric_columns[0]["name"],
                aggregation="median",
                layout="compact",
                rationale="Summarize median, quartiles, and outliers for a key measure.",
            )

        if numeric_columns and self._looks_kpi_column(numeric_columns[0]["name"]):
            self._append_chart(
                charts,
                "bullet",
                f"{numeric_columns[0]['name']} KPI Benchmark",
                numeric_columns[0]["name"],
                aggregation="avg",
                layout="compact",
                rationale="Compare the average KPI against a computed upper-quartile benchmark.",
            )

        if category_columns and not numeric_columns:
            self._append_chart(
                charts,
                "bar",
                f"{category_columns[0]['name']} Top Categories",
                category_columns[0]["name"],
                aggregation="count",
                layout="standard",
                rationale="Show the most common categories without overloading the chart.",
            )
        if category_columns and category_columns[0]["unique_count"] >= 8:
            self._append_chart(
                charts,
                "treemap",
                f"{category_columns[0]['name']} Composition",
                category_columns[0]["name"],
                aggregation="count",
                layout="standard",
                rationale="Show category composition and relative size.",
            )

        if category_columns and not numeric_columns and category_columns[0]["unique_count"] <= 12:
            self._append_chart(
                charts,
                "pie",
                f"{category_columns[0]['name']} Share",
                category_columns[0]["name"],
                aggregation="count",
                layout="compact",
                rationale="Show a compact category share when category count is small.",
            )

        if numeric_columns and category_columns:
            category_aggregation = self._preferred_aggregation(numeric_columns[0]["name"])
            category_title = (
                f"{self._aggregation_title(category_aggregation)} "
                f"{numeric_columns[0]['name']} by {category_columns[0]['name']}"
            )
            self._append_chart(
                charts,
                "bar",
                category_title,
                category_columns[0]["name"],
                y=numeric_columns[0]["name"],
                aggregation=category_aggregation,
                layout="wide",
                rationale="Compare a key numeric field across categories.",
            )
        if (
            numeric_columns
            and category_columns
            and self._looks_kpi_column(numeric_columns[0]["name"])
        ):
            self._append_chart(
                charts,
                "bullet",
                f"{numeric_columns[0]['name']} by {category_columns[0]['name']}",
                category_columns[0]["name"],
                y=numeric_columns[0]["name"],
                aggregation="avg",
                layout="wide",
                rationale="Compare each leading category against the overall average benchmark.",
            )

        if numeric_columns and temporal_columns:
            time_aggregation = self._preferred_aggregation(numeric_columns[0]["name"])
            time_title = (
                f"{self._aggregation_title(time_aggregation)} "
                f"{numeric_columns[0]['name']} by {temporal_columns[0]['name']}"
            )
            self._append_chart(
                charts,
                "line",
                time_title,
                temporal_columns[0]["name"],
                y=numeric_columns[0]["name"],
                aggregation=time_aggregation,
                layout="hero",
                rationale="Show how the key numeric field changes over time.",
            )
        if (
            numeric_columns
            and temporal_columns
            and self._looks_additive_column(numeric_columns[0]["name"])
        ):
            self._append_chart(
                charts,
                "area",
                f"Total {numeric_columns[0]['name']} by {temporal_columns[0]['name']}",
                temporal_columns[0]["name"],
                y=numeric_columns[0]["name"],
                aggregation="sum",
                layout="wide",
                rationale="Show cumulative magnitude across the time dimension.",
            )

        if len(numeric_columns) >= 2:
            self._append_chart(
                charts,
                "scatter",
                f"{numeric_columns[0]['name']} vs {numeric_columns[1]['name']}",
                numeric_columns[0]["name"],
                y=numeric_columns[1]["name"],
                layout="standard",
                rationale="Check whether two numeric fields are related.",
            )

        if (
            numeric_columns
            and category_columns
            and temporal_columns
            and category_columns[0]["unique_count"] <= 60
        ):
            heatmap_aggregation = self._preferred_aggregation(numeric_columns[0]["name"])
            heatmap_title = (
                f"{self._aggregation_title(heatmap_aggregation)} "
                f"{numeric_columns[0]['name']} by {category_columns[0]['name']} "
                f"and {temporal_columns[0]['name']}"
            )
            self._append_chart(
                charts,
                "heatmap",
                heatmap_title,
                temporal_columns[0]["name"],
                y=category_columns[0]["name"],
                z=numeric_columns[0]["name"],
                aggregation=heatmap_aggregation,
                layout="wide",
                rationale="Reveal measure concentration patterns across category and time.",
            )

        if (
            len(category_columns) >= 2
            and category_columns[0]["unique_count"] <= 30
            and category_columns[1]["unique_count"] <= 30
        ):
            if numeric_columns:
                category_heatmap_aggregation = self._preferred_aggregation(
                    numeric_columns[0]["name"]
                )
                category_heatmap_title = (
                    f"{self._aggregation_title(category_heatmap_aggregation)} "
                    f"{numeric_columns[0]['name']} by {category_columns[0]['name']} "
                    f"and {category_columns[1]['name']}"
                )
                self._append_chart(
                    charts,
                    "heatmap",
                    category_heatmap_title,
                    category_columns[0]["name"],
                    y=category_columns[1]["name"],
                    z=numeric_columns[0]["name"],
                    aggregation=category_heatmap_aggregation,
                    layout="tall",
                    rationale=(
                        "Reveal measure concentration patterns across two categorical "
                        "dimensions."
                    ),
                )
            else:
                self._append_chart(
                    charts,
                    "heatmap",
                    f"{category_columns[0]['name']} by {category_columns[1]['name']}",
                    category_columns[0]["name"],
                    y=category_columns[1]["name"],
                    aggregation="count",
                    layout="tall",
                    rationale="Reveal co-occurrence density between two categorical dimensions.",
                )
        if len(category_columns) >= 2 and not numeric_columns:
            self._append_chart(
                charts,
                "bar",
                f"{category_columns[1]['name']} Top Categories",
                category_columns[1]["name"],
                aggregation="count",
                layout="standard",
                rationale="Show another useful categorical breakdown.",
            )
        if len(category_columns) >= 2 and numeric_columns:
            second_category_aggregation = self._preferred_aggregation(numeric_columns[0]["name"])
            second_category_title = (
                f"{self._aggregation_title(second_category_aggregation)} "
                f"{numeric_columns[0]['name']} by {category_columns[1]['name']}"
            )
            self._append_chart(
                charts,
                "bar",
                second_category_title,
                category_columns[1]["name"],
                y=numeric_columns[0]["name"],
                aggregation=second_category_aggregation,
                layout="standard",
                rationale="Compare the key numeric field across a second useful dimension.",
            )

        if numeric_columns and not category_columns and not temporal_columns:
            self._append_chart(
                charts,
                "bar",
                f"{numeric_columns[0]['name']} Value Bands",
                numeric_columns[0]["name"],
                aggregation="count",
                layout="standard",
                rationale="Bucket a standalone numeric measure into readable bands.",
            )

        charts = self._select_dashboard_charts(self._dedupe_charts(charts), max_charts=6)
        return {
            "source": "fallback",
            "cleaning_suggestions": [
                {
                    "title": "Remove exported index columns",
                    "rationale": (
                        "Index-like columns add noise and should not be used as "
                        "business dimensions."
                    ),
                    "operation": "drop_probable_index_columns",
                    "column": "Unnamed: 0",
                }
            ],
            "feature_suggestions": [
                {
                    "title": "Create computed benchmark features",
                    "rationale": (
                        "Percentiles, ranks, time buckets, and ratios can make "
                        "dashboards more useful without inventing data."
                    ),
                    "formula": "derive benchmarks from existing numeric and temporal columns",
                }
            ],
            "insights": [
                {
                    "title": "Initial automated profile completed",
                    "detail": (
                        f"Dataset has {profile['row_count']} rows and "
                        f"{profile['column_count']} columns."
                    ),
                    "evidence": "Generated from deterministic profile statistics.",
                }
            ],
            "chart_plan": charts,
        }

    def _rank_columns(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            columns, key=lambda column: self._column_score(str(column["name"])), reverse=True
        )

    def _column_score(self, column_name: str) -> int:
        lowered = column_name.lower()
        score = 0
        for token in [
            "数值",
            "amount",
            "revenue",
            "sales",
            "price",
            "score",
            "rating",
            "票房",
            "收入",
            "金额",
            "评分",
        ]:
            if token in lowered:
                score += 3
        for token in ["年份", "date", "time", "日期", "时间"]:
            if token in lowered:
                score += 2
        for token in ["天数", "days", "duration", "delay", "lead_time", "偏差"]:
            if token in lowered:
                score += 4
        for token in ["id", "url", "link", "链接"]:
            if token in lowered:
                score -= 5
        return score

    def _append_chart(
        self,
        charts: list[dict[str, Any]],
        chart_type: str,
        title: str,
        x: str,
        y: str | None = None,
        z: str | None = None,
        aggregation: str = "none",
        layout: str | None = None,
        rationale: str = "",
    ) -> None:
        charts.append(
            {
                "chart_type": chart_type,
                "title": title,
                "x": x,
                "y": y,
                "z": z,
                "aggregation": aggregation,
                "layout": self._normalize_layout(layout, chart_type),
                "rationale": rationale,
            }
        )

    def _dedupe_charts(self, charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        result: list[dict[str, Any]] = []
        for chart in charts:
            key = (
                chart.get("chart_type"),
                chart.get("x"),
                chart.get("y"),
                chart.get("z"),
                chart.get("aggregation"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(chart)
        return result

    def _select_dashboard_charts(
        self, charts: list[dict[str, Any]], max_charts: int
    ) -> list[dict[str, Any]]:
        priority = {
            "line": 100,
            "bar": 90,
            "heatmap": 88,
            "histogram": 76,
            "scatter": 74,
            "area": 70,
            "treemap": 68,
            "boxplot": 62,
            "pie": 55,
            "bullet": 50,
        }
        selected: list[dict[str, Any]] = []
        type_counts: dict[str, int] = {}
        semantic_keys: set[tuple[Any, ...]] = set()
        for chart in sorted(
            charts, key=lambda item: priority.get(str(item.get("chart_type")), 0), reverse=True
        ):
            chart_type = str(chart.get("chart_type"))
            max_per_type = 1 if chart_type in {"histogram", "area"} else 2
            if type_counts.get(chart_type, 0) >= max_per_type:
                continue
            semantic_key = self._semantic_chart_key(chart)
            if semantic_key in semantic_keys:
                continue
            selected.append(chart)
            type_counts[chart_type] = type_counts.get(chart_type, 0) + 1
            semantic_keys.add(semantic_key)
            if len(selected) >= max_charts:
                return selected
        return selected

    def _semantic_chart_key(self, chart: dict[str, Any]) -> tuple[Any, ...]:
        chart_type = chart.get("chart_type")
        chart_family = "trend" if chart_type in {"line", "area"} else chart_type
        return (
            chart_family,
            chart.get("x"),
            chart.get("y"),
            chart.get("z"),
            chart.get("aggregation"),
        )

    def _normalize_layout(self, layout: Any, chart_type: Any) -> str:
        if layout in {"compact", "standard", "wide", "tall", "hero"}:
            return str(layout)
        defaults = {
            "area": "wide",
            "bar": "standard",
            "boxplot": "compact",
            "bullet": "compact",
            "heatmap": "wide",
            "histogram": "standard",
            "line": "hero",
            "pie": "compact",
            "scatter": "standard",
            "treemap": "standard",
        }
        return defaults.get(str(chart_type), "standard")

    def _has_high_variation(self, column: dict[str, Any]) -> bool:
        return int(column.get("unique_count") or 0) >= 20

    def _looks_kpi_column(self, column_name: str) -> bool:
        lowered = str(column_name).lower()
        return any(
            token in lowered for token in ["kpi", "score", "rating", "rate", "评分", "指数", "率"]
        )

    def _looks_additive_column(self, column_name: str) -> bool:
        lowered = str(column_name).lower()
        return any(
            token in lowered
            for token in [
                "amount",
                "revenue",
                "sales",
                "count",
                "energy",
                "quantity",
                "volume",
                "price",
                "票房",
                "收入",
                "金额",
                "数量",
                "电量",
                "当期值",
                "累计值",
                "计划值",
                "同期值",
                "数值",
            ]
        )

    def _looks_duration_metric(self, column_name: str) -> bool:
        lowered = str(column_name).lower()
        return any(
            token in lowered for token in ["天数", "days", "duration", "delay", "lead_time", "偏差"]
        )

    def _preferred_aggregation(self, column_name: str) -> str:
        return "sum" if self._looks_additive_column(column_name) else "avg"

    def _aggregation_title(self, aggregation: str) -> str:
        return "Total" if aggregation == "sum" else "Average"

    def _is_usable_category_column(self, column: dict[str, Any], row_count: int) -> bool:
        if (
            column["is_numeric"]
            or column["is_probable_index"]
            or column.get("is_datetime")
            or self._is_temporal_column(column["name"])
        ):
            return False
        unique_count = int(column.get("unique_count") or 0)
        if unique_count <= 1 or unique_count > 100:
            return False
        if unique_count >= row_count * 0.7:
            return False
        return not self._looks_identifier_or_free_text(column["name"])

    def _is_temporal_column(self, column_name: str) -> bool:
        lowered = column_name.lower()
        return any(token in lowered for token in ["date", "time", "year", "日期", "时间", "年份"])

    def _looks_identifier_or_free_text(self, column_name: str) -> bool:
        lowered = column_name.lower()
        blocked_tokens = [
            "id",
            "url",
            "link",
            "链接",
            "网址",
            "编号",
            "单号",
            "订单号",
            "采购订单",
            "订单编号",
            "单据",
            "凭证",
            "流水号",
            "编码",
            "代码",
            "sku",
            "serial",
            "barcode",
            "code",
            "名称",
            "名字",
            "姓名",
            "电影名",
            "标题",
            "title",
            "name",
        ]
        return any(token in lowered for token in blocked_tokens)

    def _is_semantically_valid_chart(
        self,
        chart_type: Any,
        x_column: Any,
        y_column: Any,
        z_column: Any,
        aggregation: Any,
    ) -> bool:
        x_name = str(x_column or "")
        y_name = str(y_column or "")
        z_name = str(z_column or "")
        if chart_type in {
            "histogram",
            "boxplot",
            "bullet",
            "scatter",
        } and self._looks_identifier_or_free_text(x_name):
            return False
        if y_name and aggregation != "count" and self._looks_identifier_or_free_text(y_name):
            return False
        if z_name and aggregation != "count" and self._looks_identifier_or_free_text(z_name):
            return False
        return True

    def _list_of_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]
