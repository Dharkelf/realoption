# REPORT.md — realoption

Documents actual observed runtime behaviour. Updated whenever the pipeline or a
mini-project's logic/output changes (see `AGENTS.md`, "Consistency Rule").

---

## `business` data pipeline — last run 2026-07-03

**Command:** `python main.py`

### Inputs / Parameters

- `metals.lookback_years`: 3 (rolling window ending on the run date)
- Sources: westmetall.com (`LME_Cu_cash`, `LME_Al_cash`), ECB Data Portal (`EXR/D.USD.EUR.SP00.A`)
- Requests made: 4 westmetall pages for copper (years 2023–2026) + 4 for aluminium + 1 ECB call = 9 HTTP requests total

### Data Collection

| Metric | Value |
|---|---|
| Row count (after inner join) | 757 |
| Date range | 2023-07-03 to 2026-07-02 |
| Missing values | 0 across all columns |

### Model Results (descriptive statistics)

| Column | mean | std | min | max |
|---|---|---|---|---|
| `cu_usd_per_tonne` | 9,914.01 | 1,637.31 | 7,812.50 | 14,097.00 |
| `al_usd_per_tonne` | 2,606.61 | 410.32 | 2,068.50 | 3,855.00 |
| `eur_usd_rate` | 1.1119 | 0.0451 | 1.0198 | 1.1974 |

Copper and aluminium prices both trend upward over the 3-year window; EUR/USD
stayed within a relatively narrow ~1.02–1.20 band.

### Validation

- Spot-checked the first/last 3 rows of `results/business/metals_prices.csv`
  against the raw westmetall/ECB pages for the corresponding dates — values match.
- `cu_eur_per_tonne` / `al_eur_per_tonne` verified by hand for one row:
  `9,875 USD / 1.10 USD-per-EUR ≈ 8,977 EUR` — consistent with the pipeline's output.
- All 8 unit/integration tests in `tests/` pass (`pytest tests/`); `ruff`, `ruff format
  --check`, and `mypy` all pass via `pre-commit run --all-files`.

### Known Issues

- None observed so far. westmetall's HTML repeats a header row once per month
  block within each year's table — handled in `westmetall.parse_year_table`, not
  a data quality issue but worth remembering if the site's markup changes.
- FRED's `fredgraph.csv` marks non-trading days with an empty value and some
  historical gaps with `"."` — both are dropped in `fred_rates.fetch_fred_series`,
  not treated as zero or forward-filled.

---

## `buyperp` Year 1 purchase-timing option — last run 2026-07-03

**Command:** `python results/buyperp/year1_purchase_option.py`

### Inputs / Parameters

- `CU_TONNES` / `AL_TONNES`: 100 / 100 tonnes
- `N_OPPORTUNITIES`: 12 (monthly month-end), `dt` = 1/12
- Estimated from 3 years of `results/buyperp/metals_prices.csv`:
  - `sigma` (basket cost, annualized): 18.4%
  - `mu` (basket cost, real-world annualized drift): 14.7%
  - `fx_sigma` / `fx_mu` (EUR/USD): 6.9% / 1.5%
- `r` (SOFR, latest observation): 3.66%
- `S0` (latest basket cost): 1,626,350 USD
- Monte Carlo: 10,000 simulations, seed 42 (paths) / 43 (Baseline C dates) / 142 (FX paths)

### Model Results

| Quantity | USD | EUR (execution-date FX) |
|---|---|---|
| Textbook risk-neutral cost (drift=r, sanity check) | 1,626,350 (== S0, by construction) | — |
| **Real-options cost (optimal timing, drift=mu)** | **1,641,389** | **1,444,736** |
| Baseline A — buy now | 1,626,350 | 1,426,748 |
| Baseline B — forced, year-end | 1,816,290 | 1,573,719 |
| Baseline C — random 3-of-12, 1/3 each | 1,727,639 | 1,507,221 |
| Option value vs. A (buy now) | -15,039 | -17,988 |
| Option value vs. B (forced year-end) | +174,901 | — |
| Option value vs. C (random) | +86,249 | — |

**Interpretation:** copper/aluminium prices have trended up strongly over the last 3
years (`mu` = 14.7% >> `r` = 3.66%), so on average the optimal-timing strategy is
*not* cheaper than simply buying immediately (option value vs. A is slightly
negative — buying now beats waiting when prices are expected to keep rising faster
than money grows risk-free). But the flexibility is clearly worth something
relative to being forced to wait until year-end (+174,901 USD) or to spreading
purchases out without any market view (+86,249 USD vs. random 3-of-12).

### Validation

- **Baseline A** (buy now): MC mean matches the closed form exactly, std = 0 —
  expected, since no randomness unfolds before an immediate purchase.
- **Baseline B** (forced, year-end): closed form 1,816,290 vs. MC mean 1,812,144
  (10,000 sims) — a difference of ~4,146 USD, about 1.2 Monte Carlo standard
  errors. Good agreement.
- **Real-options cost** (optimal timing): closed-form lattice value 1,641,389 vs.
  MC replay of the lattice's own exercise thresholds on continuous paths:
  1,649,324 (10,000 sims), a ~0.48% difference. Checked at 10k / 100k / 500k
  simulations — the gap stays essentially constant (~0.42% relative) while the
  Monte Carlo standard error shrinks roughly tenfold, confirming this is a
  **small, stable discretization effect** (the exercise threshold comes from a
  12-step discrete binomial tree, applied to continuously simulated paths that
  can take any intermediate value between month-ends), not sampling noise or a
  bug.
- `annualized_drift`/`annualized_volatility` cross-checked against a synthetic
  series with known parameters in `tests/test_bermudan_purchase.py`.
- All 29 tests in `tests/` pass (`pytest tests/`); `ruff`, `ruff format --check`,
  and `mypy` all pass via `pre-commit run --all-files`.

### Known Issues

- The real-world-drift construction means "option value vs. buying now" can be
  negative when the historical drift comfortably exceeds the risk-free rate —
  documented as an expected, economically meaningful result (not a bug) in
  `bermudan_purchase.py`'s module docstring and covered by
  `test_strong_upward_drift_can_make_immediate_purchase_cheaper_than_the_option`.
- EUR conversion uses execution-date FX simulation only where wired in (the core
  real-options cost, and Baselines B/C when their Monte Carlo toggles are on);
  with a toggle switched off, that baseline's EUR figure falls back to today's
  flat rate, clearly labeled as an approximation in the script's output.
