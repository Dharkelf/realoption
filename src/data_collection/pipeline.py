"""End-to-end data collection pipeline: LME metal prices + EUR/USD -> Parquet + CSV.

This module is the single entry point the rest of the project should call (from
`main.py` or a test) to (re)build the industrial metals price dataset. It follows
the project's data convention: raw scraped data is kept as Parquet under
`data/raw/` (one file per source, untouched/append-only in spirit), a merged and
currency-converted table is kept as Parquet under `data/processed/` (the
"analysis-ready" version), and — because the `results/business/*.py` scripts are
meant to be simple, standalone files a non-programmer could run without wiring up
a data folder — the same table is also dropped as a plain CSV right next to those
scripts, so they can load it with just `pd.read_csv("metals_prices.csv")`.
"""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from src.data_collection import ecb_fx, westmetall
from src.utils.paths import load_settings, processed_dir, raw_dir, results_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _date_window(lookback_years: int) -> tuple[dt.date, dt.date]:
    """Compute [start_date, end_date] as a rolling N-year window ending today.

    Using today's date (rather than a fixed date in settings.yaml) means the
    dataset is always "the last N years" whenever the pipeline is re-run.
    """
    end_date = dt.date.today()
    start_date = (pd.Timestamp(end_date) - pd.DateOffset(years=lookback_years)).date()
    return start_date, end_date


def run() -> pd.DataFrame:
    settings = load_settings()
    metals_cfg = settings["metals"]
    fx_cfg = settings["fx"]
    output_cfg = settings["output"]

    start_date, end_date = _date_window(metals_cfg["lookback_years"])
    logger.info("collecting industrial metals data for window %s to %s", start_date, end_date)

    # --- 1. Fetch each raw series independently ---------------------------------
    # Copper and aluminium each come from their own westmetall "field"; the FX
    # rate comes from a completely different source (ECB). Keeping them as three
    # separate fetches (rather than one tangled function) mirrors how a human
    # would explain the data lineage: "the metal prices come from westmetall, the
    # FX rate comes from the ECB".
    metal_frames: dict[str, pd.DataFrame] = {}
    for metal_name, metal_cfg in metals_cfg["series"].items():
        frame = westmetall.fetch_lme_cash_history(
            field=metal_cfg["westmetall_field"],
            column_prefix=metal_cfg["column_prefix"],
            start_date=start_date,
            end_date=end_date,
            base_url=metals_cfg["source"]["base_url"],
            user_agent=metals_cfg["source"]["user_agent"],
        )
        metal_frames[metal_name] = frame
        # Raw data is stored as-is, one Parquet file per source, so the original
        # scrape is always available even if the merge/FX logic changes later.
        frame.to_parquet(raw_dir() / f"lme_{metal_name}_cash.parquet", index=False)

    fx_frame = ecb_fx.fetch_eurusd_history(
        flow_ref=fx_cfg["flow_ref"],
        series_key=fx_cfg["series_key"],
        start_date=start_date,
        end_date=end_date,
        base_url=fx_cfg["source"]["base_url"],
    )
    fx_frame.to_parquet(raw_dir() / "ecb_eurusd.parquet", index=False)

    # --- 2. Merge on date ---------------------------------------------------------
    # An inner join keeps only the dates where *all three* series have a value.
    # LME and ECB are both closed on different sets of public holidays, so a
    # handful of dates naturally drop out here — that's expected, not a bug.
    merged = metal_frames["copper"]
    for metal_name in list(metal_frames)[1:]:
        merged = merged.merge(metal_frames[metal_name], on="date", how="inner")
    merged = merged.merge(fx_frame, on="date", how="inner")

    # --- 3. Add the EUR-converted view -------------------------------------------
    # eur_usd_rate is "USD per 1 EUR" (ECB convention), so dividing a USD amount
    # by it converts USD -> EUR (e.g. 9875 USD / 1.10 USD-per-EUR = 8977 EUR).
    for metal_cfg in metals_cfg["series"].values():
        prefix = metal_cfg["column_prefix"]
        merged[f"{prefix}_eur_per_tonne"] = merged[f"{prefix}_usd_per_tonne"] / merged["eur_usd_rate"]

    merged = merged.sort_values("date").reset_index(drop=True)

    # --- 4. Persist: Parquet for downstream analysis, CSV for the simple scripts --
    merged.to_parquet(processed_dir() / output_cfg["processed_filename"], index=False)

    csv_path = results_dir(output_cfg["use_case"]) / output_cfg["csv_filename"]
    merged.to_csv(csv_path, index=False)
    logger.info("wrote %d rows to %s", len(merged), csv_path)

    return merged


if __name__ == "__main__":
    run()
