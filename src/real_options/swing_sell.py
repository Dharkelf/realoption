"""Value the right to sell accumulated recycled material, repeatedly, at the
best of many monthly opportunities, under a storage-capacity constraint.

The business situation this models (see `results/sellperp/year1_sell_option.py`
for the concrete Cu/Al recycling case): every month a fixed quantity of
material accumulates (recycling output). At each month-end the holder decides
whether to sell EVERYTHING accumulated so far, or keep holding it in storage.
Storage has a capacity limit; if holding through another month's production
would exceed it, that month's excess production must be sold regardless of
price (a forced, partial sale — the accumulated pile itself is untouched).
Unlike `bermudan_purchase.py` (one purchase, once, per year), a sale here
resets accumulation to (near) zero and the process repeats — this can happen
several times within the same year, which is why it needs its own module
instead of reusing the single-exercise Bermudan pricer directly (though it
reuses that module's building blocks: `binomial_parameters`,
`annualized_volatility`/`annualized_drift`, `simulate_gbm_paths`).

Same "why real-world drift" reasoning as `bermudan_purchase.py` applies here
too — see that module's docstring. All money amounts are in whatever currency
`v0` is given in.

State representation: `n` = number of consecutive months of accumulated,
unsold production (1..max_cycle), where `max_cycle` is how many months' worth
of production fits in storage before the capacity constraint bites. Selling
resets `n` to 1 the following month (this month's fresh output); the excess
that must be force-sold at `n == max_cycle` is always exactly one month's
production, since production is constant per month.
"""

from __future__ import annotations

import math

import numpy as np

from src.real_options.bermudan_purchase import binomial_parameters


def _batch_value(v0: float, u: float, d: float, step: int, up_moves: int) -> float:
    """Value of one month's worth of production at lattice node (step, up_moves)."""
    return v0 * (u**up_moves) * (d ** (step - up_moves))


def price_swing_sell_option(
    v0: float, sigma: float, drift: float, r: float, n_months: int, max_cycle: int, dt: float
) -> float:
    """Backward-induction value of the optimal accumulate-or-sell strategy.

    `v0` is today's value of ONE month's production (e.g.
    `cu_qty_monthly * P_cu0 + al_qty_monthly * P_al0`). Since the material is
    a fungible commodity, selling `n` months' worth at time `t` is worth
    `n * price(t)` — today's price applies to the whole accumulated pile,
    regardless of when each part of it was produced.

    Unlike `bermudan_purchase.price_bermudan_purchase_option`, this does NOT
    reduce to a single price-independent number: at every (month, n) state we
    keep the full node-by-node value array (see `swing_sell_exercise_thresholds`
    for why a naive "value scales linearly with price, so the decision doesn't
    depend on price" shortcut is WRONG once a real threshold/kink exists).
    """
    root_value, _ = _swing_backward_induction(v0, sigma, drift, r, n_months, max_cycle, dt)
    return root_value


def swing_sell_exercise_thresholds(
    v0: float, sigma: float, drift: float, r: float, n_months: int, max_cycle: int, dt: float
) -> dict[tuple[int, int], float]:
    """The lattice's exercise boundary: `thresholds[(step, n)]` is the LOWEST
    price at which it's optimal to sell in state `n` at that step (sell if
    price >= threshold; keep accumulating otherwise) — the mirror image of
    `bermudan_purchase.bermudan_exercise_thresholds` (there: buy if price is
    low enough; here: sell if price is high enough). `math.inf` means "never
    sell voluntarily at this step in this state" (only ever relevant at
    n == max_cycle, where a forced partial sale happens regardless).

    Perhaps-surprising fact, provable from the recursion (and checked in
    `tests/test_swing_sell.py`): the threshold at a given step turns out to
    be the SAME for every `n`. Intuitively, selling always resets to the same
    state (n=1 next month) regardless of how much was accumulated, which
    makes the value function affine in `n` — and the "sell vs. hold"
    comparison, being linear in `n` on both sides, ends up independent of it.
    The `n` index is kept in the return type anyway for interface uniformity
    (and in case a future rule change reintroduces genuine n-dependence).
    """
    _, thresholds = _swing_backward_induction(v0, sigma, drift, r, n_months, max_cycle, dt)
    return thresholds


