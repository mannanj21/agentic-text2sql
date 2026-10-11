from app.agent.charts import choose_chart


def test_chart_rules_are_deterministic() -> None:
    assert choose_chart(["date", "sales"], [["2026-01-01", 2]]).type == "line"
    assert choose_chart(["category", "sales"], [["a", 2], ["b", 3]]).type == "bar"
    assert choose_chart(["only"], [[1]]).type == "table"
