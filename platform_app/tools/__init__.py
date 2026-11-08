"""Deterministic quantitative previews; these artifacts never authorize execution."""

from .analysis import AnalysisError, analyze_catalog, simulate_sku

__all__ = ["AnalysisError", "analyze_catalog", "simulate_sku"]
