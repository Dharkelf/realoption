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

Year 1 runs January-December (`YEAR_1_MONTH_LABELS`); sigma/mu are estimated from a
configurable trailing window, `VOLATILITY_LOOKBACK_YEARS` (currently 1, can go up to 3 —
the limit of `results/buyperp/metals_prices.csv`'s history), not the full dataset.

### Inputs / Parameters

- `CU_TONNES` / `AL_TONNES`: 100 / 100 tonnes
- `N_OPPORTUNITIES`: 12 (monthly month-end), `dt` = 1/12
- `VOLATILITY_LOOKBACK_YEARS`: 1 (trailing window used for sigma/mu; `S0`/`fx0` always
  use the single latest observation regardless of this window)
- Estimated from the trailing 1 year of `results/buyperp/metals_prices.csv`:
  - `sigma` (basket cost, annualized): 19.5%
  - `mu` (basket cost, real-world annualized drift): 25.2%
  - `fx_sigma` / `fx_mu` (EUR/USD): 5.9% / -3.1%
- `r` (SOFR, latest observation): 3.66%
- `S0` (latest basket cost): 1,626,350 USD
- Monte Carlo: 10,000 simulations, seed 42 (paths) / 43 (Baseline C dates) / 142 (FX paths)

### Model Results

| Quantity | USD | EUR (execution-date FX) |
|---|---|---|
| Textbook risk-neutral cost (drift=r, sanity check) | 1,626,350 (== S0, by construction) | — |
| **Real-options cost (optimal timing, drift=mu)** | **1,655,738** | **1,477,910** |
| Baseline A — buy now | 1,626,350 | 1,426,748 |
| Baseline B — forced, year-end | 2,016,254 | 1,826,256 |
| Baseline C — random 3-of-12, 1/3 each | 1,831,029 | 1,637,720 |
| Option value vs. A (buy now) | -29,388 | -51,162 |
| Option value vs. B (forced year-end) | +360,516 | — |
| Option value vs. C (random) | +175,291 | — |

**Interpretation:** the trailing 1-year drift (`mu` = 25.2%) is even steeper than the
full 3-year figure (14.7%) — copper/aluminium have accelerated recently — so buying
immediately looks better still relative to optimal timing (option value vs. A more
negative than with the 3y window: -29,388 vs. the earlier -15,039 USD). The option's
value relative to being forced to wait until year-end grows accordingly (+360,516 USD,
up from +174,901), since a stronger uptrend makes "always wait" much more expensive
while optimal timing still limits the downside. This is a direct, transparent
consequence of the chosen lookback window, not a change in methodology — switching
`VOLATILITY_LOOKBACK_YEARS` back to 3 reproduces the earlier, less extreme figures.

### Validation

- **Baseline A** (buy now): MC mean matches the closed form exactly, std = 0 —
  expected, since no randomness unfolds before an immediate purchase.
- **Baseline B** (forced, year-end): closed form 2,016,254 vs. MC mean 2,011,407
  (10,000 sims) — a difference of ~4,847 USD, comfortably within Monte Carlo
  sampling noise.
- **Real-options cost** (optimal timing): closed-form lattice value 1,655,738 vs.
  MC replay of the lattice's own exercise thresholds on continuous paths: 1,676,861
  (10,000 sims), a ~1.3% difference. With the 3-year window this same comparison
  showed ~0.48%, stable across 10k-500k simulations (a known discrete-tree-vs
  -continuous-path discretization effect, not sampling noise or a bug) — the
  larger gap here is consistent with the higher mu/sigma of the shorter window
  making the discrete approximation coarser, not a new issue.
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
  With a 1-year lookback this effect is more pronounced than with 3 years, simply
  because the estimated drift is higher.
- EUR conversion uses execution-date FX simulation only where wired in (the core
  real-options cost, and Baselines B/C when their Monte Carlo toggles are on);
  with a toggle switched off, that baseline's EUR figure falls back to today's
  flat rate, clearly labeled as an approximation in the script's output.

---

## `sellperp` Year 1 sell-timing option — last run 2026-07-03

**Command:** `python results/sellperp/year1_sell_option.py`

Year 1 runs January-December, mirroring `buyperp`. Storage capacity translates to
`max_cycle` = 10 months of accumulation (`LAGER_CU=100t / CU_QTY_MONTHLY=10t`, same for
aluminium). sigma/mu use the same `VOLATILITY_LOOKBACK_YEARS=1` default as `buyperp`.

### Inputs / Parameters

- `CU_QTY_MONTHLY` / `AL_QTY_MONTHLY`: 10 / 10 tonnes; `LAGER_CU` / `LAGER_AL`: 100 / 100 tonnes
- `max_cycle` (storage capacity in months): 10; `N_MONTHS`: 12, `dt` = 1/12
- Estimated from the trailing 1 year of `results/sellperp/metals_prices.csv`:
  - `sigma` (one-month batch value, annualized): 19.5%
  - `mu` (one-month batch value, real-world annualized drift): 25.2%
- `r` (SOFR, latest observation): 3.66%
- `v0` (today's one-month batch value): 162,635 USD
- Monte Carlo: 10,000 simulations, seed 42 (paths) / 43 (Baseline C) / 142 (FX paths)

### Model Results

| Quantity | USD | EUR (execution-date FX) |
|---|---|---|
| Textbook risk-neutral value (drift=r, sanity check) | 1,951,620 (== Baseline A, by construction) | — |
| **Real-options revenue (optimal timing, drift=mu)** | **2,408,833** | **2,188,017** |
| Baseline A — sell immediately every month | 2,196,743 | — |
| Baseline B — wait for storage to fill, then sell all | 2,348,567 | — |
| Baseline C — random holding periods | 2,295,372 | 2,067,300 |
| Option value vs. A (sell immediately) | +212,089 | — |
| Option value vs. B (wait for capacity) | +60,266 | — |
| Option value vs. C (random) | +113,461 | — |

**Interpretation:** unlike `buyperp`, where a strong uptrend made *buying* immediately
attractive, here a strong uptrend (`mu`=25.2%) makes the optimal *selling* strategy
clearly better than every fixed comparison policy — waiting for a higher price pays off
on average when accumulating is cheap (only a capacity constraint, no cost of carry
modeled) and prices trend up. The optimal policy sells about once per year on average
(`mean_num_sales` ≈ 1.0): typically waiting through the full 10-month accumulation
window, taking the small forced partial sale at month 11, and marking the remaining
pile to market at year-end.

### Validation

- **Risk-neutral case** (drift=r): lattice value exactly equals Baseline A and Baseline
  B (`1,951,620` all three) — the same "linear payoff ⇒ zero timing value" identity as
  `bermudan_purchase.py`, now confirmed for a repeated/reset decision structure too.
- **Baseline A/B Monte Carlo**: closed form 2,196,743 (A) / 2,348,567 (B) vs. MC means
  2,196,808 / 2,346,059 (10,000 sims) — both comfortably within a couple of Monte Carlo
  standard errors.
- **Real-options revenue**: closed-form lattice 2,408,833 vs. MC replay of the lattice's
  own exercise thresholds on continuous paths: 2,410,376 (10,000 sims, 0.06%). Checked at
  10k/100k/500k simulations: the gap stabilizes around ~0.34%, the same
  discrete-tree-vs-continuous-path discretization effect documented for `buyperp`, not a
  bug — here it's smaller because the optimal policy sells only ~once per year, giving
  fewer discrete decision points for the approximation to compound over.
- **Threshold `n`-independence**: proved analytically in `swing_sell.py`'s docstring
  (selling always resets to the same state, making the value function affine in `n`)
  and checked in `tests/test_swing_sell.py`.
- All 39 tests in `tests/` pass (`pytest tests/`); `ruff`, `ruff format --check`, and
  `mypy` all pass via `pre-commit run --all-files`.

### Known Issues

- Baseline B's "sell everything once storage is full" rule is intentionally simpler
  than the real business rule used by the optimal policy (force-sell only the excess) —
  see `swing_sell.py`'s module docstring. They answer different questions and are not
  meant to coincide.
- `simulate_swing_sell_adaptive_baseline`'s per-path loop is O(n_simulations × n_months)
  in Python (no vectorization across months, since each month's decision depends on the
  running inventory state) — fine at 10,000-500,000 simulations here, but would need
  vectorizing further if `n_simulations` grew by another order of magnitude or more.
