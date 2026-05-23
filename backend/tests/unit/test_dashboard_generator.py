import pandas as pd
from app.infrastructure.visualization.dashboard_generator import DashboardGenerator


def test_dashboard_generator_does_not_emit_analysis_text_cards():
    profile = {"row_count": 2, "column_count": 2, "quality_issues": []}
    analysis = {
        "source": "llm",
        "insights": [{"title": "Insight", "detail": "Details"}],
        "cleaning_suggestions": [{"title": "Clean", "rationale": "Reason"}],
        "feature_suggestions": [{"title": "Feature", "rationale": "Reason"}],
        "chart_plan": [
            {
                "chart_type": "bar",
                "title": "Category count",
                "x": "category",
                "y": None,
                "aggregation": "count",
            }
        ],
    }

    dashboard = DashboardGenerator().generate(
        "dataset-1",
        "v0001",
        "orders.csv",
        profile,
        pd.DataFrame({"category": ["a", "b"]}),
        analysis,
    )

    assert dashboard["title"] == "orders.csv Dashboard Draft"
    assert all(card["type"] != "text" for card in dashboard["cards"])


def test_dashboard_generator_builds_extended_chart_data():
    profile = {"row_count": 4, "column_count": 4, "quality_issues": []}
    dataframe = pd.DataFrame(
        {
            "year": [2023, 2023, 2024, 2024],
            "region": ["A", "B", "A", "B"],
            "sales": [10, 20, 30, 40],
            "category": ["x", "x", "y", "z"],
        }
    )
    analysis = {
        "source": "fallback",
        "chart_plan": [
            {
                "chart_type": "heatmap",
                "title": "Region by year",
                "x": "year",
                "y": "region",
                "aggregation": "count",
            },
            {
                "chart_type": "bullet",
                "title": "Sales by region",
                "x": "region",
                "y": "sales",
                "aggregation": "avg",
            },
            {
                "chart_type": "boxplot",
                "title": "Sales spread",
                "x": "sales",
                "aggregation": "median",
            },
            {
                "chart_type": "treemap",
                "title": "Category composition",
                "x": "category",
                "aggregation": "count",
            },
        ],
    }

    dashboard = DashboardGenerator().generate(
        "dataset-1",
        "v0001",
        "orders.csv",
        profile,
        dataframe,
        analysis,
    )
    chart_cards = [card for card in dashboard["cards"] if card["type"] == "chart"]

    assert [card["chart_type"] for card in chart_cards] == [
        "heatmap",
        "bullet",
        "boxplot",
        "treemap",
    ]
    assert chart_cards[0]["data"][0].keys() >= {"xLabel", "yLabel", "value"}
    assert chart_cards[1]["data"][0].keys() >= {"label", "value", "target"}
    assert chart_cards[2]["data"][0].keys() >= {"min", "q1", "median", "q3", "max"}


def test_dashboard_generator_formats_axis_based_titles_without_underscores():
    profile = {"row_count": 2, "column_count": 2, "quality_issues": []}
    dataframe = pd.DataFrame(
        {
            "时间": ["2026-01-01", "2026-01-02"],
            "销售额": [100, 140],
            "累计票房_数值": [300, 420],
        }
    )
    analysis = {
        "source": "fallback",
        "chart_plan": [
            {
                "chart_type": "line",
                "title": "Average 销售额_by_时间",
                "x": "时间",
                "y": "销售额",
                "aggregation": "sum",
            },
            {
                "chart_type": "histogram",
                "title": "累计票房_数值 Distribution",
                "x": "累计票房_数值",
                "aggregation": "none",
            },
        ],
    }

    dashboard = DashboardGenerator().generate(
        "dataset-1",
        "v0001",
        "sales.csv",
        profile,
        dataframe,
        analysis,
    )
    chart_cards = [card for card in dashboard["cards"] if card["type"] == "chart"]

    assert [card["title"] for card in chart_cards] == ["每日销售额", "累计票房分布"]
    assert all("_" not in card["title"] for card in chart_cards)
