"""Inspectable log-linear elasticity estimation from aggregate SKU history."""

from dataclasses import asdict, dataclass
from datetime import date
import math

import numpy as np
from scipy.stats import t


@dataclass(frozen=True)
class ElasticityEstimate:
    estimate: float
    lower: float
    upper: float
    sample_size: int
    standard_error: float
    degrees_of_freedom: int
    daily_demand: float
    residual_sigma: float
    r_squared: float
    excluded_observations: int

    def public(self) -> dict:
        result = asdict(self)
        result["confidence_level"] = 0.95
        result["method"] = "log-linear OLS with promotion/seasonal/weekly controls"
        return result


class InsufficientHistory(ValueError):
    """The observations do not identify a defensible price-response estimate."""


def estimate_elasticity(product: dict, sales: list[dict]) -> ElasticityEstimate:
    rows = []
    for observation in sales:
        try:
            price, units = float(observation["price"]), float(observation["units"])
            seasonal = float(observation.get("seasonal_index", 1))
            day = date.fromisoformat(str(observation["date"])[:10])
            if price <= 0 or units <= 0 or seasonal <= 0:
                continue
            values = (price, units, seasonal)
            if not all(math.isfinite(value) for value in values):
                continue
            rows.append((day, price, units, seasonal, bool(observation.get("promotion", False))))
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda row: row[0])
    if len(rows) < 30 or len({round(row[1], 4) for row in rows}) < 4:
        raise InsufficientHistory("At least 30 positive-sales observations and four distinct prices are required.")
    log_prices = np.log([row[1] for row in rows])
    if np.std(log_prices) < 0.015:
        raise InsufficientHistory("Observed price variation is too small to identify elasticity.")
    columns = [np.ones(len(rows)), log_prices]
    candidate_controls = [
        np.array([float(row[4]) for row in rows]),
        np.log([row[3] for row in rows]),
        np.sin([2 * np.pi * row[0].weekday() / 7 for row in rows]),
        np.cos([2 * np.pi * row[0].weekday() / 7 for row in rows]),
    ]
    control_indices = []
    for index, column in enumerate(candidate_controls):
        if np.std(column) <= 1e-8:
            continue
        proposed = np.column_stack([*columns, column])
        if np.linalg.matrix_rank(proposed) == proposed.shape[1]:
            columns.append(column)
            control_indices.append(index)
    matrix = np.column_stack(columns)
    if np.linalg.cond(matrix) > 1e8:
        raise InsufficientHistory("Price and contextual features are too collinear for a stable estimate.")
    target = np.log([row[2] for row in rows])
    coefficients, _, _, _ = np.linalg.lstsq(matrix, target, rcond=None)
    residuals = target - matrix @ coefficients
    degrees = len(rows) - matrix.shape[1]
    residual_variance = float(residuals @ residuals / degrees)
    covariance = residual_variance * np.linalg.inv(matrix.T @ matrix)
    standard_error = math.sqrt(max(float(covariance[1, 1]), 0))
    estimate = float(coefficients[1])
    width = float(t.ppf(0.975, degrees)) * standard_error
    prediction_features = [1, math.log(float(product["current_price"]))]
    # Forecast a non-promoted average weekday at the latest observed seasonal level.
    current_controls = [0, math.log(rows[-1][3]), 0, 0]
    prediction_features.extend(current_controls[index] for index in control_indices)
    predicted_log_units = float(np.dot(prediction_features, coefficients))
    # Lognormal retransformation corrects Jensen bias in the arithmetic demand mean.
    daily_demand = math.exp(min(predicted_log_units + residual_variance / 2, 25))
    total_variance = float(np.sum((target - target.mean()) ** 2))
    return ElasticityEstimate(
        estimate=estimate, lower=estimate - width, upper=estimate + width,
        sample_size=len(rows), standard_error=standard_error,
        degrees_of_freedom=degrees, daily_demand=daily_demand,
        residual_sigma=math.sqrt(residual_variance),
        r_squared=1 - float(residuals @ residuals) / total_variance if total_variance else 0,
        excluded_observations=len(sales) - len(rows),
    )
