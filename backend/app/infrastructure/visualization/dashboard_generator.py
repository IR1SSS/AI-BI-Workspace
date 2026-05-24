from typing import Any
from uuid import uuid4

import pandas as pd

from app.infrastructure.visualization.chart_title_formatter import ChartTitleFormatter
from app.infrastructure.visualization.echarts_spec_repair import EChartsSpecRepairer


class DashboardGenerator:
    def __init__(self) -> None:
        self.title_formatter = ChartTitleFormatter()
        self.spec_repairer = EChartsSpecRepairer()

    def generate(
        self,
        dataset_id: str,
        version_id: str,
        file_name: str,
        profile: dict[str, Any],
        dataframe: pd.DataFrame | None = None,
        analysis_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = analysis_plan or {}
        cards = self._metric_cards(profile)
        cards.extend(self._chart_cards(analysis.get("chart_plan", []), dataframe))

        return {
            "id": str(uuid4()),
            "title": f"{file_name} Dashboard Draft",
            "dataset_id": dataset_id,
            "version_id": version_id,
            "status": "draft",
            "analysis_source": analysis.get("source", "fallback"),
            "cards": cards,
            "layout": self._layout(len(cards)),
        }

    def _metric_cards(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"id": "row-count", "type": "metric", "title": "Rows", "value": profile["row_count"]},
            {
                "id": "column-count",
                "type": "metric",
                "title": "Columns",
                "value": profile["column_count"],
            },
            {
                "id": "quality-issues",
                "type": "metric",
                "title": "Quality Issues",
                "value": len(profile["quality_issues"]),
            },
        ]

    def _chart_cards(
        self,
        chart_plan: list[dict[str, Any]],
        dataframe: pd.DataFrame | None,
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for index, chart in enumerate(chart_plan[:10]):
            chart_type = chart["chart_type"]
            data = self._chart_data(chart, dataframe)
            if not data:
                continue
            title = self.title_formatter.title_for_chart(chart)
            sql = self.chart_sql(chart)
            raw_echarts_spec = chart.get("echarts_option") or chart.get("echarts_spec")
            card_payload = {
                "id": f"chart-{index + 1}",
                "type": "chart",
                "chart_type": chart_type,
                "title": title,
                "encoding": {
                    "x": chart.get("x"),
                    "y": chart.get("y"),
                    "z": chart.get("z"),
                    "aggregation": chart.get("aggregation"),
                },
                "layout": self._card_layout(chart, data),
                "sql": sql,
                "data": data,
            }
            if raw_echarts_spec:
                card_payload["echarts_option"] = self.spec_repairer.repair_or_fallback(
                    raw_echarts_spec,
                    data,
                    title,
                )
            cards.append(card_payload)
        return cards

    def chart_sql(self, chart: dict[str, Any]) -> str:
        chart_type = str(chart.get("chart_type") or "")
        x_column = chart.get("x")
        y_column = chart.get("y")
        z_column = chart.get("z")
        aggregation = str(chart.get("aggregation") or "none")
        if not x_column:
            return ""

        x = self._quote_identifier(str(x_column))
        y = self._quote_identifier(str(y_column)) if y_column else ""
        z = self._quote_identifier(str(z_column)) if z_column else ""

        if chart_type in {"bar", "pie", "treemap", "line", "area"}:
            if y and aggregation in {"sum", "avg", "median"}:
                agg_expr = {
                    "sum": f"SUM(TRY_CAST({y} AS DOUBLE))",
                    "avg": f"AVG(TRY_CAST({y} AS DOUBLE))",
                    "median": f"MEDIAN(TRY_CAST({y} AS DOUBLE))",
                }[aggregation]
                order_by = (
                    "ORDER BY value DESC"
                    if chart_type not in {"line", "area"}
                    else "ORDER BY label"
                )
                return (
                    f"SELECT CAST({x} AS VARCHAR) AS label, {agg_expr} AS value "
                    f"FROM dataset WHERE {x} IS NOT NULL AND {y} IS NOT NULL "
                    f"GROUP BY 1 {order_by} LIMIT 12"
                )
            return (
                f"SELECT CAST({x} AS VARCHAR) AS label, COUNT(*) AS value "
                f"FROM dataset WHERE {x} IS NOT NULL GROUP BY 1 ORDER BY value DESC LIMIT 12"
            )

        if chart_type == "scatter" and y:
            return (
                f"SELECT TRY_CAST({x} AS DOUBLE) AS x, TRY_CAST({y} AS DOUBLE) AS y "
                f"FROM dataset WHERE {x} IS NOT NULL AND {y} IS NOT NULL LIMIT 200"
            )

        if chart_type == "heatmap" and y:
            if z and aggregation in {"sum", "avg", "median"}:
                agg_expr = {
                    "sum": f"SUM(TRY_CAST({z} AS DOUBLE))",
                    "avg": f"AVG(TRY_CAST({z} AS DOUBLE))",
                    "median": f"MEDIAN(TRY_CAST({z} AS DOUBLE))",
                }[aggregation]
            else:
                agg_expr = "COUNT(*)"
            return (
                f"SELECT CAST({x} AS VARCHAR) AS xLabel, CAST({y} AS VARCHAR) AS yLabel, "
                f"{agg_expr} AS value FROM dataset "
                f"WHERE {x} IS NOT NULL AND {y} IS NOT NULL GROUP BY 1, 2 LIMIT 144"
            )

        if chart_type == "boxplot":
            return (
                f"SELECT MIN(TRY_CAST({x} AS DOUBLE)) AS min, "
                f"QUANTILE_CONT(TRY_CAST({x} AS DOUBLE), 0.25) AS q1, "
                f"MEDIAN(TRY_CAST({x} AS DOUBLE)) AS median, "
                f"QUANTILE_CONT(TRY_CAST({x} AS DOUBLE), 0.75) AS q3, "
                f"MAX(TRY_CAST({x} AS DOUBLE)) AS max FROM dataset WHERE {x} IS NOT NULL"
            )

        return f"SELECT {x} FROM dataset WHERE {x} IS NOT NULL LIMIT 10000"

    def _quote_identifier(self, column_name: str) -> str:
        return '"' + column_name.replace('"', '""') + '"'

    def _card_layout(self, chart: dict[str, Any], data: list[dict[str, Any]]) -> dict[str, str]:
        requested = chart.get("layout")
        chart_type = str(chart.get("chart_type") or "")
        if requested in {"compact", "standard", "wide", "tall", "hero"}:
            size = str(requested)
        else:
            size = {
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
            }.get(chart_type, "standard")

        if chart_type == "heatmap" and len(data) > 48:
            size = "tall"
        if chart_type in {"line", "area"} and len(data) >= 8:
            size = "hero"
        return {"size": size}

    def _chart_data(
        self,
        chart: dict[str, Any],
        dataframe: pd.DataFrame | None,
    ) -> list[dict[str, Any]]:
        if dataframe is None:
            return []

        chart_type = chart["chart_type"]
        x_column = chart.get("x")
        y_column = chart.get("y")
        aggregation = chart.get("aggregation") or "none"
        if not x_column or x_column not in dataframe.columns:
            return []

        if chart_type == "histogram":
            return self._histogram_data(dataframe, x_column)
        if chart_type == "boxplot":
            return self._boxplot_data(dataframe, x_column)
        if chart_type == "bullet":
            return self._bullet_data(dataframe, x_column, y_column, aggregation)
        if chart_type == "treemap":
            if y_column:
                return self._category_aggregate_data(dataframe, x_column, y_column, aggregation)
            return self._category_count_data(dataframe, x_column)
        if chart_type == "heatmap":
            if not y_column:
                return []
            return self._heatmap_data(dataframe, x_column, y_column, chart.get("z"), aggregation)
        if chart_type == "pie":
            return self._category_count_data(dataframe, x_column)
        if chart_type == "bar":
            if aggregation == "count" or not y_column:
                return self._category_count_data(dataframe, x_column)
            return self._category_aggregate_data(dataframe, x_column, y_column, aggregation)
        if chart_type in {"line", "area"}:
            if not y_column:
                return self._category_count_data(dataframe, x_column)
            return self._category_aggregate_data(
                dataframe,
                x_column,
                y_column,
                aggregation,
                sort_by_value=False,
            )
        if chart_type == "scatter" and y_column:
            return self._scatter_data(dataframe, x_column, y_column)
        return []

    def _histogram_data(self, dataframe: pd.DataFrame, column: str) -> list[dict[str, Any]]:
        series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
        if series.empty:
            return []

        bins = min(10, max(4, int(series.nunique() ** 0.5)))
        counts = pd.cut(series, bins=bins).value_counts().sort_index()
        return [
            {"label": f"{interval.left:.1f} - {interval.right:.1f}", "value": int(value)}
            for interval, value in counts.items()
        ]

    def _boxplot_data(self, dataframe: pd.DataFrame, column: str) -> list[dict[str, Any]]:
        series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
        if series.empty:
            return []

        quantiles = series.quantile([0, 0.25, 0.5, 0.75, 1]).tolist()
        return [
            {
                "label": column,
                "min": round(float(quantiles[0]), 2),
                "q1": round(float(quantiles[1]), 2),
                "median": round(float(quantiles[2]), 2),
                "q3": round(float(quantiles[3]), 2),
                "max": round(float(quantiles[4]), 2),
                "value": round(float(quantiles[2]), 2),
            }
        ]

    def _bullet_data(
        self,
        dataframe: pd.DataFrame,
        x_column: str,
        y_column: str | None,
        aggregation: str,
    ) -> list[dict[str, Any]]:
        if y_column and y_column in dataframe.columns:
            grouped = self._category_aggregate_data(
                dataframe,
                x_column,
                y_column,
                aggregation,
            )
            overall = pd.to_numeric(dataframe[y_column], errors="coerce").dropna()
            if overall.empty:
                return []
            target = round(float(overall.mean()), 2)
            return [{**item, "target": target} for item in grouped[:8]]

        series = pd.to_numeric(dataframe[x_column], errors="coerce").dropna()
        if series.empty:
            return []

        value = round(float(series.mean()), 2)
        target = round(float(series.quantile(0.75)), 2)
        marker = round(float(series.median()), 2)
        return [{"label": x_column, "value": value, "target": target, "marker": marker}]

    def _category_count_data(
        self,
        dataframe: pd.DataFrame,
        category_column: str,
    ) -> list[dict[str, Any]]:
        if pd.api.types.is_numeric_dtype(dataframe[category_column]):
            numeric = pd.to_numeric(dataframe[category_column], errors="coerce").dropna()
            if not numeric.empty and numeric.nunique() > 12:
                return self._histogram_data(dataframe, category_column)

        counts = dataframe[category_column].dropna().astype(str).value_counts().head(12)
        return [{"label": str(label), "value": int(value)} for label, value in counts.items()]

    def _heatmap_data(
        self,
        dataframe: pd.DataFrame,
        x_column: str,
        y_column: str,
        z_column: str | None,
        aggregation: str,
    ) -> list[dict[str, Any]]:
        if y_column not in dataframe.columns:
            return []

        working_columns = [x_column, y_column]
        if z_column and z_column in dataframe.columns:
            working_columns.append(z_column)

        working = dataframe[working_columns].dropna().copy()
        if working.empty:
            return []

        top_x = working[x_column].astype(str).value_counts().head(12).index
        top_y = working[y_column].astype(str).value_counts().head(12).index
        working["_x"] = working[x_column].astype(str)
        working["_y"] = working[y_column].astype(str)
        working = working[working["_x"].isin(top_x) & working["_y"].isin(top_y)]
        if working.empty:
            return []

        if z_column and z_column in working.columns and aggregation in {"avg", "sum", "median"}:
            working[z_column] = pd.to_numeric(working[z_column], errors="coerce")
            group = working.dropna().groupby(["_x", "_y"], dropna=True)[z_column]
            if aggregation == "sum":
                grouped = group.sum()
            elif aggregation == "median":
                grouped = group.median()
            else:
                grouped = group.mean()
        else:
            grouped = working.groupby(["_x", "_y"], dropna=True).size()

        return [
            {
                "xLabel": str(x_label),
                "yLabel": str(y_label),
                "label": f"{x_label} / {y_label}",
                "value": round(float(value), 2),
            }
            for (x_label, y_label), value in grouped.items()
        ]

    def _category_aggregate_data(
        self,
        dataframe: pd.DataFrame,
        category_column: str,
        numeric_column: str,
        aggregation: str,
        sort_by_value: bool = True,
    ) -> list[dict[str, Any]]:
        if numeric_column not in dataframe.columns:
            return []

        working = dataframe[[category_column, numeric_column]].copy()
        working[numeric_column] = pd.to_numeric(working[numeric_column], errors="coerce")
        group = working.dropna().groupby(category_column, dropna=True)[numeric_column]
        if aggregation == "sum":
            grouped = group.sum()
        elif aggregation == "median":
            grouped = group.median()
        else:
            grouped = group.mean()

        grouped = grouped.sort_values(ascending=False) if sort_by_value else grouped.sort_index()
        grouped = grouped.head(12)
        return [
            {"label": str(label), "value": round(float(value), 2)}
            for label, value in grouped.items()
        ]

    def _scatter_data(
        self,
        dataframe: pd.DataFrame,
        x_column: str,
        y_column: str,
    ) -> list[dict[str, Any]]:
        if y_column not in dataframe.columns:
            return []

        working = dataframe[[x_column, y_column]].copy()
        working[x_column] = pd.to_numeric(working[x_column], errors="coerce")
        working[y_column] = pd.to_numeric(working[y_column], errors="coerce")
        working = working.dropna().head(200)
        return [
            {"label": str(index), "x": float(row[x_column]), "y": float(row[y_column])}
            for index, row in working.iterrows()
        ]

    def _layout(self, card_count: int) -> list[dict[str, int | str]]:
        return [
            {
                "card_id": f"card-{index}",
                "x": (index % 3) * 4,
                "y": (index // 3) * 3,
                "w": 4,
                "h": 3,
            }
            for index in range(card_count)
        ]
