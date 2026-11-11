"""Shared embedding validation; failures must never echo document or credential content."""

import math
from numbers import Real


class EmbeddingUnavailable(RuntimeError):
    """The explicitly selected embedding provider cannot produce usable vectors."""


def validate_texts(texts: list[str]) -> None:
    if not isinstance(texts, list) or not texts or not all(
        isinstance(text, str) and text.strip() for text in texts
    ):
        raise ValueError("Embedding input must be a nonempty list of nonblank text strings.")


def validate_vectors(vectors, expected_count: int, dimensions: int) -> list[list[float]]:
    try:
        if len(vectors) != expected_count:
            raise ValueError
        result = []
        for vector in vectors:
            if len(vector) != dimensions or not all(
                isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
                for value in vector
            ):
                raise ValueError
            values = [float(value) for value in vector]
            if not any(value != 0 for value in values):
                raise ValueError
            result.append(values)
        return result
    except (TypeError, ValueError, OverflowError):
        raise EmbeddingUnavailable("Embedding provider returned invalid, nonfinite, zero, or incorrectly sized vectors.") from None
