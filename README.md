# realoption

## Overview

Collection of independent real-options / derivative-pricing mini-projects. Each result is
a self-contained, reproducible valuation model (binomial lattices, Monte Carlo simulation,
closed-form threshold models, etc.), inspired by — but not copied from — reference course
material kept locally only (see `AGENTS.md`, section "`local/` Directory — Never Synced").

Mini-projects are added incrementally; this README is updated in the same commit as each one.

- **`business`**: a data collection pipeline supplying real, industrial daily commodity
  prices (copper, aluminium, EUR/USD, USD SOFR) so mini-projects can value real options
  with actual market data instead of made-up numbers.
- **`buyperp`**: values the flexibility to choose *when* within a year to buy an annual
  copper/aluminium requirement, against three alternative baselines.

## Architecture

```
config/settings.yaml ──► src/<module>/ ──► results/<use_case>/*.py ──► (optional) jupytext ──► .ipynb
                              │
                              ▼
                          tests/test_<module>.py
```

### `business` use case — data flow

```
westmetall.com (free, daily)     ECB Data Portal (free, daily)     FRED (free, daily)
  LME Copper Cash-Settlement       EXR/D.USD.EUR.SP00.A               SOFR
  LME Aluminium Cash-Settlement    (USD per 1 EUR)
        │                                 │                            │
        ▼                                 ▼                            ▼
 westmetall.py                       ecb_fx.py                   fred_rates.py
        │                                 │                            │
        └────────────────┬────────────────┘                            │
                          ▼                                            │
           src/data_collection/pipeline.py::run()  ◄────────────────────┘
                          │
        ┌─────────────────┼──────────────────────┬─────────────────────┐
        ▼                 ▼                      ▼                     ▼
 data/raw/*.parquet  data/processed/     results/business/     results/buyperp/
 (one file per         metals_prices.    metals_prices.csv     metals_prices.csv
  source, as scraped)  parquet           (no path needed)      + sofr_rate.csv
                        (merged + EUR)                         (no path needed)
```

Why both Parquet and CSV: Parquet under `data/` is the analysis-ready, typed
storage format used by the rest of the project (per `AGENTS.md`). The CSVs under
`results/<use_case>/` exist purely so a simple, standalone `results/<use_case>/*.py`
script (or its jupytext-converted `.ipynb`) can do `pd.read_csv("metals_prices.csv")`
without needing to know about `data/` or any path configuration at all.

### `buyperp` use case — Year 1 purchase-timing option

The company must buy a fixed annual copper+aluminium requirement exactly once, at
whichever of `n` scheduled dates (month-ends) is cheapest — or be forced to buy at the
last one. `src/real_options/bermudan_purchase.py` prices this via a binomial lattice
(backward induction, real-world drift `mu` — see the module and script docstrings for
why risk-neutral pricing would trivially give zero timing value here) and cross-checks
it with Monte Carlo simulation, converting each scenario to EUR using the EUR/USD rate
simulated forward to that scenario's own execution date (not a flat snapshot rate).

