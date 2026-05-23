from app.infrastructure.analysis.ai_analysis_planner import AIAnalysisPlanner

DELIVERY_DELAY_COLUMN = (
    "\u5b9e\u9645\u4ea4\u8d27\u65e5\u671f_\u8f83_"
    "\u8ba1\u5212\u4ea4\u8d27\u65e5\u671f_\u5929\u6570"
)


def test_fallback_plan_handles_derived_numeric_and_moderate_categories():
    profile = {
        "row_count": 3141,
        "column_count": 11,
        "quality_issues": [],
        "columns": [
            {
                "name": "\u7535\u5f71\u540d",
                "is_numeric": False,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 3139,
            },
            {
                "name": "\u7d2f\u8ba1\u7968\u623f_\u6570\u503c",
                "is_numeric": True,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 2138,
            },
            {
                "name": "\u4e0a\u6620\u65f6\u95f4",
                "is_numeric": False,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 1442,
            },
            {
                "name": "\u4e0a\u6620\u65f6\u95f4_\u5e74\u4efd",
                "is_numeric": True,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 30,
            },
            {
                "name": "\u56fd\u5bb6\u53ca\u5730\u533a",
                "is_numeric": False,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 48,
            },
        ],
    }

    chart_plan = AIAnalysisPlanner()._fallback_plan(profile)["chart_plan"]

    assert len(chart_plan) >= 3
    assert {chart["chart_type"] for chart in chart_plan} >= {"histogram", "bar", "line", "heatmap"}
    assert any(chart["x"] == "\u56fd\u5bb6\u53ca\u5730\u533a" for chart in chart_plan)
    assert any(chart["x"] == "\u4e0a\u6620\u65f6\u95f4_\u5e74\u4efd" for chart in chart_plan)


def test_fallback_plan_does_not_treat_order_number_as_measure():
    profile = {
        "row_count": 40,
        "column_count": 6,
        "quality_issues": [],
        "columns": [
            {
                "name": "\u91c7\u8d2d\u8ba2\u5355\u53f7",
                "is_numeric": True,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 40,
            },
            {
                "name": "\u5b9e\u9645\u4ea4\u8d27\u65e5\u671f",
                "is_numeric": False,
                "is_datetime": True,
                "is_probable_index": False,
                "unique_count": 36,
            },
            {
                "name": "\u7269\u8d44\u7c7b\u522b",
                "is_numeric": False,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 3,
            },
            {
                "name": DELIVERY_DELAY_COLUMN,
                "is_numeric": True,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 12,
            },
        ],
    }

    chart_plan = AIAnalysisPlanner()._fallback_plan(profile)["chart_plan"]

    assert chart_plan
    assert all(chart.get("y") != "\u91c7\u8d2d\u8ba2\u5355\u53f7" for chart in chart_plan)
    assert all(chart.get("x") != "\u91c7\u8d2d\u8ba2\u5355\u53f7" for chart in chart_plan)
    assert any(
        chart.get("y") == DELIVERY_DELAY_COLUMN
        or chart.get("x") == DELIVERY_DELAY_COLUMN
        for chart in chart_plan
    )


def test_fallback_plan_treats_datetime_columns_as_time_dimensions():
    profile = {
        "row_count": 1000,
        "column_count": 5,
        "quality_issues": [],
        "columns": [
            {
                "name": "\u7edf\u8ba1\u5468\u671f",
                "is_numeric": False,
                "is_datetime": True,
                "is_probable_index": False,
                "unique_count": 6,
            },
            {
                "name": "\u7701\u5e02",
                "is_numeric": False,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 26,
            },
            {
                "name": "\u7528\u7535\u7c7b\u522b",
                "is_numeric": False,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 10,
            },
            {
                "name": "\u5f53\u671f\u503c",
                "is_numeric": True,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 900,
            },
            {
                "name": "\u7d2f\u8ba1\u503c",
                "is_numeric": True,
                "is_datetime": False,
                "is_probable_index": False,
                "unique_count": 880,
            },
        ],
    }

    chart_plan = AIAnalysisPlanner()._fallback_plan(profile)["chart_plan"]

    assert all(
        not (
            chart.get("chart_type") == "bar"
            and chart.get("x") == "\u7edf\u8ba1\u5468\u671f"
            and chart.get("aggregation") == "count"
        )
        for chart in chart_plan
    )
    assert any(
        chart.get("chart_type") == "line"
        and chart.get("x") == "\u7edf\u8ba1\u5468\u671f"
        and chart.get("y") == "\u5f53\u671f\u503c"
        and chart.get("aggregation") == "sum"
        for chart in chart_plan
    )
    assert any(
        chart.get("chart_type") == "heatmap"
        and chart.get("x") == "\u7edf\u8ba1\u5468\u671f"
        and chart.get("z") == "\u5f53\u671f\u503c"
        and chart.get("aggregation") == "sum"
        for chart in chart_plan
    )
