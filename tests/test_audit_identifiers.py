"""Redaction preserves canonical audit references without exposing known credentials."""

from platform_app.llm.safety import redact
from platform_app.storage import Store


ID = "5c168845-fb11-4583-9f98-123456789012"


def test_numeric_uuid_segment_remains_reconstructible_in_append_only_audit(tmp_path):
    store = Store(tmp_path)
    store.audit("decision", {"item_id": ID, "phone": "+1 415 555 2671"}, run_id=ID)
    [event] = store.list_audit()
    assert event["run_id"] == event["detail"]["item_id"] == ID
    assert event["detail"]["phone"] == "[REDACTED]"
    assert redact("Contact +1 415 555 2671.") == "Contact [PHONE]."


def test_uuid_shaped_known_secret_is_redacted_before_identifier_preservation():
    assert redact(ID, secrets=[ID]) == "[REDACTED]"
