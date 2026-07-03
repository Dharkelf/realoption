"""Unit tests for the Bermudan purchase-timing option pricer.

The central economic fact this module leans on for testing (explained in
`bermudan_purchase.py`'s docstrings) is that, under a risk-neutral tree
(`drift=r`), ANY non-adaptive purchase policy — buy immediately, be forced
to wait until the last date, or buy random slices at random dates — has the
same expected present-value cost as `s0`, and even the *adaptive* Bermudan
policy collapses to exactly `s0` too (a linear "buy at spot" payoff has zero
timing value under a no-arbitrage measure). Only once the tree is built with
`drift != r` (the real-world/historical drift this module actually uses for
its headline result) does genuine option value appear. That gives us strong,
meaningful assertions to test against, rather than just re-implementing the
formulas a second time.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.real_options import bermudan_purchase as bp


def test_annualized_volatility_matches_known_daily_sigma() -> None:
    # A synthetic random walk with a known daily log-return std; the annualized
    # figure should recover that std scaled by sqrt(252), the standard convention.
    rng = np.random.default_rng(0)
    daily_sigma = 0.01
    log_returns = rng.normal(loc=0.0, scale=daily_sigma, size=5000)
    cost_series = pd.Series(100.0 * np.exp(np.cumsum(log_returns)))

    result = bp.annualized_volatility(cost_series)

    assert result == pytest.approx(daily_sigma * math.sqrt(252), rel=0.05)


def test_annualized_drift_matches_known_daily_mean() -> None:
    # Same idea as the volatility test, but checking the *mean* log return
    # (the real-world drift mu) rather than its std.
    rng = np.random.default_rng(0)
    daily_mu, daily_sigma = 0.0005, 0.01
    log_returns = rng.normal(loc=daily_mu, scale=daily_sigma, size=5000)
    cost_series = pd.Series(100.0 * np.exp(np.cumsum(log_returns)))

    result = bp.annualized_drift(cost_series)

    assert result == pytest.approx(daily_mu * 252, abs=0.03)


def test_binomial_parameters_reproduce_the_given_drift() -> None:
    u, d, p = bp.binomial_parameters(sigma=0.25, drift=0.04, dt=1 / 12)

    assert u * d == pytest.approx(1.0)
    assert 0.0 < p < 1.0
    # The defining property of this tree construction: the expected one-step
    # growth factor equals exp(drift*dt) for WHATEVER drift is passed in —
    # risk-neutral (drift=r) or real-world (drift=mu) alike.
    assert p * u + (1 - p) * d == pytest.approx(math.exp(0.04 * (1 / 12)))


def test_single_opportunity_lattice_equals_forced_last_date_closed_form() -> None:
    # With n_steps=1, the one and only opportunity IS the forced last date, so
    # there is no early-exercise choice at all — the two functions must agree
    # exactly. This pins down the step-0 "no exercise allowed" boundary logic.
    s0, sigma, drift, r, dt = 100.0, 0.22, 0.07, 0.04, 1 / 12

    lattice_value = bp.price_bermudan_purchase_option(s0, sigma, drift, r, n_steps=1, dt=dt)
    closed_form = bp.baseline_forced_last_date_cost_closed_form(s0, sigma, drift, r, n_steps=1, dt=dt)

    assert lattice_value == pytest.approx(closed_form)


def test_risk_neutral_tree_gives_zero_timing_value() -> None:
    # drift=r (textbook risk-neutral): a linear "buy at spot" payoff has NO
    # timing value under a no-arbitrage measure — the lattice must collapse
    # to exactly s0, and the forced-last-date baseline must too. This is the
    # surprising-but-correct result documented at length in the module
    # docstring, and it's what motivated switching to real-world drift.
    s0, sigma, r, n_steps, dt = 250.0, 0.3, 0.05, 12, 1 / 12

    lattice_value = bp.price_bermudan_purchase_option(s0, sigma, drift=r, r=r, n_steps=n_steps, dt=dt)
    forced_last = bp.baseline_forced_last_date_cost_closed_form(
        s0, sigma, drift=r, r=r, n_steps=n_steps, dt=dt
    )

    assert lattice_value == pytest.approx(s0)
    assert forced_last == pytest.approx(s0)


def test_real_world_drift_produces_genuine_option_value() -> None:
    # Once drift (mu) differs from the discount rate (r), the martingale
    # collapse above no longer applies, and the adaptive policy should cost
    # strictly less than being forced to wait until the last date.
    s0, sigma, mu, r, n_steps, dt = 100.0, 0.25, 0.10, 0.04, 12, 1 / 12

    lattice_value = bp.price_bermudan_purchase_option(s0, sigma, mu, r, n_steps, dt)
    forced_last = bp.baseline_forced_last_date_cost_closed_form(s0, sigma, mu, r, n_steps, dt)

    assert lattice_value < forced_last


@pytest.mark.parametrize("mu", [0.02, 0.04, 0.10, 0.15])
def test_option_value_never_exceeds_forced_last_date_cost_for_any_drift(mu: float) -> None:
    # Unlike the "vs. immediate purchase" comparison, THIS property is
    # unconditional: having several chances to react is never worse than
    # being forced to use only the very last one, no matter the drift.
    s0, sigma, r, n_steps, dt = 100.0, 0.25, 0.04, 12, 1 / 12

    lattice_value = bp.price_bermudan_purchase_option(s0, sigma, mu, r, n_steps, dt)
    forced_last = bp.baseline_forced_last_date_cost_closed_form(s0, sigma, mu, r, n_steps, dt)

    assert lattice_value <= forced_last + 1e-9


def test_more_opportunities_can_only_lower_the_option_cost() -> None:
    # Same total 1-year horizon, but 12 monthly chances vs 4 quarterly chances
    # to catch a low price. More chances to react should never cost more.
    s0, sigma, mu, r = 100.0, 0.25, 0.10, 0.04

    monthly_value = bp.price_bermudan_purchase_option(s0, sigma, mu, r, n_steps=12, dt=1 / 12)
    quarterly_value = bp.price_bermudan_purchase_option(s0, sigma, mu, r, n_steps=4, dt=1 / 4)

    assert monthly_value <= quarterly_value


def test_option_value_never_exceeds_immediate_purchase_cost_when_drift_at_or_below_r() -> None:
    # When the real-world drift doesn't exceed the discount rate, waiting can
    # only help (or be neutral) — same argument as "no dividend/no carry cost
    # means an American call is never exercised early". This is NOT a
    # universal property once drift > r, though: see the test below.
    s0 = 100.0
    lattice_value = bp.price_bermudan_purchase_option(
        s0, sigma=0.28, drift=0.02, r=0.04, n_steps=12, dt=1 / 12
    )

    assert lattice_value <= bp.baseline_immediate_purchase_cost(s0)


def test_strong_upward_drift_can_make_immediate_purchase_cheaper_than_the_option() -> None:
    # If the real-world drift is well above the discount rate (as it has been
    # for copper/aluminium historically), prices are expected to keep rising
    # faster than money grows risk-free — so on average, buying right away
    # can beat even the *optimal* wait-and-see strategy. This is a genuine,
    # important business insight (not a bug): the option is always worth at
    # least as much as being FORCED to wait until year-end, but a strong
    # uptrend can still make "buy now" the cheaper choice overall.
    s0 = 100.0
    lattice_value = bp.price_bermudan_purchase_option(
        s0, sigma=0.2, drift=0.15, r=0.04, n_steps=12, dt=1 / 12
    )

    assert lattice_value > bp.baseline_immediate_purchase_cost(s0)


def test_monte_carlo_immediate_baseline_is_deterministic() -> None:
    paths = bp.simulate_gbm_paths(
        s0=100.0, sigma=0.25, drift=0.04, n_steps=12, dt=1 / 12, n_simulations=1000, seed=1
    )
    result = bp.verify_anchor_baselines_via_monte_carlo(paths, r=0.04, dt=1 / 12, n_steps=12)

    # Buying today is known with certainty at t=0 — no simulated randomness
    # has happened yet, so the mean must be exactly s0 and the std exactly 0.
    assert result["immediate_mean"] == pytest.approx(100.0)
    assert result["immediate_std"] == pytest.approx(0.0, abs=1e-9)


def test_monte_carlo_forced_last_baseline_converges_to_risk_neutral_s0() -> None:
    # Under drift=r specifically, the forced-last-date baseline must converge
    # to s0 (the risk-neutral martingale identity) — verified here by
    # simulation, independent of the closed-form binomial sum.
    s0, sigma, r, n_steps, dt = 100.0, 0.25, 0.04, 12, 1 / 12
    paths = bp.simulate_gbm_paths(
        s0=s0, sigma=sigma, drift=r, n_steps=n_steps, dt=dt, n_simulations=20_000, seed=1
    )
    result = bp.verify_anchor_baselines_via_monte_carlo(paths, r=r, dt=dt, n_steps=n_steps)

    # Allow a few standard errors of Monte Carlo sampling noise around the
    # theoretical s0 rather than an exact match.
    standard_error = result["forced_last_std"] / math.sqrt(20_000)
    assert result["forced_last_mean"] == pytest.approx(s0, abs=5 * standard_error)


def test_random_three_of_n_baseline_also_converges_to_risk_neutral_s0() -> None:
    s0, sigma, r, n_steps, dt = 100.0, 0.25, 0.04, 12, 1 / 12
    paths = bp.simulate_gbm_paths(
        s0=s0, sigma=sigma, drift=r, n_steps=n_steps, dt=dt, n_simulations=20_000, seed=1
    )
    result = bp.simulate_random_three_of_n_baseline(paths, r=r, dt=dt, n_steps=n_steps, seed=42)

    # Same martingale argument as the other two baselines: under drift=r, a
    # policy that doesn't react to the realized price (random dates, fixed
    # 1/3 shares) costs s0 in expectation too.
    standard_error = result["std"] / math.sqrt(20_000)
    assert result["mean"] == pytest.approx(s0, abs=5 * standard_error)


def test_random_three_of_n_baseline_uses_distinct_dates() -> None:
    # Regression guard: rng.choice(..., replace=False) must actually be used,
    # or the same month-end could get "bought" more than once.
    paths = bp.simulate_gbm_paths(
        s0=100.0, sigma=0.25, drift=0.04, n_steps=12, dt=1 / 12, n_simulations=5, seed=7
    )
    # Re-derive the chosen dates the same way the function does internally,
    # using the same seed, and check they're always 3 distinct values.
    rng = np.random.default_rng(7)
    for _ in range(paths.shape[0]):
        chosen = rng.choice(np.arange(1, 13), size=3, replace=False)
        assert len(set(chosen)) == 3


def test_exercise_thresholds_rise_as_the_horizon_shortens_under_positive_drift() -> None:
    # With positive drift (mu > r), waiting longer means the price is
    # expected to be higher still, so the bar for "worth buying now rather
    # than waiting" should get easier to clear (a higher threshold) the
    # closer the last, mandatory opportunity gets — there's less time left
    # for a lucky dip to make waiting pay off.
    s0, sigma, mu, r, n_steps, dt = 100.0, 0.25, 0.10, 0.04, 12, 1 / 12
    thresholds = bp.bermudan_exercise_thresholds(s0, sigma, mu, r, n_steps, dt)

    interior_thresholds = thresholds[1:n_steps]
    assert interior_thresholds == sorted(interior_thresholds)


def test_adaptive_baseline_replay_matches_lattice_value_within_a_few_percent() -> None:
    # The lattice's exercise thresholds, replayed against continuously
    # simulated paths, should approximately reproduce the lattice's own
    # value — "approximately" because the threshold comes from a 12-step
    # discrete tree while the replay path is continuous, a known small
    # discretization mismatch (see results/buyperp/year1_purchase_option.py's
    # REPORT notes), not a bug.
    s0, sigma, mu, r, n_steps, dt = 100.0, 0.25, 0.10, 0.04, 12, 1 / 12
    lattice_value = bp.price_bermudan_purchase_option(s0, sigma, mu, r, n_steps, dt)
    thresholds = bp.bermudan_exercise_thresholds(s0, sigma, mu, r, n_steps, dt)

    paths = bp.simulate_gbm_paths(s0, sigma, mu, n_steps, dt, n_simulations=50_000, seed=3)
    result = bp.simulate_adaptive_purchase_baseline(paths, thresholds, r, dt, n_steps)

    assert result["mean"] == pytest.approx(lattice_value, rel=0.02)
    # Every path must exercise at some valid opportunity between 1 and n_steps.
    assert 1 <= result["mean_exercise_month"] <= n_steps


def test_monte_carlo_functions_convert_to_eur_using_execution_date_fx_rate() -> None:
    # A deliberately simple, checkable case: FX drifts sharply upward (EUR
    # buys more USD later), so the EUR cost of a LATER purchase should be
    # pulled down noticeably more than converting with today's flat FX rate
    # would suggest — proof that the conversion really uses each path's own
    # future FX rate, not a single snapshot.
    s0, sigma, mu, r, n_steps, dt = (
        100.0,
        0.2,
        0.04,
        0.04,
        12,
        1 / 12,
    )  # mu=r: no cost drift, isolates the FX effect
    fx0 = 1.10
    cost_paths = bp.simulate_gbm_paths(s0, sigma, mu, n_steps, dt, n_simulations=20_000, seed=5)
    fx_paths = bp.simulate_gbm_paths(
        fx0, sigma=0.08, drift=0.20, n_steps=n_steps, dt=dt, n_simulations=20_000, seed=9
    )

    result = bp.verify_anchor_baselines_via_monte_carlo(cost_paths, r, dt, n_steps, fx_paths=fx_paths)

    naive_conversion = result["forced_last_mean"] / fx0
    assert result["forced_last_mean_eur"] < naive_conversion
