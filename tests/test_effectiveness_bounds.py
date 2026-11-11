"""The evaluation-only continuous ceiling bounds independent dense price searches."""

import numpy as np
import pytest

from scripts.effectiveness_feasibility import continuous_bound
from test_analysis import fixtures


@pytest.mark.parametrize("elasticity", [-3., -1.06, -.5, -.06, .7])
@pytest.mark.parametrize("stock", [300, 700, 2000])
def test_continuous_revenue_ceiling_bounds_dense_feasible_search(elasticity, stock):
    product = fixtures()[0]
    truth = {"elasticity": elasticity, "baseline_demand": 50.}
    bound = continuous_bound(product, truth, stock, 1., 14)
    prices = np.linspace(8., 12., 10_001)
    demand = 50. * 14 * (prices / 10.) ** (elasticity + .06)
    exhaustive = prices * np.minimum(demand, stock)
    assert 8 <= bound["price"] <= 12
    assert bound["revenue"] >= float(exhaustive.max()) - 1e-7
    # A dense search also approaches the bound: it is an achieved continuous
    # maximum, not an arbitrarily inflated number that would obscure feasibility.
    assert bound["revenue"] - float(exhaustive.max()) < .5
