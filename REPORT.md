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
