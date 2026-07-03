"""Fetch the daily official EUR/USD reference rate from the ECB's public Data Portal.

Why the ECB: it publishes the reference exchange rate it uses itself, once per
business day at 14:15 CET, free and without an API key, via its "Data Portal" REST
API (the successor to the older "SDW" service, which no longer resolves). This lets
us convert the USD/tonne LME metal prices into EUR/tonne for an Austrian/European
cost perspective, without depending on a paid FX data vendor.

The dataflow/series key "EXR / D.USD.EUR.SP00.A" decodes as:
  EXR   = exchange rates dataflow (the "flow reference", first path segment)
  D     = daily frequency
  USD   = the "measured" currency (US dollar)
  EUR   = the base/denominator currency (1 EUR = X USD)
  SP00  = spot rate
  A     = "average"/reference rate collection
So a value of 1.10 means 1 EUR = 1.10 USD that day. The ECB Data Portal API expects
these as two separate URL path segments (".../data/EXR/D.USD.EUR.SP00.A"), not one
dotted string — a 400 Bad Request is what you get if you concatenate them wrong.
"""

from __future__ import annotations

import datetime as dt
import logging
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20


def fetch_eurusd_history(
    flow_ref: str,
    series_key: str,
    start_date: dt.date,
    end_date: dt.date,
    base_url: str,
) -> pd.DataFrame:
    """Download the daily EUR/USD rate for [start_date, end_date] as a tidy DataFrame.

    The ECB API accepts the whole date range in a single request (no yearly
    pagination like westmetall), so this is just one HTTP call.
    """
    url = f"{base_url}/{flow_ref}/{series_key}"
    logger.info("fetching ECB EUR/USD rate from %s to %s", start_date, end_date)

    response = requests.get(
        url,
        params={
            "format": "csvdata",
            "startPeriod": start_date.isoformat(),
            "endPeriod": end_date.isoformat(),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    # The ECB returns "SDMX-CSV": one observation per row, with a lot of metadata
    # columns we don't need. We only care about the observation date and value.
    raw = pd.read_csv(StringIO(response.text))
    tidy = raw[["TIME_PERIOD", "OBS_VALUE"]].rename(
        columns={"TIME_PERIOD": "date", "OBS_VALUE": "eur_usd_rate"}
    )
    tidy["date"] = pd.to_datetime(tidy["date"])
    return tidy.sort_values("date").reset_index(drop=True)
