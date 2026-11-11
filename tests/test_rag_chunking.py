"""Chunking preserves exact source offsets and explicit model token budgets."""

import pytest

from platform_app.rag.chunking import chunk_text


def reconstruct(chunks):
    text = chunks[0].text
    previous_end = chunks[0].end_char
    for chunk in chunks[1:]:
        overlap = max(0, previous_end - chunk.start_char)
        text += chunk.text[overlap:]
        previous_end = chunk.end_char
    return text


def test_unicode_and_offsets_round_trip_without_mutating_source():
    text = "Margin_policy—café_₹_€_USD." * 17
    chunks = chunk_text(text, chunk_size=91, overlap=13)
    assert len(chunks) > 2
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.text == text[chunk.start_char:chunk.end_char]
        assert 0 < len(chunk.text) <= 91
    for earlier, later in zip(chunks, chunks[1:]):
        assert earlier.start_char < later.start_char <= earlier.end_char
        assert 0 < earlier.end_char - later.start_char <= 13
    assert chunks[0].start_char == 0 and chunks[-1].end_char == len(text)
    assert reconstruct(chunks) == text
    assert chunk_text(text, chunk_size=91, overlap=13) == chunks


def test_whitespace_trimming_retains_exact_offsets_and_covers_all_source_content():
    text = " \n\tMargin policy — café\n\nBrand guidance: ₹, €, and USD.\t" * 17
    chunks = chunk_text(text, chunk_size=91, overlap=13)
    covered = set()
    for chunk in chunks:
        assert chunk.text == text[chunk.start_char:chunk.end_char]
        assert 0 < len(chunk.text) <= 91
        covered.update(range(chunk.start_char, chunk.end_char))
    assert all(index in covered for index, character in enumerate(text) if not character.isspace())


def test_short_document_and_zero_overlap_are_supported():
    only = chunk_text("One margin rule.", chunk_size=50, overlap=0)
    assert len(only) == 1 and only[0].text == "One margin rule."
    text = "Price_and_margin." * 20
    chunks = chunk_text(text, chunk_size=47, overlap=0)
    assert all(first.end_char == second.start_char for first, second in zip(chunks, chunks[1:]))
    assert reconstruct(chunks) == text


@pytest.mark.parametrize("size,overlap", [(0, 0), (-1, 0), (20, -1), (20, 20), (20, 21)])
def test_invalid_chunk_limits_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("A valid document.", chunk_size=size, overlap=overlap)


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_empty_document_is_rejected(text):
    with pytest.raises(ValueError):
        chunk_text(text)


def test_model_token_budget_shrinks_chunks_and_overlap_without_losing_source():
    text = "margin-policy_costs_₹" * 23
    # Each character stands for a token in this adversarial tokenizer fixture.
    chunks = chunk_text(text, chunk_size=100, overlap=70, token_count=len, max_tokens=19)
    assert all(len(chunk.text) <= 19 for chunk in chunks)
    assert all(next_chunk.start_char > chunk.start_char for chunk, next_chunk in zip(chunks, chunks[1:]))
    assert reconstruct(chunks) == text


@pytest.mark.parametrize("budget", [0, -1])
def test_invalid_token_budgets_are_rejected(budget):
    with pytest.raises(ValueError):
        chunk_text("Margin policy.", token_count=len, max_tokens=budget)