def _swing_backward_induction(
    v0: float, sigma: float, drift: float, r: float, n_months: int, max_cycle: int, dt: float
) -> tuple[float, dict[tuple[int, int], float]]:
    u, d, p = binomial_parameters(sigma, drift, dt)
    discount = math.exp(-r * dt)
    thresholds: dict[tuple[int, int], float] = {}

    # Terminal month: no sale is forced (per the business rule), but holding
    # vs. selling are worth exactly the same then — there's no more future
    # optionality left, so any remaining pile is marked to market at the
    # terminal price. This makes the terminal condition simple and uniform
    # across every inventory state `n`.
    value = {
        n: [n * _batch_value(v0, u, d, n_months, j) for j in range(n_months + 1)]
        for n in range(1, max_cycle + 1)
    }

    for step in range(n_months - 1, 0, -1):
        new_value: dict[int, list[float]] = {}
        for n in range(1, max_cycle + 1):
            node_values = []
            exercising_prices = []
            for j in range(step + 1):
                price_now = _batch_value(v0, u, d, step, j)
                # Selling now: cash in hand for the whole pile, plus next
                # month's fresh single-month accumulation (n resets to 1).
                continuation_after_sale = discount * (p * value[1][j + 1] + (1 - p) * value[1][j])
                sell_value = n * price_now + continuation_after_sale

                if n < max_cycle:
                    continuation_hold = discount * (p * value[n + 1][j + 1] + (1 - p) * value[n + 1][j])
                    node_value = max(sell_value, continuation_hold)
                    exercised = sell_value >= continuation_hold
                else:
                    # At capacity: the coming month's production is forced to
                    # sell regardless (only that one month's worth — the
                    # capped pile itself stays put), unless the holder instead
                    # chooses to voluntarily liquidate the whole pile now.
                    capped = value[max_cycle]
                    continuation_stay_at_cap = discount * (p * capped[j + 1] + (1 - p) * capped[j])
                    forced_partial_value = 1 * price_now + continuation_stay_at_cap
                    node_value = max(sell_value, forced_partial_value)
                    exercised = sell_value >= forced_partial_value

                node_values.append(node_value)
                if exercised:
                    exercising_prices.append(price_now)

            new_value[n] = node_values
            # Selling revenue rises with price while continuing to accumulate
            # does not rise as fast — so (unlike the buy-side lattice) the
            # exercise region is at HIGH prices: sell once price clears this
            # (lowest exercising) threshold.
            thresholds[(step, n)] = min(exercising_prices) if exercising_prices else math.inf
        value = new_value

    # Step 0 (today) isn't itself a decision point — month 1's production
    # hasn't happened yet — so the root is just the discounted continuation
    # into month 1's guaranteed starting state (n=1).
    root_value = discount * (p * value[1][1] + (1 - p) * value[1][0])
    return root_value, thresholds


def baseline_sell_immediately_revenue(v0: float, drift: float, r: float, n_months: int, dt: float) -> float:
    """Revenue from selling each month's production as soon as it's made —
    no accumulation, no storage, no timing decision at all.

    Closed form: under the real-world drift `drift`, the expected value of
    one month's production at month `t` is `v0 * exp(drift * t * dt)` (the
    same expected-growth identity `binomial_parameters` is built to enforce),
    discounted back to today at `r`.
    """
    return sum(v0 * math.exp(drift * t * dt) * math.exp(-r * t * dt) for t in range(1, n_months + 1))


