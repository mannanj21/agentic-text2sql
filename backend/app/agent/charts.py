"""Deterministic chart selection for query results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ChartSpec(BaseModel):
    type: Literal["line", "bar", "table"]
    x: str | None = None
    y: str | None = None
    title: str = "Query results"


def choose_chart(columns: list[str], rows: list[list[Any]]) -> ChartSpec:
    """Pick a conservative visualisation; fall back to a table."""
    if not columns or not rows or len(columns) < 2:
        return ChartSpec(type="table")
    values = list(zip(*rows, strict=False))
    numeric = [
        i
        for i, col in enumerate(values)
        if col and all(isinstance(v, (int, float)) for v in col if v is not None)
    ]
    if not numeric:
        return ChartSpec(type="table")
    y = numeric[0]
    x = next((i for i in range(len(columns)) if i != y), None)
    if x is None:
        return ChartSpec(type="table")
    name = columns[x].lower()
    chart_type: Literal["line", "bar"] = "line" if "date" in name or "time" in name else "bar"
    if len(set(values[x])) > 20 and chart_type == "bar":
        return ChartSpec(type="table")
    return ChartSpec(type=chart_type, x=columns[x], y=columns[y])
