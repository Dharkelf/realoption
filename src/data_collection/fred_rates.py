"""Fetch a daily USD interest-rate series from FRED (Federal Reserve Economic Data).

Why FRED: it's the standard, free, public repository for US macro/financial time
series. Unlike most FRED usage examples you'll find online, this module does NOT
use FRED's official JSON API (which requires a free API key) — it uses the
"fredgraph.csv" endpoint that powers the interactive charts on the FRED website.
That endpoint returns a plain CSV for any series ID, with no key and no login,
which fits our "free, no-auth" sourcing rule.

We use it here for **SOFR** (Secured Overnight Financing Rate), the standard
USD risk-free proxy since LIBOR's retirement — this is the discount rate `r`
fed into the real-options lattice in `src/real_options/bermudan_purchase.py`.
"""

from __future__ import annotations

import datetime as dt
import logging
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20


def fetch_fred_series(
    series_id: str,
    start_date: dt.date,
    end_date: dt.date,
    base_url: str,
) -> pd.DataFrame:
    """Download one FRED series as a tidy (date, value) DataFrame.

    FRED marks non-trading days (weekends, US holidays) with an empty value
    rather than omitting the row entirely — those rows are dropped here, since
    a missing rate isn't a data point we can use (and would otherwise show up
    as NaN downstream for no good reason).
    """
    logger.info("fetching FRED series=%s from %s to %s", series_id, start_date, end_date)

    response = requests.get(
        f"{base_url}/fredgraph.csv",
        params={
            "id": series_id,
            "cosd": start_date.isoformat(),  # "cosd" = chart observation start date
            "coed": end_date.isoformat(),  # "coed" = chart observation end date
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    raw = pd.read_csv(StringIO(response.text))
    raw = raw.rename(columns={"observation_date": "date", series_id: "value"})
    raw["date"] = pd.to_datetime(raw["date"])

    # "." is FRED's own missing-value marker on some series; combined with the
    # blank-string case above, both must be coerced before dropping NaNs.
    raw["value"] = pd.to_numeric(raw["value"], errors="coerce")
    return raw.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
