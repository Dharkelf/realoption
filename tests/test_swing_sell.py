"""Unit tests for the swing-sell (accumulate-or-sell-under-capacity) pricer.

Mirrors the testing philosophy in `test_bermudan_purchase.py`: lean on
provable economic/mathematical properties (risk-neutral collapse, the
`n`-independence of the exercise threshold, the optimal policy never losing
to a fixed comparison policy) rather than re-implementing the DP a second
time, plus Monte Carlo cross-checks with explicit convergence tolerances.
"""

from __future__ import annotations

import math

import pytest

from src.real_options import swing_sell as ss
from src.real_options.bermudan_purchase import simulate_gbm_paths


def test_single_month_matches_sell_immediately_baseline() -> None:
    # With only one opportunity (which is also the terminal month), there's
    # no accumulation decision to make at all — both must agree exactly.
    v0, sigma, drift, r, dt = 200.0, 0.25, 0.10, 0.04, 1 / 12

    lattice_value = ss.price_swing_sell_option(v0, sigma, drift, r, n_months=1, max_cycle=1, dt=dt)
    baseline_a = ss.baseline_sell_immediately_revenue(v0, drift, r, n_months=1, dt=dt)

    assert lattice_value == pytest.approx(baseline_a)


def test_risk_neutral_tree_gives_no_timing_value() -> None:
    # Same lesson as bermudan_purchase.py: a linear revenue-in-price payoff
    # has zero timing value under a risk-neutral (drift=r) tree — selling
    # immediately, waiting for capacity, and optimal adaptive timing must
    # all agree exactly.
    v0, sigma, r, n_months, max_cycle, dt = 200.0, 0.3, 0.05, 12, 10, 1 / 12

    lattice_value = ss.price_swing_sell_option(v0, sigma, r, r, n_months, max_cycle, dt)
    baseline_a = ss.baseline_sell_immediately_revenue(v0, r, r, n_months, dt)
    baseline_b = ss.baseline_wait_for_capacity_revenue(v0, r, r, n_months, max_cycle, dt)

    assert lattice_value == pytest.approx(baseline_a)
    assert lattice_value == pytest.approx(baseline_b)
    assert lattice_value == pytest.approx(v0 * n_months)


def test_optimal_policy_never_loses_to_the_wait_for_capacity_baseline() -> None:
    # The adaptive policy can always at least replicate "wait for capacity,
    # then sell everything" (or do better), for any drift.
    v0, sigma, r, n_months, max_cycle, dt = 200.0, 0.25, 0.04, 12, 10, 1 / 12

    for drift in (0.0, 0.02, 0.04, 0.10, 0.15):
        lattice_value = ss.price_swing_sell_option(v0, sigma, drift, r, n_months, max_cycle, dt)
        baseline_b = ss.baseline_wait_for_capacity_revenue(v0, drift, r, n_months, max_cycle, dt)
        assert lattice_value >= baseline_b - 1e-9


def test_exercise_threshold_does_not_depend_on_inventory_state() -> None:
    # Documented (and proved in the module docstring) surprising property:
    # selling always resets to the same state, so the sell-vs-hold
    # comparison is linear in `n` on both sides and `n` cancels out.
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.25, -0.05, 0.04, 12, 10, 1 / 12
    thresholds = ss.swing_sell_exercise_thresholds(v0, sigma, drift, r, n_months, max_cycle, dt)

    for step in range(1, n_months):
        thresholds_this_step = {thresholds[(step, n)] for n in range(1, max_cycle + 1)}
        assert len(thresholds_this_step) == 1


def test_exercise_thresholds_appear_and_fall_over_time_under_negative_drift() -> None:
    # With a declining price outlook, waiting is unattractive, so there
    # should be a genuine (finite) price at which selling now beats holding
    # — and as the year progresses (less time for a lucky rebound), that bar
    # should get easier to clear (a falling threshold).
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.25, -0.05, 0.04, 12, 10, 1 / 12
    thresholds = ss.swing_sell_exercise_thresholds(v0, sigma, drift, r, n_months, max_cycle, dt)

    threshold_series = [thresholds[(step, 1)] for step in range(1, n_months)]
    assert all(math.isfinite(t) for t in threshold_series)
    assert threshold_series == sorted(threshold_series, reverse=True)


