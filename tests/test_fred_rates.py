"""Unit tests for the FRED rate fetcher — network call is mocked out."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from src.data_collection import fred_rates

# A trimmed but realistic fredgraph.csv response: a holiday (empty value) and
# a genuinely missing observation ("."), both of which must be dropped.
SAMPLE_CSV = "observation_date,SOFR\n2026-06-30,3.68\n2026-07-01,\n2026-07-02,.\n2026-07-03,3.66\n"


def test_fetch_fred_series_drops_missing_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        text = SAMPLE_CSV

        def raise_for_status(self) -> None:
            pass

    captured: dict = {}

    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(fred_rates.requests, "get", fake_get)

    result = fred_rates.fetch_fred_series(
        series_id="SOFR",
        start_date=dt.date(2026, 6, 30),
        end_date=dt.date(2026, 7, 3),
        base_url="https://example.test/graph",
    )

    # Only the two rows with an actual numeric value should survive.
    assert len(result) == 2
    assert list(result.columns) == ["date", "value"]
    assert result["value"].tolist() == [3.68, 3.66]
    assert result["date"].iloc[-1] == pd.Timestamp("2026-07-03")

    assert captured["url"] == "https://example.test/graph/fredgraph.csv"
    assert captured["params"] == {"id": "SOFR", "cosd": "2026-06-30", "coed": "2026-07-03"}
