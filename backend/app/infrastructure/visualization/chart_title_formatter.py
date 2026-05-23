import re
from typing import Any


class ChartTitleFormatter:
    def decorate_card(self, card: dict[str, Any]) -> dict[str, Any]:
        if card.get("type") != "chart":
            return card

        decorated = dict(card)
        decorated["title"] = self.title_for_chart(card)
        return decorated

    def title_for_chart(self, chart: dict[str, Any]) -> str:
        chart_type = str(chart.get("chart_type") or "")
        encoding = chart.get("encoding") if isinstance(chart.get("encoding"), dict) else chart
        x_column = str(encoding.get("x") or "")
        y_column = str(encoding.get("y") or "")
        z_column = str(encoding.get("z") or "")
        aggregation = str(encoding.get("aggregation") or "")

        if chart_type in {"line", "area"}:
            measure = self._field_label(y_column) if y_column else "记录数"
            return f"{self._time_prefix(x_column)}{measure}"

        if chart_type == "bar":
            dimension = self._field_label(x_column)
            if aggregation == "count" or not y_column:
                return f"{dimension}分布"
            aggregation_prefix = self._aggregation_prefix(aggregation)
            return f"各{dimension}{aggregation_prefix}{self._field_label(y_column)}"

        if chart_type == "heatmap":
            x_label = self._heatmap_axis_label(x_column)
            y_label = self._field_label(y_column)
            if z_column:
                return f"{y_label}×{x_label}{self._field_label(z_column)}热力图"
            return f"{y_label}×{x_label}分布热力图"

        if chart_type == "histogram":
            return f"{self._field_label(x_column)}分布"

        if chart_type == "boxplot":
            return f"{self._field_label(x_column)}离散度"

        if chart_type == "bullet":
            measure = self._field_label(y_column or x_column)
            return f"{measure}基准对比"

        if chart_type == "scatter" and y_column:
            return f"{self._field_label(x_column)}与{self._field_label(y_column)}关系"

        if chart_type == "pie":
            return f"{self._field_label(x_column)}占比"

        if chart_type == "treemap":
            return f"{self._field_label(x_column)}构成"

        return self._fallback_title(chart)

    def _fallback_title(self, chart: dict[str, Any]) -> str:
        title = str(chart.get("title") or chart.get("chart_type") or "图表")
        return self._field_label(title)

    def _field_label(self, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return "指标"

        parts = [part for part in re.split(r"[_\s\-]+", cleaned) if part]
        technical_suffixes = {"value", "values", "numeric", "number", "num", "数值"}
        while len(parts) > 1 and parts[-1].lower() in technical_suffixes:
            parts.pop()

        if any(self._contains_cjk(part) for part in parts):
            return "".join(parts)
        return " ".join(part.capitalize() for part in parts)

    def _time_prefix(self, column_name: str) -> str:
        lowered = column_name.lower()
        if any(token in lowered for token in ["月份", "年月", "month"]):
            return "每月"
        if any(token in lowered for token in ["周", "week"]):
            return "每周"
        if any(token in lowered for token in ["季度", "quarter"]):
            return "每季度"
        if any(token in lowered for token in ["年份", "年度", "year"]):
            return "年度"
        if any(token in lowered for token in ["日期", "时间", "date", "time", "day"]):
            return "每日"
        if any(token in lowered for token in ["期间", "周期", "period"]):
            return "各期"
        return f"按{self._field_label(column_name)}"

    def _heatmap_axis_label(self, column_name: str) -> str:
        prefix = self._time_prefix(column_name)
        if prefix.startswith("按"):
            return self._field_label(column_name)
        return prefix

    def _aggregation_prefix(self, aggregation: str) -> str:
        if aggregation == "avg":
            return "平均"
        if aggregation == "median":
            return "中位数"
        return ""

    def _contains_cjk(self, value: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in value)
