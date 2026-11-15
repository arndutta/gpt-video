"""Bounded validation explanations retain every complete deterministic verdict."""

from collections import Counter

from platform_app.tools import AnalysisError
from .prompts import narrative_prompt
from .schemas import CitedNarrative


def require_policy(owner, expected_version):
    if owner.governance.mode()["policy_version"] != expected_version:
        raise AnalysisError("Policy changed after the numeric stage. Start a new run to recompute its constraints.",
                            "stale_policy")


async def narrate_verdicts(owner, run_id, items, policy_version):
    """No item is activated here; Execution is reached only after every batch succeeds."""
    require_policy(owner, policy_version)
    batch_size = owner.settings_provider().validation_batch_size
    bands = dict(Counter(item["band"] for item in items))
    batches = []
    for offset in range(0, len(items), batch_size):
        require_policy(owner, policy_version)
        batch = items[offset:offset + batch_size]
        result = await owner.llm.generate(CitedNarrative, role="strategist",
            query="Explain retail compliance veto and review band thresholds",
            facts={"bands": bands, "verdicts": [{"sku": item["sku"], "band": item["band"],
                                                  "compliance": item["compliance"]} for item in batch]},
            run_id=run_id, prompt=narrative_prompt(
                "Explain the deterministic verdicts. A model explanation cannot change any rule or approval band."),
            policy_version=str(policy_version))
        require_policy(owner, policy_version)
        batches.append({"sku_ids": [item["sku"] for item in batch], "narrative": result.model_dump()})
    require_policy(owner, policy_version)
    if not batches:
        raise AnalysisError("No recommendation verdicts were available for validation.", "no_eligible_skus")
    if len(batches) == 1:
        return batches[0]["narrative"]
    # Keep each complete model response, rather than cutting a combined string/list
    # to fit a single response schema's per-call limits. Top-level unions retain
    # the existing evidence/citation affordances for report readers.
    unions = {key: list(dict.fromkeys(value for batch in batches for value in batch["narrative"][key]))
              for key in ("assumptions", "anomalies", "citations")}
    return {"interpretation": f"Complete validation explanations are retained in {len(batches)} SKU batches.",
            **unions, "batches": batches}
