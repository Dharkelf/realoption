"""Value the right to buy a fixed quantity of something ONCE, at the best of
several scheduled dates, instead of being forced to buy on a single fixed date.

The business situation this models (see `results/buyperp/year1_purchase_option.py`
for the concrete Cu/Al cable-input case): a company must acquire a fixed annual
quantity of a commodity, and gets `n` scheduled chances during the year (e.g.
month-end) to place that (one, full) purchase. If it never actively decides to
buy earlier, it is forced to buy at the last of the n dates. This is a
"Bermudan option" in derivatives terminology — American-style (early exercise
allowed) but only at a fixed, discrete set of dates rather than continuously —
except here the holder is *minimizing a cost* rather than maximizing a payoff,
so the backward-induction recursion uses `min()` instead of the usual `max()`.

Why a single "cost" process instead of separate copper/aluminium processes:
the purchase decision only cares about the *combined* cost at each date, so
building one recombining binomial tree on `cost(t) = cu_qty * P_cu(t) +
al_qty * P_al(t)` — with volatility estimated directly from that combined
series' own historical returns — captures the copper/aluminium correlation
for free, without needing a two-asset lattice. This mirrors the single-asset
lattice approach used for the Simplico gold mine in `local/DP_M7_L1.ipynb`.

**Why real-world drift, not risk-neutral, drives the tree probability:** a
first version of this module built the tree the "textbook derivatives" way —
`drift = r` (the risk-free rate), giving a risk-neutral, no-arbitrage tree.
That construction makes `p*u + (1-p)*d == exp(r*dt)` hold EXACTLY at every
single node, which means the discounted continuation value at every node is
always exactly equal to that node's own cost — so `min(cost, continuation)`
never picks "exercise early", and the option's value collapses to precisely
`s0` (zero timing value), no matter the volatility or number of opportunities.
This isn't a bug: it's the correct, unavoidable consequence of pricing a
purely LINEAR "buy the traded asset at spot" payoff under a no-arbitrage
measure — you can't create value by timing purchases of a fairly-priced
asset (that's what "fairly priced" means). The Simplico gold mine avoids this
because its payoff is NONLINEAR (a lease value floored at zero), not because
its tree is built differently.
A company buying physical cable inputs isn't trading a hedgeable derivative
for arbitrage-free resale, though — it's forming a view based on how these
commodities have actually, historically moved. So this module builds the
tree's probability `p` from the **real-world (historically estimated) drift
`mu`**, while still discounting continuation values at the risk-free rate `r`
— a standard simplification in practitioner real-options analysis (e.g.
Copeland & Antikarov) for decisions that can't be perfectly replicated/hedged
in a market. Whenever `mu != r`, the martingale collapse above no longer
holds, and genuine, meaningful timing value emerges.

All money amounts in this module are in whatever currency `s0` is given in —
the caller (the results script) decides USD vs EUR.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def annualized_volatility(cost_series: pd.Series, trading_days_per_year: int = 252) -> float:
    """Estimate sigma from a daily cost series' own historical log returns.

    We don't attempt to derive the basket's volatility analytically from the
    individual copper/aluminium volatilities and their correlation (the usual
    "portfolio variance" formula) — instead we just treat the combined cost
    series as if it were itself a traded asset and measure its own historical
    log-return volatility. This is simpler, and it captures the correlation
    automatically: if copper and aluminium move together, the combined
    series is more volatile than either alone would suggest in isolation;
    if they partially offset each other, it's less volatile. Annualizing
    assumes ~252 trading days/year, the standard convention.
    """
    log_prices = cost_series.apply(math.log)
    log_returns = log_prices.diff().dropna()
    daily_sigma = log_returns.std(ddof=1)
    return float(daily_sigma * math.sqrt(trading_days_per_year))


def annualized_drift(cost_series: pd.Series, trading_days_per_year: int = 252) -> float:
    """Estimate the real-world (physical) drift mu from the same historical
    log returns used for `annualized_volatility` — the *mean*, not the std.

    This is what makes the option pricing "real-world" rather than
    risk-neutral: `mu` reflects how the basket cost has actually tended to
    move historically, not a synthetic no-arbitrage assumption. See this
    module's docstring for why that distinction produces a meaningful option
    value instead of a mathematically-guaranteed zero.
    """
    log_prices = cost_series.apply(math.log)
    log_returns = log_prices.diff().dropna()
    daily_mu = log_returns.mean()
    return float(daily_mu * trading_days_per_year)


def binomial_parameters(sigma: float, drift: float, dt: float) -> tuple[float, float, float]:
    """Cox-Ross-Rubinstein up/down moves and up-probability for a given drift.

    `u` and `d` are chosen so the tree's volatility matches `sigma` over one
    step of length `dt` (same construction as the gold-price lattice in
    `local/DP_M7_L1.ipynb`), and `p` is whatever value makes the expected
    one-step growth factor equal `exp(drift*dt)`. Pass `drift=r` (the
    risk-free rate) for a textbook risk-neutral tree, or `drift=mu` (the
    historically estimated real-world drift) for the real-world tree this
    module actually uses for the headline option value — see the module
    docstring for why that choice matters.
    """
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    p = (math.exp(drift * dt) - d) / (u - d)
    return u, d, p


def _node_cost(s0: float, u: float, d: float, step: int, up_moves: int) -> float:
    """Cost at the lattice node reached after `up_moves` ups out of `step` moves."""
    return s0 * (u**up_moves) * (d ** (step - up_moves))


def price_bermudan_purchase_option(
    s0: float, sigma: float, drift: float, r: float, n_steps: int, dt: float
) -> float:
    """Backward-induction value of the optimal purchase-timing strategy.

    `n_steps` is the number of scheduled purchase opportunities (e.g. 12 for
    monthly), each `dt` years apart. Step 0 (today / contract inception) is
    deliberately NOT treated as a purchase opportunity — the first chance to
    buy is step 1, and the last (step `n_steps`) is a forced purchase, since
    the company must have bought by then. Getting this boundary right matters:
    if step 0 were allowed to "exercise", this function would silently
    collapse into the trivial "buy immediately" baseline instead of pricing
    genuine timing flexibility.

    `drift` drives the tree's up-probability (see `binomial_parameters`);
    `r` is always the discount rate for converting future cost into present
    value. Passing `drift=r` reproduces the risk-neutral, zero-timing-value
    result explained in this module's docstring; the results script instead
    passes `drift=mu` (the historically estimated real-world drift).
    """
    root_value, _ = _bermudan_backward_induction(s0, sigma, drift, r, n_steps, dt)
    return root_value


def bermudan_exercise_thresholds(
    s0: float, sigma: float, drift: float, r: float, n_steps: int, dt: float
) -> list[float]:
    """The lattice's exercise boundary: `thresholds[step]` is the highest cost
    at which it's still optimal to buy at that step (buy if the actual cost is
    at or below it; keep waiting otherwise). Index 0 and `n_steps` are unused
    placeholders (step 0 can't exercise; step `n_steps` always must).

    This lets the *same* decision rule the lattice derived be replayed against
    continuously simulated price paths (see `simulate_adaptive_purchase_baseline`),
    e.g. to convert each simulated path's cost into EUR using the FX rate
    prevailing on that path's own (data-driven) exercise date, rather than a
    single snapshot FX rate.
    """
    _, thresholds = _bermudan_backward_induction(s0, sigma, drift, r, n_steps, dt)
    return thresholds


def _bermudan_backward_induction(
    s0: float, sigma: float, drift: float, r: float, n_steps: int, dt: float
) -> tuple[float, list[float]]:
    u, d, p = binomial_parameters(sigma, drift, dt)
    discount = math.exp(-r * dt)

    # At the last opportunity, the purchase is mandatory: there's no "wait and
    # see" branch left, so the value at every node is simply that node's cost.
    values = [_node_cost(s0, u, d, n_steps, j) for j in range(n_steps + 1)]
    thresholds = [math.inf] * (n_steps + 1)

    # Walk backward through opportunities n_steps-1 down to 1. At each node,
    # the holder compares buying now (this node's cost) against the
    # discounted, probability-weighted value of waiting for the next
    # opportunity, and picks whichever is cheaper — exactly the same
    # backward-induction pattern as the lease-value lattice in
    # local/DP_M7_L1.ipynb, just with `min` instead of `max` because we're
    # minimizing a cost rather than maximizing a payoff. Costs are monotonic
    # in `j` (more up-moves = higher cost), so the boundary between "exercise"
    # and "wait" nodes at each step is a single threshold cost, not a scattered
    # set — we record the highest node cost at which exercise still wins.
    for step in range(n_steps - 1, 0, -1):
        node_costs = [_node_cost(s0, u, d, step, j) for j in range(step + 1)]
        continuations = [discount * (p * values[j + 1] + (1 - p) * values[j]) for j in range(step + 1)]
        values = [min(node_costs[j], continuations[j]) for j in range(step + 1)]

        exercising_costs = [node_costs[j] for j in range(step + 1) if node_costs[j] <= continuations[j]]
        thresholds[step] = max(exercising_costs) if exercising_costs else -math.inf

    # Step 0 has no exercise choice of its own (see docstring) — its value is
    # purely the discounted continuation value into step 1.
    root_value = discount * (p * values[1] + (1 - p) * values[0])
    return root_value, thresholds


def baseline_immediate_purchase_cost(s0: float) -> float:
    """Cost of buying the full quantity right now, with no flexibility at all."""
    return s0


def baseline_forced_last_date_cost_closed_form(
    s0: float, sigma: float, drift: float, r: float, n_steps: int, dt: float
) -> float:
    """Discounted expected cost of a policy that always waits until the very
    last opportunity, with no active timing decision in between.

    Computed by explicitly summing over the lattice's terminal (binomial)
    distribution rather than just asserting an answer, so this doubles as a
    numerical check on the lattice construction. Under `drift=r` (the
    risk-neutral tree), this MUST equal `s0` exactly — that's the martingale
    identity explained in this module's docstring, and a good sanity check
    that the tree is built correctly. Under `drift=mu != r` (the real-world
    tree actually used for the headline result), this will differ from `s0`
    — e.g. if the historical drift exceeds the risk-free rate, waiting is
    expected to cost MORE than buying today, which is an economically
    meaningful (not a bug) result.
    """
    u, d, p = binomial_parameters(sigma, drift, dt)
    discount = math.exp(-r * dt * n_steps)
    expected_terminal_cost = sum(
        math.comb(n_steps, j) * (p**j) * ((1 - p) ** (n_steps - j)) * _node_cost(s0, u, d, n_steps, j)
        for j in range(n_steps + 1)
    )
    return discount * expected_terminal_cost


def simulate_gbm_paths(
    s0: float, sigma: float, drift: float, n_steps: int, dt: float, n_simulations: int, seed: int
) -> np.ndarray:
    """Simulate `n_simulations` price paths under the given drift, as a
    continuous-time (geometric Brownian motion) counterpart to the discrete
    binomial lattice.

    Returned array has shape (n_simulations, n_steps + 1); column 0 is `s0`
    for every path (nothing has happened yet), column k is the simulated cost
    at opportunity k. This is the shared "raw material" for both Monte Carlo
    checks below — simulating it once and reusing it (rather than resimulating
    per baseline) is both faster and statistically sound ("common random
    numbers"), since all quantities being compared are functions of the same
    underlying price paths. Pass `drift=r` to reproduce the risk-neutral
    anchors, or `drift=mu` for the real-world-consistent baselines.
    """
    rng = np.random.default_rng(seed)
    random_shocks = rng.standard_normal(size=(n_simulations, n_steps))

    # GBM log-increment: the given drift, minus the usual Ito variance
    # correction so that the *arithmetic* expected growth rate matches `drift`.
    log_increments = (drift - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * random_shocks
    log_paths = np.cumsum(log_increments, axis=1)

    paths = s0 * np.exp(log_paths)
    s0_column = np.full((n_simulations, 1), s0)
    return np.hstack([s0_column, paths])


def verify_anchor_baselines_via_monte_carlo(
    paths: np.ndarray, r: float, dt: float, n_steps: int, fx_paths: np.ndarray | None = None
) -> dict[str, float]:
    """Independently re-derive the two closed-form anchor baselines by
    averaging over simulated price paths, as a sanity check on the formulas.

    The "immediate purchase" case has zero variance almost by definition (the
    cost is known and paid today, before any randomness unfolds) — showing
    that explicitly (mean == s0, std == 0) is itself a useful confirmation
    that the simulation setup is wired correctly, not just a formality.

    If `fx_paths` is given (same shape as `paths`, simulated separately from
    the metal cost — see `simulate_gbm_paths`), this also reports each
    baseline's EUR present value, converted using the EUR/USD rate on that
    SAME simulated path at its OWN execution date — not a single snapshot
    rate — which is the whole point of doing this via simulation rather than
    a flat division by today's rate.
    """
    immediate_costs = paths[:, 0]
    forced_last_costs = paths[:, n_steps] * math.exp(-r * dt * n_steps)
    result = {
        "immediate_mean": float(immediate_costs.mean()),
        "immediate_std": float(immediate_costs.std(ddof=1)),
        "forced_last_mean": float(forced_last_costs.mean()),
        "forced_last_std": float(forced_last_costs.std(ddof=1)),
    }
    if fx_paths is not None:
        immediate_eur = immediate_costs / fx_paths[:, 0]
        forced_last_eur = (paths[:, n_steps] / fx_paths[:, n_steps]) * math.exp(-r * dt * n_steps)
        result["immediate_mean_eur"] = float(immediate_eur.mean())
        result["immediate_std_eur"] = float(immediate_eur.std(ddof=1))
        result["forced_last_mean_eur"] = float(forced_last_eur.mean())
        result["forced_last_std_eur"] = float(forced_last_eur.std(ddof=1))
    return result


def simulate_random_three_of_n_baseline(
    paths: np.ndarray, r: float, dt: float, n_steps: int, seed: int, fx_paths: np.ndarray | None = None
) -> dict[str, float]:
    """A "no market-timing skill" baseline: buy exactly 1/3 of the quantity at
    each of 3 opportunities chosen uniformly at random (a different random
    triple per simulated path), instead of choosing the 3 (or fewer) dates
    deliberately.

    This uses its own `seed`, independent of the RNG that generated `paths`,
    so the "which dates get picked" randomness and the "what does the price
    do" randomness are two clearly separate sources — which is also why this
    is its own function rather than folded into `verify_anchor_baselines_...`:
    it answers a conceptually different question (what does *undisciplined*
    timing cost, not just what does *no* timing cost).

    If `fx_paths` is given, each of the 3 purchases is converted to EUR using
    the FX rate at ITS OWN date, not a single snapshot rate (see
    `verify_anchor_baselines_via_monte_carlo` for the same idea applied there).
    """
    rng = np.random.default_rng(seed)
    n_simulations = paths.shape[0]
    opportunity_steps = np.arange(1, n_steps + 1)

    usd_costs = np.empty(n_simulations)
    eur_costs = np.empty(n_simulations)
    for i in range(n_simulations):
        chosen_steps = rng.choice(opportunity_steps, size=3, replace=False)
        thirds_usd = paths[i, chosen_steps] / 3.0
        discount_factors = np.exp(-r * dt * chosen_steps)
        usd_costs[i] = (thirds_usd * discount_factors).sum()
        if fx_paths is not None:
            thirds_eur = thirds_usd / fx_paths[i, chosen_steps]
            eur_costs[i] = (thirds_eur * discount_factors).sum()

    result = {"mean": float(usd_costs.mean()), "std": float(usd_costs.std(ddof=1))}
    if fx_paths is not None:
        result["mean_eur"] = float(eur_costs.mean())
        result["std_eur"] = float(eur_costs.std(ddof=1))
    return result


def simulate_adaptive_purchase_baseline(
    cost_paths: np.ndarray,
    thresholds: list[float],
    r: float,
    dt: float,
    n_steps: int,
    fx_paths: np.ndarray | None = None,
) -> dict[str, float]:
    """Replay the lattice's own exercise thresholds (from
    `bermudan_exercise_thresholds`) against continuously simulated cost paths,
    to get an independent, path-based estimate of the real-options cost —
    and, if `fx_paths` is given, its EUR present value converted using the
    FX rate prevailing on each path's OWN (data-driven, possibly early)
    exercise date, rather than a single snapshot rate.

    For each path: walk forward through opportunities 1..n_steps-1, buying as
    soon as the simulated cost first drops to or below that step's threshold;
    if it never does, buy at the mandatory last opportunity `n_steps`.
    """
    n_simulations = cost_paths.shape[0]
    exercise_steps = np.full(n_simulations, n_steps)
    for step in range(1, n_steps):
        still_waiting = exercise_steps == n_steps
        triggered_now = still_waiting & (cost_paths[:, step] <= thresholds[step])
        exercise_steps[triggered_now] = step

    row_index = np.arange(n_simulations)
    usd_costs = cost_paths[row_index, exercise_steps] * np.exp(-r * dt * exercise_steps)

    result = {
        "mean": float(usd_costs.mean()),
        "std": float(usd_costs.std(ddof=1)),
        "mean_exercise_month": float(exercise_steps.mean()),
    }
    if fx_paths is not None:
        eur_costs = (cost_paths[row_index, exercise_steps] / fx_paths[row_index, exercise_steps]) * np.exp(
            -r * dt * exercise_steps
        )
        result["mean_eur"] = float(eur_costs.mean())
        result["std_eur"] = float(eur_costs.std(ddof=1))
    return result
