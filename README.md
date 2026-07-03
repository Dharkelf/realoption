# realoption

## Overview

Collection of independent real-options / derivative-pricing mini-projects. Each result is
a self-contained, reproducible valuation model (binomial lattices, Monte Carlo simulation,
closed-form threshold models, etc.), inspired by — but not copied from — reference course
material kept locally only (see `AGENTS.md`, section "`local/` Directory — Never Synced").

Mini-projects are added incrementally; this README is updated in the same commit as each one.

The first supporting piece is the **`business`** use case: a data collection pipeline that
supplies real, industrial daily commodity prices (copper, aluminium) so later mini-projects
can value real options with actual market data instead of made-up numbers.

## Architecture

```
config/settings.yaml ──► src/<module>/ ──► results/<use_case>/*.py ──► (optional) jupytext ──► .ipynb
                              │
                              ▼
                          tests/test_<module>.py
```

### `business` use case — data flow

```
westmetall.com (free, daily)          ECB Data Portal (free, daily)
  LME Copper Cash-Settlement            EXR/D.USD.EUR.SP00.A
  LME Aluminium Cash-Settlement         (USD per 1 EUR)
        │                                       │
        ▼                                       ▼
 src/data_collection/westmetall.py     src/data_collection/ecb_fx.py
        │                                       │
        └───────────────┬───────────────────────┘
                         ▼
          src/data_collection/pipeline.py::run()
                         │
        ┌────────────────┼─────────────────────┐
        ▼                ▼                     ▼
 data/raw/*.parquet  data/processed/      results/business/
 (one file per         metals_prices.      metals_prices.csv
  source, as scraped)  parquet             (no path needed —
                        (merged + EUR)      simple scripts read
                                            it directly)
```

Why both Parquet and CSV: Parquet under `data/` is the analysis-ready, typed
storage format used by the rest of the project (per `AGENTS.md`). The CSV under
`results/business/` exists purely so a simple, standalone `results/business/*.py`
script (or its jupytext-converted `.ipynb`) can do `pd.read_csv("metals_prices.csv")`
without needing to know about `data/` or any path configuration at all.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
```

## Configuration

All tunable parameters for the `business` data pipeline live in `config/settings.yaml`:

| Key | Meaning |
|---|---|
| `metals.lookback_years` | How many years back from today to fetch (rolling window) |
| `metals.series.<name>.westmetall_field` | westmetall.com's internal series code (e.g. `LME_Cu_cash`) |
| `metals.series.<name>.column_prefix` | Column name prefix in the merged table (`cu`, `al`) |
| `metals.source.base_url` / `user_agent` | westmetall.com endpoint and polite User-Agent string |
| `fx.flow_ref` / `fx.series_key` | ECB Data Portal dataflow + series key for EUR/USD |
| `fx.source.base_url` | ECB Data Portal API endpoint |
| `paths.raw_dir` / `processed_dir` / `results_dir` | Where Parquet/CSV output is written |
| `output.use_case` | Subfolder under `results/` for this mini-project (`business`) |
| `output.processed_filename` / `csv_filename` | Output file names |

## Usage

Run the full data collection pipeline (fetch, merge, convert, save):

```bash
python main.py
```

This (re)creates:
- `data/raw/lme_copper_cash.parquet`, `data/raw/lme_aluminium_cash.parquet`, `data/raw/ecb_eurusd.parquet`
- `data/processed/metals_prices.parquet`
- `results/business/metals_prices.csv` — columns: `date`, `cu_usd_per_tonne`, `al_usd_per_tonne`,
  `eur_usd_rate`, `cu_eur_per_tonne`, `al_eur_per_tonne`

Once a `results/business/*.py` valuation script is added, run it standalone:

```bash
python results/business/<name>.py
```

Convert it to a notebook:

```bash
jupytext --to notebook results/business/<name>.py
```

## Data

`results/business/metals_prices.csv` (and the matching `data/processed/metals_prices.parquet`):

| Column | Type | Meaning |
|---|---|---|
| `date` | date | Trading day (LME + ECB business day) |
| `cu_usd_per_tonne` | float | LME Copper Cash-Settlement, USD/tonne |
| `al_usd_per_tonne` | float | LME Aluminium Cash-Settlement, USD/tonne |
| `eur_usd_rate` | float | ECB reference rate, USD per 1 EUR |
| `cu_eur_per_tonne` | float | Copper price converted to EUR/tonne (`cu_usd_per_tonne / eur_usd_rate`) |
| `al_eur_per_tonne` | float | Aluminium price converted to EUR/tonne (`al_usd_per_tonne / eur_usd_rate`) |

Rows are an **inner join** on `date` across all three sources — a date only appears if
westmetall published both metals *and* the ECB published a rate that day. See
`REPORT.md` for the actual row count and date range last observed.

## Development

```bash
pytest tests/
pre-commit run --all-files
```

Add a new mini-project by creating a new `src/<module>/`, a matching
`results/<use_case>/` directory, and `tests/test_<module>.py` — then update this
README and `AGENTS.md`'s "Modules in This Project" table in the same commit.

## Known Limitations

- westmetall.com and the ECB Data Portal are both free but unofficial/best-effort
  sources (no SLA); if either changes its HTML/API shape, the scraper/parser will
  need updating.
- Only cash-settlement (spot) prices are collected, not the LME 3-month forward —
  add it later if a mini-project needs the forward curve.
- No mini-project consumes this data yet — `results/business/` currently holds only
  the input CSV.

## Future Improvements

- First valuation mini-project using `results/business/metals_prices.csv`
  (to be scoped by the user).

## References

- [westmetall.com market data](https://www.westmetall.com/en/markdaten.php) — free daily LME cash-settlement prices
- [ECB Data Portal](https://data-api.ecb.europa.eu/) — free daily EUR/USD reference rate
- See `AGENTS.md` for full project conventions.