def baseline_wait_for_capacity_revenue(
    v0: float, drift: float, r: float, n_months: int, max_cycle: int, dt: float
) -> float:
    """Revenue from a simple, non-adaptive policy: never sell voluntarily;
    once storage would be full (every `max_cycle` months), sell the ENTIRE
    accumulated pile — not just the excess — then start accumulating again.
    Any partial cycle still held at year-end is marked to market.

    This is deliberately simpler than the real business rule used by
    `price_swing_sell_option` (which force-sells only the excess once
    capacity is hit): it's a comparison baseline representing "wait as long
    as possible with no market view", not the actual physical constraint.
    """
    revenue = 0.0
    months_elapsed = 0
    while months_elapsed + max_cycle <= n_months:
        months_elapsed += max_cycle
        revenue += max_cycle * v0 * math.exp(drift * months_elapsed * dt) * math.exp(-r * months_elapsed * dt)

    remaining_cycles = n_months - months_elapsed
    if remaining_cycles > 0:
        revenue += remaining_cycles * v0 * math.exp(drift * n_months * dt) * math.exp(-r * n_months * dt)

    return revenue


def simulate_random_cycle_baseline(
    cost_paths: np.ndarray,
    r: float,
    dt: float,
    n_months: int,
    max_cycle: int,
    seed: int,
    fx_paths: np.ndarray | None = None,
) -> dict[str, float]:
    """A "no market-timing skill" baseline: repeatedly draw a random holding
    period (1..max_cycle months, uniform, independent of price), sell
    everything accumulated when it elapses, and start over — for the rest of
    the year. Any partial cycle still held at year-end is marked to market at
    that path's own terminal price (and FX rate, if `fx_paths` is given).
    """
    rng = np.random.default_rng(seed)
    n_simulations = cost_paths.shape[0]

    usd_revenue = np.empty(n_simulations)
    eur_revenue = np.empty(n_simulations)
    for i in range(n_simulations):
        month = 0
        total_usd = 0.0
        total_eur = 0.0
        while month < n_months:
            cycle_length = int(rng.integers(1, max_cycle + 1))
            sale_month = min(month + cycle_length, n_months)
            cycles_held = sale_month - month
            discount_factor = math.exp(-r * dt * sale_month)
            price_at_sale = cost_paths[i, sale_month]
            total_usd += cycles_held * price_at_sale * discount_factor
            if fx_paths is not None:
                total_eur += cycles_held * (price_at_sale / fx_paths[i, sale_month]) * discount_factor
            month = sale_month
        usd_revenue[i] = total_usd
        eur_revenue[i] = total_eur

    result = {"mean": float(usd_revenue.mean()), "std": float(usd_revenue.std(ddof=1))}
    if fx_paths is not None:
        result["mean_eur"] = float(eur_revenue.mean())
        result["std_eur"] = float(eur_revenue.std(ddof=1))
    return result


def verify_baselines_via_monte_carlo(
    cost_paths: np.ndarray,
    drift: float,
    r: float,
    dt: float,
    n_months: int,
    max_cycle: int,
    fx_paths: np.ndarray | None = None,
) -> dict[str, float]:
    """Independently re-derive Baselines A (sell immediately) and B (wait for
    capacity) by averaging over simulated price paths, as a sanity check on
    the closed forms — and, if `fx_paths` is given, their EUR present value
    converted using the EUR/USD rate on each path's own execution date(s).
    """
    n_simulations = cost_paths.shape[0]

    immediate_usd = np.zeros(n_simulations)
    immediate_eur = np.zeros(n_simulations)
    for t in range(1, n_months + 1):
        discount_factor = math.exp(-r * dt * t)
        immediate_usd += cost_paths[:, t] * discount_factor
        if fx_paths is not None:
            immediate_eur += (cost_paths[:, t] / fx_paths[:, t]) * discount_factor

    capacity_usd = np.zeros(n_simulations)
    capacity_eur = np.zeros(n_simulations)
    months_elapsed = 0
    while months_elapsed + max_cycle <= n_months:
        months_elapsed += max_cycle
        discount_factor = math.exp(-r * dt * months_elapsed)
        price_at_sale = cost_paths[:, months_elapsed]
        capacity_usd += max_cycle * price_at_sale * discount_factor
        if fx_paths is not None:
            capacity_eur += max_cycle * (price_at_sale / fx_paths[:, months_elapsed]) * discount_factor
    remaining_cycles = n_months - months_elapsed
    if remaining_cycles > 0:
        discount_factor = math.exp(-r * dt * n_months)
        price_at_year_end = cost_paths[:, n_months]
        capacity_usd += remaining_cycles * price_at_year_end * discount_factor
        if fx_paths is not None:
            capacity_eur += remaining_cycles * (price_at_year_end / fx_paths[:, n_months]) * discount_factor

    result = {
        "immediate_mean": float(immediate_usd.mean()),
        "immediate_std": float(immediate_usd.std(ddof=1)),
        "capacity_mean": float(capacity_usd.mean()),
        "capacity_std": float(capacity_usd.std(ddof=1)),
    }
    if fx_paths is not None:
        result["immediate_mean_eur"] = float(immediate_eur.mean())
        result["immediate_std_eur"] = float(immediate_eur.std(ddof=1))
        result["capacity_mean_eur"] = float(capacity_eur.mean())
        result["capacity_std_eur"] = float(capacity_eur.std(ddof=1))
    return result


