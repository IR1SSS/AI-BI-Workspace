from app.infrastructure.visualization.echarts_spec_repair import EChartsSpecRepairer


def test_echarts_spec_repairer_strips_markdown_and_trailing_commas():
    content = """
    ```json
    {
      xAxis: { type: "category", data: ["A", "B"], },
      yAxis: { type: "value", },
      series: [{ type: "bar", data: [1, 2], },],
    }
    ```
    """

    option = EChartsSpecRepairer().repair_or_fallback(content, [], "Fallback")

    assert option["series"][0]["type"] == "bar"
    assert option["xAxis"]["data"] == ["A", "B"]


def test_echarts_spec_repairer_returns_safe_bar_when_unrepairable():
    option = EChartsSpecRepairer().repair_or_fallback(
        "not json",
        [{"label": "A", "value": 2}, {"label": "B", "value": 5}],
        "Safe fallback",
    )

    assert option["title"]["text"] == "Safe fallback"
    assert option["xAxis"]["data"] == ["B", "A"]
    assert option["series"][0]["data"] == [5.0, 2.0]
