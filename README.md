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
- **`sellperp`**: values the flexibility to choose *when* to sell accumulated recycled
  copper/aluminium output under a storage-capacity constraint — a repeated, resetting
  cousin of `buyperp`'s single-decision problem.

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
        ┌─────────────────┼───────────┬──────────────────────┬─────────┐
        ▼                 ▼           ▼                      ▼         ▼
 data/raw/*.parquet  data/processed/  results/business/  results/buyperp/  results/sellperp/
 (one file per         metals_prices. metals_prices.csv  metals_prices.csv metals_prices.csv
  source, as scraped)  parquet        (no path needed)   + sofr_rate.csv   + sofr_rate.csv
                        (merged + EUR)                    (no path needed) (no path needed)
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

### `sellperp` use case — Year 1 sell-timing option under a storage cap

Every month, recycling produces a fixed quantity of copper+aluminium. Each month-end the
holder decides whether to sell EVERYTHING accumulated so far, or keep holding it — but
storage has a cap, and holding through another month's production once the cap is (near)
reached forces that month's *excess* to be sold regardless of price. Unlike `buyperp`
(exactly one purchase per year), a sale here can happen **several times** within the
year, resetting accumulation each time — so `src/real_options/swing_sell.py` adds an
extra state dimension (months of unsold accumulation) on top of `bermudan_purchase.py`'s
binomial tree, reusing that module's tree/GBM building blocks rather than duplicating them.

```
results/sellperp/metals_prices.csv, sofr_rate.csv
                 │
                 ▼
results/sellperp/year1_sell_option.py
                 │  (imports the reusable pricer)
                 ▼
       src/real_options/swing_sell.py ──uses──► src/real_options/bermudan_purchase.py
        │                    │                   (binomial_parameters, GBM paths,
        ▼                    ▼                    volatility/drift estimation)
 lattice (closed form,   Monte Carlo (paths +
 month × storage-cycle   thresholds; multiple
 × price node)           sales per path possible)
        │                    │
        └─────────┬──────────┘
                   ▼
 real-options revenue vs. 3 baselines (sell immediately / wait for storage to fill /
 random holding periods), each in USD and execution-date-converted EUR (summed across
 however many sales a given scenario produces in a year)
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
| `output.sofr_use_cases` / `sofr_csv_filename` | Use-case folders that get the SOFR CSV copy |
| `output.processed_filename` / `csv_filename` | Output file names |

`buyperp`'s and `sellperp`'s own business quantities (tonnes, storage caps, lookback
window, Monte Carlo sample size/seed) are NOT in `settings.yaml` — each
`results/<use_case>/*.py` script keeps its own at the top of the file, per AGENTS.md's
Result Format rules.

## Usage

Run the full data collection pipeline (fetch, merge, convert, save):

```bash
python main.py
```

This (re)creates:
- `data/raw/lme_copper_cash.parquet`, `lme_aluminium_cash.parquet`, `ecb_eurusd.parquet`, `fred_sofr.parquet`
- `data/processed/metals_prices.parquet`
- `results/business/metals_prices.csv`, `results/buyperp/metals_prices.csv`, `results/sellperp/metals_prices.csv`
  — columns: `date`, `cu_usd_per_tonne`, `al_usd_per_tonne`, `eur_usd_rate`, `cu_eur_per_tonne`, `al_eur_per_tonne`
- `results/buyperp/sofr_rate.csv`, `results/sellperp/sofr_rate.csv` — columns: `date`, `sofr_rate_pct`

Run a mini-project result standalone (from anywhere, thanks to the editable install):

```bash
python results/buyperp/year1_purchase_option.py
python results/sellperp/year1_sell_option.py
```

Both the `.py` and its already-converted `.ipynb` are committed side by side in each
`results/<use_case>/` folder. Regenerate the notebook after editing the `.py`:

```bash
jupytext --to notebook results/sellperp/year1_sell_option.py
jupyter execute --inplace results/sellperp/year1_sell_option.ipynb
```

## Data

`results/business/metals_prices.csv` / `results/buyperp/metals_prices.csv` /
`results/sellperp/metals_prices.csv` (and the matching
`data/processed/metals_prices.parquet`):

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

`results/buyperp/sofr_rate.csv` / `results/sellperp/sofr_rate.csv`:

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
- Both `buyperp`'s and `sellperp`'s Monte Carlo replay of the lattice's exercise policy
  shows a small, *stable* gap versus the closed-form lattice value — a known
  discrete-tree-vs-continuous-path discretization effect, not a bug (see `REPORT.md`).
- FX simulation is independent of the metal cost/batch-value simulation in both use
  cases (no modeled correlation between EUR/USD and copper/aluminium prices).
- Both `buyperp` and `sellperp` currently only cover Year 1; their pricing functions are
  written to be reusable for Year 2, Year 3, ... (new price/volatility/drift inputs each
  year from fresh data), but no multi-year chaining exists yet.
- `sellperp`'s actual storage rule (force-sell only the excess above capacity) differs
  deliberately from Baseline B's simplified rule (sell everything once storage would be
  full) — see `swing_sell.py`'s module docstring for why these are two different things.

## Future Improvements

- Extend `buyperp` and `sellperp` to Year 2+ once next year's market data exists.
- Model correlation between the EUR/USD path and the metal cost path in both use cases.

## References

- [westmetall.com market data](https://www.westmetall.com/en/markdaten.php) — free daily LME cash-settlement prices
- [ECB Data Portal](https://data-api.ecb.europa.eu/) — free daily EUR/USD reference rate
- [FRED (fredgraph.csv)](https://fred.stlouisfed.org/graph/fredgraph.csv) — free daily SOFR series, no API key
- See `AGENTS.md` for full project conventions.
