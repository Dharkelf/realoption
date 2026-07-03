"""Fetch daily LME cash-settlement metal prices (USD/tonne) from westmetall.com.

Why westmetall.com: the London Metal Exchange (LME) is the actual price-setting venue
for industrial base metals like copper and aluminium, but its own historical data is
behind a paid subscription. westmetall.com republishes the official daily LME
"cash-settlement" price (the spot/next-day settlement price, as opposed to the
3-month forward price also quoted on the LME) for free, with one HTML table per
calendar year, going back to 2008. No API key or login required.

Quirk to handle: within a year's table, the header row ("date", "... Cash-Settlement",
...) repeats once per month block instead of appearing only once at the top. We drop
those repeated header rows during parsing.
"""

from __future__ import annotations

import datetime as dt
import logging
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# A generous timeout: westmetall is a small site, but we'd rather fail loudly than
# hang the pipeline indefinitely on a slow response.
REQUEST_TIMEOUT_SECONDS = 20


def fetch_year_html(field: str, year: int, base_url: str, user_agent: str) -> str:
    """Download the raw HTML page for one metal ('field') and one calendar year.

    `field` is westmetall's internal series code, e.g. "LME_Cu_cash" for copper or
    "LME_Al_cash" for aluminium — see config/settings.yaml for the mapping.
    Kept separate from `parse_year_table` so tests can exercise the parser on a
    saved HTML fixture without making a real network call.
    """
    response = requests.get(
        base_url,
        params={"action": "table", "field": field, "year": str(year)},
        headers={"User-Agent": user_agent},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


def parse_year_table(html: str, column_prefix: str) -> pd.DataFrame:
    """Turn one year's HTML table into a tidy (date, price) DataFrame.

    `column_prefix` ("cu" or "al") becomes part of the output column name so that
    copper and aluminium series can later be merged side by side without clashing.
    """
    # pandas.read_html scans the page for <table> elements and returns a list of
    # DataFrames — westmetall's year pages contain exactly one table. Wrapping in
    # StringIO forces pandas to treat `html` as literal markup rather than trying
    # to interpret it as a file path or URL.
    tables = pd.read_html(StringIO(html))
    table = tables[0]

    # Every month block repeats the header row as an ordinary data row (the value
    # in the "date" column is literally the string "date"). Drop those.
    table = table[table["date"] != "date"].copy()

    # The exact column name is e.g. "LME Copper Cash-Settlement" — find it by
    # substring instead of hard-coding the metal name, so this function works for
    # any metal westmetall publishes.
    cash_col = next(c for c in table.columns if "Cash-Settlement" in c)

    # Dates arrive as "02. July 2026"; prices as "9,875.00" (thousands separator).
    table["date"] = pd.to_datetime(table["date"], format="%d. %B %Y")
    table[f"{column_prefix}_usd_per_tonne"] = (
        table[cash_col].astype(str).str.replace(",", "", regex=False).astype(float)
    )

    return table[["date", f"{column_prefix}_usd_per_tonne"]].sort_values("date").reset_index(drop=True)


def fetch_lme_cash_history(
    field: str,
    column_prefix: str,
    start_date: dt.date,
    end_date: dt.date,
    base_url: str,
    user_agent: str,
) -> pd.DataFrame:
    """Fetch and stitch together every year page needed to cover [start_date, end_date].

    westmetall only serves one calendar year per request, so a 3-year lookback
    means 3-4 requests (the partial start/end years are fetched in full and then
    trimmed to the requested window).
    """
    frames = []
    for year in range(start_date.year, end_date.year + 1):
        logger.info("fetching westmetall field=%s year=%s", field, year)
        html = fetch_year_html(field, year, base_url, user_agent)
        frames.append(parse_year_table(html, column_prefix))

    history = pd.concat(frames, ignore_index=True)

    # Trim the first/last partial years down to the exact requested window.
    mask = (history["date"] >= pd.Timestamp(start_date)) & (history["date"] <= pd.Timestamp(end_date))
    return history.loc[mask].sort_values("date").reset_index(drop=True)
