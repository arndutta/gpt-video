"""Every validation verdict is explained once before Execution can activate anything."""

from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import pytest

from platform_app.config import Settings
from platform_app.llm import GroundedLLMError
from platform_app.tools import AnalysisError
from platform_app.workflow.nodes import AgentNodes
from platform_app.workflow.schemas import CitedNarrative


def fixture(count=28, batch_size=25):
    items = [{"id": f"item-{index}", "sku": f"SKU-{index}", "band": "review" if index % 2 else "escalate",
              "status": "pending_review", "executable": False,
              "compliance": {"status": "passed", "rules": [{"rule": f"rule-{rule}", "passed": True,
                  "actual": {"price": "10.00", "precision": 2}, "threshold": "9.00",
                  "message": f"Complete evidence for rule {rule}"} for rule in range(8)]}}
             for index in range(count)]
    state = {"run_id": "validation-fixture", "report": {"recommendations": deepcopy(items),
                "configuration": {"numeric_policy_version": 1}, "aggregate": {"fixture": True}},
             "context": {"catalog": [{"sku": item["sku"]} for item in items]}, "history": [],
             "data_narrative": {"fixture": "data"}, "quantitative_narrative": {"fixture": "numeric"}}
    owner = SimpleNamespace(policy_version=1, calls=[], registration=[], activation=[],
                            fail_at=None, change_policy_at=None, change_during_registration=False)

    async def register(*args, **kwargs):
        owner.registration.append((deepcopy(args), deepcopy(kwargs)))
        if owner.change_during_registration:
            owner.policy_version += 1
        return deepcopy(items)

    async def activate(*args):
        owner.activation.append(args)

    async def generate(schema, **kwargs):
        owner.calls.append((schema, deepcopy(kwargs)))
        number = len(owner.calls)
        if owner.fail_at == number:
            raise GroundedLLMError("structured_output_invalid", "Explicit fixture model failure")
        if owner.change_policy_at == number:
            owner.policy_version += 1
        return CitedNarrative(interpretation=f"Complete batch {number} explanation.",
                             assumptions=["Shared assumption", f"Batch {number} assumption"],
                             anomalies=[f"Batch {number} warning"], citations=["policy:shared", f"policy:{number}"])

    owner.governance = SimpleNamespace(mode=lambda: {"policy_version": owner.policy_version},
                                       register=register, activate=activate)
    owner.llm = SimpleNamespace(generate=generate)
    owner.settings_provider = lambda: Settings(validation_batch_size=batch_size)
    owner.store = SimpleNamespace(update_run=lambda *_a, **_k: None, audit=lambda *_a, **_k: None)
    return owner, state, items


@pytest.mark.parametrize("batch_size", [1, 7, 25])
async def test_all_28_verdicts_and_full_rules_are_retained_exactly_once(batch_size):
    owner, state, items = fixture(batch_size=batch_size)
    before = deepcopy(state)
    result = await AgentNodes(owner).validation(state)
    assert state == before, "Narration must not mutate the numerical input report."
    assert len(owner.registration) == 1 and owner.registration[0][1]["activate"] is False
    assert not owner.activation
    assert all(schema is CitedNarrative for schema, _ in owner.calls)
    assert all(len(call["facts"]["verdicts"]) <= batch_size for _, call in owner.calls)
    explained = [verdict for _, call in owner.calls for verdict in call["facts"]["verdicts"]]
    expected = [{key: item[key] for key in ("sku", "band", "compliance")} for item in items]
    assert explained == expected
    assert Counter(item["sku"] for item in explained) == Counter(item["sku"] for item in items)
    assert all(call["policy_version"] == "1" for _, call in owner.calls)
    assert all(call["facts"]["bands"] == dict(Counter(item["band"] for item in items))
               for _, call in owner.calls)
    assert result["report"]["recommendations"] == items
    assert result["report"]["executable"] is False
    narrative = result["validation_narrative"]
    assert narrative == result["report"]["validation_narrative"]
    assert [sku for batch in narrative["batches"] for sku in batch["sku_ids"]] == [i["sku"] for i in items]
    for number, batch in enumerate(narrative["batches"], 1):
        assert batch["narrative"] == CitedNarrative(interpretation=f"Complete batch {number} explanation.",
            assumptions=["Shared assumption", f"Batch {number} assumption"],
            anomalies=[f"Batch {number} warning"], citations=["policy:shared", f"policy:{number}"]).model_dump()
    assert narrative["assumptions"] == ["Shared assumption"] + [
        f"Batch {number} assumption" for number in range(1, len(owner.calls) + 1)]
    assert narrative["anomalies"] == [f"Batch {number} warning" for number in range(1, len(owner.calls) + 1)]
    assert narrative["citations"] == ["policy:shared"] + [
        f"policy:{number}" for number in range(1, len(owner.calls) + 1)]


async def test_default_small_run_keeps_existing_cited_narrative_shape():
    owner, state, _ = fixture(count=3)
    result = await AgentNodes(owner).validation(state)
    assert len(owner.calls) == 1
    narrative = result["validation_narrative"]
    assert set(narrative) == {"interpretation", "assumptions", "anomalies", "citations"}
    assert CitedNarrative.model_validate(narrative).model_dump() == narrative


async def test_middle_batch_failure_does_not_return_executable_report_or_activate_items():
    owner, state, _ = fixture(batch_size=7)
    owner.fail_at = 2
    with pytest.raises(GroundedLLMError) as caught:
        await AgentNodes(owner).validation(state)
    assert caught.value.code == "structured_output_invalid"
    assert len(owner.calls) == 2 and len(owner.registration) == 1
    assert owner.registration[0][1]["activate"] is False and not owner.activation


@pytest.mark.parametrize("change_at", [1, 2])
async def test_changed_policy_after_any_batch_stops_before_execution(change_at):
    owner, state, _ = fixture()
    owner.change_policy_at = change_at
    with pytest.raises(AnalysisError) as caught:
        await AgentNodes(owner).validation(state)
    assert caught.value.code == "stale_policy"
    assert len(owner.calls) == change_at and not owner.activation
    assert all(call["policy_version"] == "1" for _, call in owner.calls)


async def test_policy_change_during_registration_prevents_the_first_model_call():
    owner, state, _ = fixture()
    owner.change_during_registration = True
    with pytest.raises(AnalysisError) as caught:
        await AgentNodes(owner).validation(state)
    assert caught.value.code == "stale_policy" and not owner.calls and not owner.activation


def test_validation_batch_size_is_an_explicit_bounded_environment_choice(monkeypatch):
    assert Settings().validation_batch_size == 25
    monkeypatch.setenv("LLM_VALIDATION_BATCH_SIZE", "3")
    assert Settings.from_environment().validation_batch_size == 3
    for value in (0, 26, 1.5):
        with pytest.raises(ValueError):
            Settings(validation_batch_size=value)
