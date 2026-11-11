"""Deterministic overlapping chunks with exact source offsets and optional token budgets."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start_char: int
    end_char: int


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 100, *,
               token_count: Callable[[str], int] | None = None,
               max_tokens: int | None = None) -> list[TextChunk]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Document text must contain non-whitespace content")
    if type(chunk_size) is not int or chunk_size < 1:
        raise ValueError("chunk_size must be a positive integer")
    if type(overlap) is not int or not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be a non-negative integer smaller than chunk_size")
    if (token_count is None) != (max_tokens is None):
        raise ValueError("token_count and max_tokens must be supplied together")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
        raise ValueError("max_tokens must be a positive integer")
    chunks, cursor = [], 0
    while cursor < len(text):
        end = min(cursor + chunk_size, len(text))
        if token_count is not None and token_count(text[cursor:end]) > max_tokens:
            low, high = cursor + 1, end
            while low < high:
                middle = (low + high + 1) // 2
                if token_count(text[cursor:middle]) <= max_tokens:
                    low = middle
                else:
                    high = middle - 1
            end = low
        # Prefer paragraph/word boundaries without creating an unbounded overlap loop.
        minimum = cursor + max(1, (end - cursor) // 2)
        if end < len(text):
            boundary = text.rfind("\n\n", minimum, end)
            if boundary < minimum:
                boundary = text.rfind(" ", minimum, end)
            if boundary > minimum:
                end = boundary
        if token_count is not None:
            # Truncating a word can change tokenization; validate the exact final prefix.
            while end > cursor and token_count(text[cursor:end]) > max_tokens:
                end -= 1
            if end == cursor:
                raise ValueError("The embedding token budget cannot fit the next source character")
        raw = text[cursor:end]
        start_trim = len(raw) - len(raw.lstrip())
        stop_trim = len(raw.rstrip())
        if stop_trim > start_trim:
            start, stop = cursor + start_trim, cursor + stop_trim
            chunks.append(TextChunk(len(chunks), text[start:stop], start, stop))
        if end == len(text):
            break
        effective_overlap = min(overlap, max(0, (end - cursor) // 2))
        cursor = max(cursor + 1, end - effective_overlap)
    if not chunks:
        raise ValueError("No non-whitespace chunks could be produced")
    return chunks