def simulate_swing_sell_adaptive_baseline(
    cost_paths: np.ndarray,
    thresholds: dict[tuple[int, int], float],
    r: float,
    dt: float,
    n_months: int,
    max_cycle: int,
    fx_paths: np.ndarray | None = None,
) -> dict[str, float]:
    """Replay the lattice's own exercise thresholds against continuously
    simulated price paths — an independent, path-based cross-check on
    `price_swing_sell_option`'s closed-form (binomial) value, and, if
    `fx_paths` is given, the strategy's EUR present value using the FX rate
    prevailing at EACH of the (possibly several) sale dates on that path.

    A small, stable gap versus the closed-form lattice value is expected here
    too — same discrete-tree-vs-continuous-path discretization effect
    documented for `bermudan_purchase.simulate_adaptive_purchase_baseline`.
    """
    n_simulations = cost_paths.shape[0]
    usd_revenue = np.zeros(n_simulations)
    eur_revenue = np.zeros(n_simulations)
    sale_counts = np.zeros(n_simulations)

    for i in range(n_simulations):
        n = 0  # months accumulated so far; becomes 1 once month 1's output exists
        total_usd = 0.0
        total_eur = 0.0
        sales = 0
        for month in range(1, n_months + 1):
            n += 1  # this month's production has just been added
            price_now = cost_paths[i, month]

            if month == n_months:
                # Terminal month: no forced sale, but holding is marked to
                # market — numerically identical to "selling" here, so no
                # decision is needed.
                total_usd += n * price_now * math.exp(-r * dt * month)
                if fx_paths is not None:
                    total_eur += n * (price_now / fx_paths[i, month]) * math.exp(-r * dt * month)
                break

            threshold = thresholds.get((month, min(n, max_cycle)), math.inf)
            voluntary_sale = price_now >= threshold
            forced_partial_sale = n > max_cycle  # this month's output overflowed capacity

            if voluntary_sale:
                total_usd += n * price_now * math.exp(-r * dt * month)
                if fx_paths is not None:
                    total_eur += n * (price_now / fx_paths[i, month]) * math.exp(-r * dt * month)
                sales += 1
                n = 0
            elif forced_partial_sale:
                total_usd += 1 * price_now * math.exp(-r * dt * month)
                if fx_paths is not None:
                    total_eur += 1 * (price_now / fx_paths[i, month]) * math.exp(-r * dt * month)
                sales += 1
                n = max_cycle

        usd_revenue[i] = total_usd
        eur_revenue[i] = total_eur
        sale_counts[i] = sales

    result = {
        "mean": float(usd_revenue.mean()),
        "std": float(usd_revenue.std(ddof=1)),
        "mean_num_sales": float(sale_counts.mean()),
    }
    if fx_paths is not None:
        result["mean_eur"] = float(eur_revenue.mean())
        result["std_eur"] = float(eur_revenue.std(ddof=1))
    return result
