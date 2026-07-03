"""Unit tests for the ECB EUR/USD fetcher — network call is mocked out.

The ECB returns "SDMX-CSV": one row per observation plus a lot of metadata
columns. We only assert that `fetch_eurusd_history` extracts the two columns
we actually need (date, rate) and builds the URL the way the ECB API expects
(flow_ref and series_key as separate path segments — see the module docstring
for why getting this wrong silently produces a 400 error).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from src.data_collection import ecb_fx

# A trimmed but realistic ECB SDMX-CSV response (same shape as the real API).
SAMPLE_CSV = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-02-01,1.0850,A\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-02-02,1.0900,A\n"
)


def test_fetch_eurusd_history_extracts_date_and_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        text = SAMPLE_CSV

        def raise_for_status(self) -> None:
            pass

    captured: dict = {}

    def fake_get(url: str, params: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(ecb_fx.requests, "get", fake_get)

    result = ecb_fx.fetch_eurusd_history(
        flow_ref="EXR",
        series_key="D.USD.EUR.SP00.A",
        start_date=dt.date(2024, 2, 1),
        end_date=dt.date(2024, 2, 2),
        base_url="https://example.test/service/data",
    )

    assert list(result.columns) == ["date", "eur_usd_rate"]
    assert len(result) == 2
    assert result["eur_usd_rate"].iloc[0] == pytest.approx(1.0850)
    assert result["date"].iloc[1] == pd.Timestamp("2024-02-02")

    # flow_ref and series_key must be joined as two path segments, not one
    # dotted string, or the real ECB API rejects the request.
    assert captured["url"] == "https://example.test/service/data/EXR/D.USD.EUR.SP00.A"
    assert captured["params"]["startPeriod"] == "2024-02-01"
    assert captured["params"]["endPeriod"] == "2024-02-02"