```
results/buyperp/metals_prices.csv, sofr_rate.csv
                 │
                 ▼
results/buyperp/year1_purchase_option.py
                 │  (imports the reusable pricer)
                 ▼
    src/real_options/bermudan_purchase.py
        │                    │
        ▼                    ▼
 lattice (closed form)   Monte Carlo (paths + exercise thresholds)
        │                    │
        └─────────┬──────────┘
                   ▼
   real-options cost vs. 3 baselines (buy now / forced year-end / random 3-of-n),
   each in USD and execution-date-converted EUR
```

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .          # makes `src/` importable from any results/<use_case>/*.py
pre-commit install
```

## Configuration

All tunable parameters live in `config/settings.yaml`:

| Key | Meaning |
|---|---|
| `metals.lookback_years` | How many years back from today to fetch (rolling window) |
| `metals.series.<name>.westmetall_field` | westmetall.com's internal series code (e.g. `LME_Cu_cash`) |
| `metals.series.<name>.column_prefix` | Column name prefix in the merged table (`cu`, `al`) |
| `metals.source.base_url` / `user_agent` | westmetall.com endpoint and polite User-Agent string |
| `fx.flow_ref` / `fx.series_key` | ECB Data Portal dataflow + series key for EUR/USD |
| `fx.source.base_url` | ECB Data Portal API endpoint |
| `fred.series_id` | FRED series id for the USD risk-free proxy (`SOFR`) |
| `fred.source.base_url` | FRED `fredgraph.csv` endpoint |
| `paths.raw_dir` / `processed_dir` / `results_dir` | Where Parquet/CSV output is written |
| `output.use_cases` | Use-case folders under `results/` that get a `metals_prices.csv` copy |
| `output.sofr_use_case` / `sofr_csv_filename` | Where the SOFR CSV is copied (only `buyperp` needs it) |
| `output.processed_filename` / `csv_filename` | Output file names |
| `buyperp.cu_tonnes` / `al_tonnes` | Annual quantities (tonnes) — also set at the top of `year1_purchase_option.py` |
| `buyperp.n_opportunities` | Scheduled purchase dates per year (12 = monthly) |
| `buyperp.monte_carlo.n_simulations` / `seed` | Monte Carlo sample size and reproducibility seed |

## Usage

Run the full data collection pipeline (fetch, merge, convert, save):

```bash
python main.py
```

This (re)creates:
- `data/raw/lme_copper_cash.parquet`, `lme_aluminium_cash.parquet`, `ecb_eurusd.parquet`, `fred_sofr.parquet`
- `data/processed/metals_prices.parquet`
- `results/business/metals_prices.csv` and `results/buyperp/metals_prices.csv` — columns:
  `date`, `cu_usd_per_tonne`, `al_usd_per_tonne`, `eur_usd_rate`, `cu_eur_per_tonne`, `al_eur_per_tonne`
- `results/buyperp/sofr_rate.csv` — columns: `date`, `sofr_rate_pct`

Run a mini-project result standalone (from anywhere, thanks to the editable install):

```bash
python results/buyperp/year1_purchase_option.py
```

Both the `.py` and its already-converted `.ipynb` are committed side by side in each
`results/<use_case>/` folder. Regenerate the notebook after editing the `.py`:

```bash
jupytext --to notebook results/buyperp/year1_purchase_option.py
jupyter execute --inplace results/buyperp/year1_purchase_option.ipynb
```

## Data

`results/business/metals_prices.csv` / `results/buyperp/metals_prices.csv` (and the
matching `data/processed/metals_prices.parquet`):

| Column | Type | Meaning |
|---|---|---|
| `date` | date | Trading day (LME + ECB business day) |
| `cu_usd_per_tonne` | float | LME Copper Cash-Settlement, USD/tonne |
| `al_usd_per_tonne` | float | LME Aluminium Cash-Settlement, USD/tonne |
| `eur_usd_rate` | float | ECB reference rate, USD per 1 EUR |
| `cu_eur_per_tonne` | float | Copper price converted to EUR/tonne (`cu_usd_per_tonne / eur_usd_rate`) |
| `al_eur_per_tonne` | float | Aluminium price converted to EUR/tonne (`al_usd_per_tonne / eur_usd_rate`) |

Rows are an **inner join** on `date` across all sources — a date only appears if every
source published a value that day. See `REPORT.md` for the actual row count and date
range last observed.

`results/buyperp/sofr_rate.csv`:

| Column | Type | Meaning |
|---|---|---|
| `date` | date | Business day |
| `sofr_rate_pct` | float | Secured Overnight Financing Rate, in percent (e.g. `3.66` = 3.66%) |

## Development

```bash
pytest tests/
pre-commit run --all-files
```

Add a new mini-project by creating a new `src/<module>/`, a matching
`results/<use_case>/` directory (with both the `.py` and its converted `.ipynb`), and
`tests/test_<module>.py` — then update this README and `AGENTS.md`'s "Modules in This
Project" table in the same commit.

## Known Limitations

- westmetall.com, the ECB Data Portal, and FRED are all free but unofficial/best-effort
  sources (no SLA); if any changes its HTML/API shape, the scraper/parser will need
  updating.
- Only cash-settlement (spot) prices are collected, not the LME 3-month forward.
- `buyperp`'s Monte Carlo replay of the lattice's exercise policy shows a small
  (~0.4-0.5%), *stable* gap versus the closed-form lattice value — a known
  discrete-tree-vs-continuous-path discretization effect, not a bug (see `REPORT.md`).
- `buyperp`'s FX simulation is independent of the metal cost simulation (no modeled
  correlation between EUR/USD and copper/aluminium prices).
- `buyperp` currently only covers Year 1; the pricing function is written to be
  reusable for Year 2, Year 3, ... (new `S0`/`sigma`/`mu` each year from fresh data),
  but no multi-year chaining exists yet.

## Future Improvements

- Extend `buyperp` to Year 2+ once next year's market data exists.
- Model correlation between the EUR/USD path and the metal cost path in `buyperp`.

## References

- [westmetall.com market data](https://www.westmetall.com/en/markdaten.php) — free daily LME cash-settlement prices
- [ECB Data Portal](https://data-api.ecb.europa.eu/) — free daily EUR/USD reference rate
- [FRED (fredgraph.csv)](https://fred.stlouisfed.org/graph/fredgraph.csv) — free daily SOFR series, no API key
- See `AGENTS.md` for full project conventions.
