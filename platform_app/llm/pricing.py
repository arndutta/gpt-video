"""Small attributed LiteLLM standard-text rate snapshot with explicit unknown fallback."""

from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name("model_prices.json").read_text())


def estimate_cost(settings, role, alias, raw, tokens_in, tokens_out):
    try:
        snapshot = catalog()
    except (OSError, ValueError):
        snapshot = {"models": {}}
    configured = getattr(settings, "pricing_model_" + role, None)
    metadata = getattr(raw, "response_metadata", None) or {}
    candidates = [configured] if configured else [metadata.get("model_name"), metadata.get("model"), alias]
    name = next((name for name in candidates if isinstance(name, str) and name in snapshot["models"]), None)
    if name is None:
        return {"cost_usd": (tokens_in * settings.llm_input_cost_per_million
                             + tokens_out * settings.llm_output_cost_per_million) / 1_000_000,
                "pricing_source": "configured_fallback_rates", "pricing_model": None}
    rates = snapshot["models"][name]
    suffix = "_above_200k_tokens" if tokens_in > 200_000 else ""
    input_rate = rates.get("input_cost_per_token" + suffix, rates["input_cost_per_token"])
    output_rate = rates.get("output_cost_per_token" + suffix, rates["output_cost_per_token"])
    details = (getattr(raw, "usage_metadata", None) or {}).get("input_token_details", {})
    details = details if isinstance(details, dict) else {}
    cached = details.get("cache_read", 0)
    cached = min(cached, tokens_in) if isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0 else 0
    cache_rate = rates.get("cache_read_input_token_cost" + suffix,
                           rates.get("cache_read_input_token_cost", input_rate))
    cost = (tokens_in - cached) * input_rate + cached * cache_rate + tokens_out * output_rate
    return {"cost_usd": cost, "pricing_source": "litellm_snapshot", "pricing_model": name}
