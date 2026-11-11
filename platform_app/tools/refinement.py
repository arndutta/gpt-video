"""Bounded, versioned numerical refinements; never consume evaluator ground truth."""

from dataclasses import replace
from scipy.stats import t


def refine_estimate(estimate, state: dict | None):
    if not state or state.get("observations", 0) < 3 or state.get("observed_days", 0) < 30:
        return estimate
    offset = max(-.5, min(.5, float(state.get("elasticity_offset", 0))))
    multiplier = max(.75, min(2., float(state.get("uncertainty_multiplier", 1))))
    standard_error = max(.01, estimate.standard_error * multiplier)
    width = float(t.ppf(.975, estimate.degrees_of_freedom)) * standard_error
    value = max(-5., min(-.05, estimate.estimate + offset))
    return replace(estimate, estimate=value, standard_error=standard_error,
                   lower=value - width, upper=value + width,
                   residual_sigma=max(.04, min(.7, estimate.residual_sigma * multiplier)))
