"""Unit tests for the westmetall scraper.

We never hit the real website in tests — that would make the test suite slow,
flaky (network hiccups) and dependent on westmetall staying online. Instead we
feed `parse_year_table` a small, hand-crafted HTML snippet that reproduces the
one quirk that actually matters: the repeated header row per month block.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data_collection import westmetall

# A minimal but faithful stand-in for a real westmetall year page: two month
# blocks, each starting with its own header row (the "quirk" the parser must
# filter out), and a thousands-separator in one price to check comma-stripping.
SAMPLE_HTML = """
<table>
<tr><th>date</th><th>LME Copper Cash-Settlement</th><th>LME Copper 3-month</th><th>LME Copper stock</th></tr>
<tr><td>02. February 2024</td><td>8,500.00</td><td>8,520.00</td><td>100000</td></tr>
<tr><td>01. February 2024</td><td>8,450.50</td><td>8,470.00</td><td>101000</td></tr>
<tr><td>date</td><td>LME Copper Cash-Settlement</td><td>LME Copper 3-month</td><td>LME Copper stock</td></tr>
<tr><td>31. January 2024</td><td>8,300.00</td><td>8,320.00</td><td>102000</td></tr>
</table>
"""


def test_parse_year_table_drops_repeated_headers_and_sorts_by_date() -> None:
    result = westmetall.parse_year_table(SAMPLE_HTML, column_prefix="cu")

    # The repeated header row must not survive as a fake data row.
    assert len(result) == 3
    assert list(result.columns) == ["date", "cu_usd_per_tonne"]

    # parse_year_table promises ascending date order, regardless of the HTML's
    # (descending) order — downstream code (merging, plotting) assumes this.
    assert result["date"].is_monotonic_increasing
    assert result["date"].iloc[0] == pd.Timestamp("2024-01-31")
    assert result["date"].iloc[-1] == pd.Timestamp("2024-02-02")


def test_parse_year_table_strips_thousands_separator() -> None:
    result = westmetall.parse_year_table(SAMPLE_HTML, column_prefix="cu")

    # "8,500.00" must become the float 8500.00, not fail to parse or truncate
    # at the comma.
    row = result[result["date"] == pd.Timestamp("2024-02-02")].iloc[0]
    assert row["cu_usd_per_tonne"] == pytest.approx(8500.00)


def test_parse_year_table_uses_given_column_prefix() -> None:
    result = westmetall.parse_year_table(SAMPLE_HTML, column_prefix="al")

    # The prefix lets copper and aluminium be merged side by side later
    # without their price columns clashing.
    assert "al_usd_per_tonne" in result.columns
    assert "cu_usd_per_tonne" not in result.columns


def test_fetch_year_html_calls_requests_with_expected_params(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self) -> None:
            pass

    def fake_get(url: str, params: dict, headers: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(westmetall.requests, "get", fake_get)

    html = westmetall.fetch_year_html(
        field="LME_Cu_cash",
        year=2024,
        base_url="https://example.test/markdaten.php",
        user_agent="test-agent",
    )

    assert html == "<html>ok</html>"
    assert captured["params"] == {"action": "table", "field": "LME_Cu_cash", "year": "2024"}
    assert captured["headers"]["User-Agent"] == "test-agent"
