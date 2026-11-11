"""Decision uncertainty uses fitted draws and the same joint feasible objective."""

import numpy as np
import pytest
from itertools import product as combinations

from platform_app.tools.analysis import _confidence
from platform_app.tools.elasticity import estimate_elasticity
from platform_app.tools.optimization import objective_sample_scores, objective_scores
from platform_app.tools.selection import selection_uncertainty
from test_analysis import fixtures


@pytest.mark.parametrize("objective", ["balanced", "revenue", "margin"])
def test_sample_objective_expectation_preserves_business_objective(objective):
    draws = {"revenue": np.array([[100., 110.], [130., 90.]]),
             "gross_profit": np.array([[20., 40.], [60., 10.]])}
    assert objective_sample_scores(draws, objective).mean(axis=1) == pytest.approx(objective_scores(draws, objective))


def test_per_sample_optimizer_respects_family_ladder_and_fixed_siblings():
    first = {"sku": "small", "family_id": "family", "size": 1, "current_price": "9.00"}
    second = {"sku": "large", "family_id": "family", "size": 2, "current_price": "10.00"}
    prepared = [{"product": first, "prices": [9., 13.],
                 "sample_scores": np.array([[0., 0., 0., 0.], [100., 100., 100., 100.]])},
                {"product": second, "prices": [10., 12.],
                 "sample_scores": np.array([[3., 0., 3., 0.], [0., 3., 0., 3.]])}]
    result = selection_uncertainty(prepared, [first, second], {"small": 9., "large": 10.})
    assert result["small"]["lower"] == result["small"]["upper"] == 9.
    assert result["small"]["selected_price_probability"] == 1
    assert result["large"]["lower"] == 10 and result["large"]["upper"] == 12
    assert result["large"]["selected_price_probability"] == .5
    fixed = selection_uncertainty(prepared[:1], [first, second], {"small": 9.})
    assert fixed["small"]["lower"] == fixed["small"]["upper"] == 9


def test_wide_price_argmax_caps_confidence_without_replacing_price_or_hiding_sku():
    product, rows, _, competitor = fixtures()
    estimate = estimate_elasticity(product, rows)
    forecast = {"revenue": {"mean": 100., "variance": 1.}}
    base, _ = _confidence(estimate, forecast, [competitor], {"status": "passed"})
    selection = {"precision_cap": .65}
    capped, factors = _confidence(estimate, forecast, [competitor], {"status": "passed"}, selection=selection)
    assert base > .8 and capped == .65 and factors["base_score"] == base
    assert factors["selection_precision_cap"] == .65
    assert factors["confidence_model_version"] == "confidence-v2-selection"
    assert factors["calibrated"] is False


def test_selection_summary_is_deterministic_and_does_not_mutate_draws():
    product = {"sku": "one", "size": 1, "current_price": "10.00"}
    scores = np.array([[1., 3., 1., 3.], [3., 1., 3., 1.]])
    prepared = [{"product": product, "prices": [9., 11.], "sample_scores": scores}]
    first = selection_uncertainty(prepared, [product], {"one": 9.})
    assert first == selection_uncertainty(prepared, [product], {"one": 9.})
    assert np.array_equal(scores, np.array([[1., 3., 1., 3.], [3., 1., 3., 1.]]))
    assert first["one"]["precision_cap"] == pytest.approx(1 / (1 + 2 / 9))


def test_joint_sample_argmax_matches_independent_exhaustive_ladder_search():
    rng = np.random.default_rng(18)
    products = [{"sku": str(i), "family_id": "family", "size": i + 1,
                 "current_price": str(8 + i)} for i in range(3)]
    prices = [[8., 11.], [9., 12.], [10., 13.]]
    scores = [rng.normal(size=(2, 17)) for _ in products]
    prepared = [{"product": p, "prices": options, "sample_scores": values}
                for p, options, values in zip(products, prices, scores)]
    legal = [choice for choice in combinations(range(2), repeat=3)
             if prices[0][choice[0]] <= prices[1][choice[1]] <= prices[2][choice[2]]]
    best = [max(legal, key=lambda choice: sum(scores[i][choice[i], sample] for i in range(3)))
            for sample in range(17)]
    chosen = {p["sku"]: options[0] for p, options in zip(products, prices)}
    result = selection_uncertainty(prepared, products, chosen)
    for index, p in enumerate(products):
        independent = np.array([prices[index][choice[index]] for choice in best])
        interval = np.quantile(independent, [.025, .5, .975])
        assert [result[p["sku"]][key] for key in ("lower", "median", "upper")] == pytest.approx(interval)
        assert result[p["sku"]]["selected_price_probability"] == pytest.approx(np.mean(independent == prices[index][0]))
