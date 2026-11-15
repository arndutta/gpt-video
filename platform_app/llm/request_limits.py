"""Explicit application-envelope limits; never an estimate of provider token capacity.

The measured UTF-8 JSON object contains every application message and the complete
Pydantic schema. SDK transformations, provider framing, model IDs and wire headers
are outside this application envelope. Inputs are rejected intact, never truncated.
"""

from .safety import GroundedLLMError, canonical


def envelope_size(schema, messages):
    envelope = {"messages": [{"role": role, "content": content} for role, content in messages],
                "schema": schema.model_json_schema()}
    return len(canonical(envelope).encode("utf-8"))


def enforce_envelope_limit(schema, messages, maximum_bytes):
    if maximum_bytes is None:
        return
    size = envelope_size(schema, messages)
    if size > maximum_bytes:
        raise GroundedLLMError("model_envelope_too_large",
            f"The complete messages/schema envelope is {size} UTF-8 bytes, exceeding "
            f"LLM_MAX_ENVELOPE_BYTES={maximum_bytes}. Use a smaller selected scope or strategy "
            "batch, or configure a cap supported by the gateway. Inputs were not truncated; "
            "this byte cap does not verify the model's token-context capacity.")