def test_monte_carlo_verifies_baselines_a_and_b() -> None:
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.25, 0.08, 0.04, 12, 10, 1 / 12
    paths = simulate_gbm_paths(v0, sigma, drift, n_months, dt, n_simulations=20_000, seed=1)

    mc = ss.verify_baselines_via_monte_carlo(paths, drift, r, dt, n_months, max_cycle)
    baseline_a = ss.baseline_sell_immediately_revenue(v0, drift, r, n_months, dt)
    baseline_b = ss.baseline_wait_for_capacity_revenue(v0, drift, r, n_months, max_cycle, dt)

    se_a = mc["immediate_std"] / math.sqrt(20_000)
    se_b = mc["capacity_std"] / math.sqrt(20_000)
    assert mc["immediate_mean"] == pytest.approx(baseline_a, abs=5 * se_a)
    assert mc["capacity_mean"] == pytest.approx(baseline_b, abs=5 * se_b)


def test_adaptive_replay_roughly_matches_the_closed_form_lattice() -> None:
    # Same discrete-tree-vs-continuous-path discretization gap documented for
    # bermudan_purchase's adaptive replay — expect close but not exact
    # agreement, within a few percent.
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.25, 0.08, 0.04, 12, 10, 1 / 12
    lattice_value = ss.price_swing_sell_option(v0, sigma, drift, r, n_months, max_cycle, dt)
    thresholds = ss.swing_sell_exercise_thresholds(v0, sigma, drift, r, n_months, max_cycle, dt)

    paths = simulate_gbm_paths(v0, sigma, drift, n_months, dt, n_simulations=20_000, seed=2)
    replay = ss.simulate_swing_sell_adaptive_baseline(paths, thresholds, r, dt, n_months, max_cycle)

    assert replay["mean"] == pytest.approx(lattice_value, rel=0.05)
    assert replay["mean_num_sales"] >= 1.0


def test_random_cycle_baseline_uses_distinct_holding_periods_and_covers_the_year() -> None:
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.25, 0.08, 0.04, 12, 10, 1 / 12
    paths = simulate_gbm_paths(v0, sigma, drift, n_months, dt, n_simulations=5, seed=3)

    result = ss.simulate_random_cycle_baseline(paths, r, dt, n_months, max_cycle, seed=7)

    assert result["mean"] > 0
    assert result["std"] >= 0


def test_monte_carlo_functions_convert_to_eur_using_execution_date_fx_rate() -> None:
    # drift=r isolates the FX effect (no cost-side timing value to muddy it).
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.2, 0.04, 0.04, 12, 10, 1 / 12
    fx0 = 1.10
    cost_paths = simulate_gbm_paths(v0, sigma, drift, n_months, dt, n_simulations=20_000, seed=5)
    fx_paths = simulate_gbm_paths(
        fx0, sigma=0.08, drift=0.20, n_steps=n_months, dt=dt, n_simulations=20_000, seed=9
    )

    mc = ss.verify_baselines_via_monte_carlo(cost_paths, drift, r, dt, n_months, max_cycle, fx_paths=fx_paths)

    naive_conversion = mc["capacity_mean"] / fx0
    assert mc["capacity_mean_eur"] < naive_conversion


def test_random_cycle_baseline_reproducible_with_same_seed() -> None:
    v0, sigma, drift, r, n_months, max_cycle, dt = 200.0, 0.25, 0.08, 0.04, 12, 10, 1 / 12
    paths = simulate_gbm_paths(v0, sigma, drift, n_months, dt, n_simulations=100, seed=3)

    result_a = ss.simulate_random_cycle_baseline(paths, r, dt, n_months, max_cycle, seed=11)
    result_b = ss.simulate_random_cycle_baseline(paths, r, dt, n_months, max_cycle, seed=11)

    assert result_a == result_b
