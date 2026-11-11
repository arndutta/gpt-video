"""Simulated uncertainty of the jointly feasible optimizer, not evaluator truth."""

from collections import defaultdict

import numpy as np

SELECTION_VERSION = "joint-price-selection-v1"


def selection_uncertainty(prepared, catalog, selected):
    """Re-optimize each existing sample column with unchanged family constraints.

    A precise elasticity estimate can still have a broad price argmax when the
    objective is flat. These ranges expose that uncertainty without changing the
    expected-objective choice, dropping a SKU, or widening the feasible price set.
    """
    if not prepared:
        return {}
    by_sku = {item["product"]["sku"]: item for item in prepared}
    iterations = prepared[0]["sample_scores"].shape[1]
    columns = np.arange(iterations)
    families = defaultdict(list)
    for product in catalog:
        families[product.get("family_id") or product["sku"]].append(product)
    result = {}
    for family in families.values():
        ordered = sorted(family, key=lambda p: (float(p.get("size", 1)), p["sku"]))
        options, values = [], []
        for product in ordered:
            item = by_sku.get(product["sku"])
            options.append(np.asarray(item["prices"] if item else [float(product["current_price"])]))
            values.append(item["sample_scores"] if item else np.zeros((1, iterations)))
        totals, links = values[0], []
        for index in range(1, len(ordered)):
            next_totals = np.full((len(options[index]), iterations), -np.inf)
            parents = np.full((len(options[index]), iterations), -1, dtype=int)
            for position, price in enumerate(options[index]):
                allowed = np.flatnonzero(options[index - 1] <= price + 1e-9)
                if not len(allowed):
                    continue
                best = np.argmax(totals[allowed], axis=0)
                best_indices = allowed[best]
                best_scores = totals[best_indices, columns]
                next_totals[position] = best_scores + values[index][position]
                parents[position] = best_indices
            totals = next_totals
            links.append(parents)
        valid = np.isfinite(totals).any(axis=0)
        if not valid.all():
            # The feasibility set is sample-independent. Invalid columns mean
            # no complete family ladder exists; no precision claim is emitted.
            continue
        choices = np.argmax(totals, axis=0)
        for index in range(len(ordered) - 1, -1, -1):
            product = ordered[index]
            sku = product["sku"]
            if sku in selected:
                sampled_prices = options[index][choices]
                lower, median, upper = np.quantile(sampled_prices, [.025, .5, .975])
                chosen = selected[sku]
                relative_width = float(upper - lower) / max(abs(chosen), 1e-9)
                result[sku] = {"method": SELECTION_VERSION, "samples": iterations,
                               "lower": float(lower), "median": float(median), "upper": float(upper),
                               "interval_level": .95, "relative_width": relative_width,
                               "selected_price_probability": float(np.mean(np.isclose(sampled_prices, chosen, atol=1e-9, rtol=0))),
                               "precision_cap": 1 / (1 + relative_width),
                               "interpretation": "Simulated joint argmax range under fitted uncertainty, not empirical coverage or a probability of price accuracy."}
            if index:
                choices = links[index - 1][choices, columns]
    return result
