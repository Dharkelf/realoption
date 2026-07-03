"""Integration test for the full collect -> merge -> convert -> save pipeline.

This does NOT hit the network — `westmetall.fetch_lme_cash_history` and
`ecb_fx.fetch_eurusd_history` are replaced with small synthetic DataFrames, so
the test focuses on what `pipeline.run()` itself is responsible for: joining
three sources on date, computing the EUR conversion correctly, and writing
Parquet (raw + processed) and CSV (for the simple `results/business/*.py`
scripts) to the right places. Real data structures (actual pandas DataFrames,
actual Parquet/CSV files on disk) are used throughout, per the project's
"integration tests use real data structures, not mocks" rule — only the two
network-fetching functions are swapped out.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.data_collection import ecb_fx, fred_rates, pipeline, westmetall


def _fake_lme_history(field: str, column_prefix: str, **_kwargs: Any) -> pd.DataFrame:
    # Three trading days; 2024-01-03 only exists for copper, to prove the
    # inner join correctly drops dates that aren't in every source.
    if column_prefix == "cu":
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        prices = [8000.0, 8100.0, 8200.0]
    else:
        dates = ["2024-01-01", "2024-01-02"]
        prices = [2000.0, 2050.0]
    return pd.DataFrame({"date": pd.to_datetime(dates), f"{column_prefix}_usd_per_tonne": prices})


def _fake_eurusd_history(**_kwargs: Any) -> pd.DataFrame:
    dates = ["2024-01-01", "2024-01-02"]
    rates = [1.10, 1.10]  # constant rate keeps the expected EUR math simple
    return pd.DataFrame({"date": pd.to_datetime(dates), "eur_usd_rate": rates})


def _fake_sofr_history(**_kwargs: Any) -> pd.DataFrame:
    # Column name "value" matches the real fred_rates.fetch_fred_series output;
    # pipeline.run() renames it to "sofr_rate_pct" itself.
    dates = ["2024-01-01", "2024-01-02"]
    rates = [5.30, 5.31]
    return pd.DataFrame({"date": pd.to_datetime(dates), "value": rates})


@pytest.fixture
def isolated_output_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect the pipeline's raw/processed/results output into tmp_path.

    Patched on the `pipeline` module itself (not `src.utils.paths`), because
    `pipeline.py` imported these functions by name — patching the origin
    module wouldn't affect the names already bound in `pipeline`'s namespace.
    """
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    results_root = tmp_path / "results"
    raw.mkdir()
    processed.mkdir()

    def fake_results_dir(use_case: str) -> Path:
        use_case_dir = results_root / use_case
        use_case_dir.mkdir(parents=True, exist_ok=True)
        return use_case_dir

    monkeypatch.setattr(pipeline, "raw_dir", lambda: raw)
    monkeypatch.setattr(pipeline, "processed_dir", lambda: processed)
    monkeypatch.setattr(pipeline, "results_dir", fake_results_dir)
    return {
        "raw": raw,
        "processed": processed,
        "results_business": results_root / "business",
        "results_buyperp": results_root / "buyperp",
    }


def test_run_merges_on_date_and_converts_to_eur(
    monkeypatch: pytest.MonkeyPatch, isolated_output_dirs: dict[str, Path]
) -> None:
    monkeypatch.setattr(westmetall, "fetch_lme_cash_history", _fake_lme_history)
    monkeypatch.setattr(ecb_fx, "fetch_eurusd_history", _fake_eurusd_history)
    monkeypatch.setattr(fred_rates, "fetch_fred_series", _fake_sofr_history)

    result = pipeline.run()

    # 2024-01-03 has no aluminium price and no FX rate, so the inner join must
    # drop it — only the two fully-covered dates remain.
    assert len(result) == 2
    assert result["date"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]

    # EUR/USD rate is "USD per 1 EUR", so USD -> EUR is a division, not a
    # multiplication — this is the exact bug a learner would most likely make.
    first_row = result.iloc[0]
    assert first_row["cu_eur_per_tonne"] == pytest.approx(8000.0 / 1.10)
    assert first_row["al_eur_per_tonne"] == pytest.approx(2000.0 / 1.10)


def test_run_writes_raw_parquet_processed_parquet_and_csv(
    monkeypatch: pytest.MonkeyPatch, isolated_output_dirs: dict[str, Path]
) -> None:
    monkeypatch.setattr(westmetall, "fetch_lme_cash_history", _fake_lme_history)
    monkeypatch.setattr(ecb_fx, "fetch_eurusd_history", _fake_eurusd_history)
    monkeypatch.setattr(fred_rates, "fetch_fred_series", _fake_sofr_history)

    pipeline.run()

    raw, processed = isolated_output_dirs["raw"], isolated_output_dirs["processed"]
    assert (raw / "lme_copper_cash.parquet").exists()
    assert (raw / "lme_aluminium_cash.parquet").exists()
    assert (raw / "ecb_eurusd.parquet").exists()
    assert (raw / "fred_sofr.parquet").exists()
    assert (processed / "metals_prices.parquet").exists()

    # metals_prices.csv is copied into every use case (business AND buyperp),
    # so each standalone results/<use_case>/*.py script can read it with no
    # path plumbing at all.
    for results_dir in (isolated_output_dirs["results_business"], isolated_output_dirs["results_buyperp"]):
        csv_path = results_dir / "metals_prices.csv"
        assert csv_path.exists()
        csv_df = pd.read_csv(csv_path, parse_dates=["date"])
        assert len(csv_df) == 2
        assert "cu_eur_per_tonne" in csv_df.columns

    # SOFR (the buyperp discount rate) is only needed by that one use case.
    sofr_path = isolated_output_dirs["results_buyperp"] / "sofr_rate.csv"
    assert sofr_path.exists()
    sofr_df = pd.read_csv(sofr_path)
    assert list(sofr_df.columns) == ["date", "sofr_rate_pct"]
    assert not (isolated_output_dirs["results_business"] / "sofr_rate.csv").exists()


def test_date_window_is_lookback_years_ending_today() -> None:
    start, end = pipeline._date_window(lookback_years=3)

    assert end == dt.date.today()
    assert start == (pd.Timestamp(end) - pd.DateOffset(years=3)).date()
