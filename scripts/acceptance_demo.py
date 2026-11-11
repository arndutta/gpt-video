"""Run isolated W1–W9 HTTP/graph acceptance fixtures and retain measured evidence.

This never targets running services. Model/embedding fixtures and a simulated
observation clock are explicit; passing does not certify a real gateway or product KPIs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "W1": {"description": "Five-node grounded run, numeric integrity and checkpoint recovery", "tests": [
        "test_workflow_integration.py::test_five_nodes_numeric_integrity_citations_and_mixed_item_execution",
        "test_workflow_integration.py::test_checkpoint_survives_restart_and_requires_recorded_item_decision"]},
    "W2": {"description": "Mode/band matrix, absolute compliance and kill fencing", "tests": [
        "test_governance_workflow.py::test_mode_band_matrix_and_dispatch",
        "test_governance_workflow.py::test_escalation_never_auto_and_requires_written_human_override",
        "test_governance_veto_matrix.py::test_every_rule_vetoes_in_every_mode_and_human_override",
        "test_governance_execution.py::test_kill_ack_fences_unsent_and_preserves_inflight_receipt"]},
    "W3": {"description": "Saved multi-SKU scenarios, distributions, stress, baseline and no writes", "tests": [
        "test_operations_api.py::test_scenarios_save_distributions_stress_compare_and_never_approve",
        "test_analysis.py::test_fixed_seed_and_scenario_share_identical_price_conditioned_draws"]},
    "W4": {"description": "Runtime upload replacement consumed by the next grounded run", "tests": [
        "test_acceptance_demo.py::test_runtime_upload_version_is_consumed_by_subsequent_grounded_graph_without_restart",
        "test_grounding_api.py::test_replacement_changes_live_context_retains_old_citations_and_replay_is_idempotent"]},
    "W5": {"description": "Partial writes, original-key reconciliation, exact replay and compliant revert", "tests": [
        "test_governance_execution.py::test_partial_commerce_outcome_is_persisted_per_item",
        "test_governance_execution.py::test_ambiguous_commit_reads_original_receipt_and_applies_once",
        "test_governance_execution.py::test_compensating_revert_is_idempotent_and_current_rules_veto",
        "test_commerce.py::test_batch_replay_is_noop_and_conflicting_payload_is_rejected"]},
    "W6": {"description": "HTTP mature-window readback, disjoint evidence and bounded learning", "tests": [
        "test_acceptance_demo.py::test_real_commerce_http_aggregate_readback_updates_three_disjoint_learning_versions",
        "test_feedback_learning.py::test_bounded_learning_requires_disjoint_evidence_and_can_widen",
        "test_feedback_learning.py::test_short_windows_cannot_refine_or_claim_calibrated_confidence"]},
    "W7": {"description": "Append-only per-SKU audit reconstruction and redacted export", "tests": [
        "test_audit_history.py::test_sku_chain_includes_human_decision_and_http_attempt_without_explicit_sku",
        "test_platform.py::test_audit_is_persisted_and_append_only",
        "test_discovery_integration.py::test_central_audit_redactor_uses_current_memory_only_key_for_export_and_storage"]},
    "W8": {"description": "Runtime settings, credential/TLS boundaries and metered structured gateway requests", "tests": [
        "test_platform.py::test_gateway_secret_is_memory_only_never_returned_or_echoed",
        "test_platform.py::test_tls_bypass_requires_explicit_environment_permission",
        "test_platform_safety.py::test_runtime_settings_swap_preserves_prior_snapshot",
        "test_llm_gateway_and_telemetry.py::test_actual_langchain_json_schema_gateway_request_and_usage"]},
    "W9": {"description": "Explicit-start loop, iteration cap, stop, failure halt and no boot restart", "tests": [
        "test_interval_loop.py::test_loop_off_until_explicit_start_and_iteration_cap_serializes_runs",
        "test_interval_loop.py::test_stop_cancels_timer_and_never_starts_another_iteration",
        "test_workflow_failures.py::test_unknown_full_graph_execution_stops_loop_without_second_iteration",
        "test_workflow_failures.py::test_validation_model_failure_leaves_drafts_unexecutable_and_stops_loop",
        "test_interval_loop.py::test_reboot_marks_prior_session_interrupted_and_never_restarts_timer"]},
}


def cases_from_junit(path):
    if not path.exists():
        return []
    result = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    for case in root.iter("testcase"):
        status = next((name for name in ("error", "failure", "skipped") if case.find(name) is not None), "passed")
        result.append({"module": case.get("classname", ""), "name": case.get("name", ""),
                       "seconds": float(case.get("time", "0")), "status": status})
    return result


def workflow_results(cases, workflows=WORKFLOWS):
    result = {}
    for workflow, plan in workflows.items():
        groups = []
        for selector in plan["tests"]:
            filename, function = selector.split("::", 1)
            stem = Path(filename).stem
            selected = [case for case in cases if case["module"].endswith(stem)
                        and case["name"].split("[", 1)[0] == function]
            status = ("not_run" if not selected else "passed" if all(case["status"] == "passed" for case in selected)
                      else "incomplete" if all(case["status"] in {"passed", "skipped"} for case in selected) else "failed")
            groups.append({"selector": "tests/" + selector, "status": status,
                           "case_count": len(selected), "cases": selected})
        passed = all(group["status"] == "passed" for group in groups)
        result[workflow] = {"description": plan["description"], "status": "passed" if passed else "failed",
                            "evidence": groups}
    return result


def source_digest():
    digest, count = hashlib.sha256(), 0
    for directory in ("commerce", "platform_app", "scripts", "tests"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            if "__pycache__" not in path.parts:
                digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes() + b"\0")
                count += 1
    return {"sha256": digest.hexdigest(), "python_files": count,
            "scope": "commerce, platform_app, scripts, tests; source including uncommitted files"}


def fixture_environment(directory):
    prefixes = ("GATEWAY_", "LLM_", "RAG_", "ALLOW_", "LANGFUSE_", "LANGCHAIN_", "LANGSMITH_", "LIVE_COMPETITOR_", "PRICING_")
    excluded = {"DATA_DIR", "COMMERCE_URL", "COMMERCE_DB_PATH", "PYTEST_ADDOPTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    environment = {key: value for key, value in os.environ.items() if key not in excluded and not key.startswith(prefixes)}
    environment["DATA_DIR"] = str(directory / "runtime")
    environment["PRICING_STARTUP_MODE"] = "preview"
    return environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/acceptance_demo_result.json")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args(argv)
    if not 30 <= args.timeout_seconds <= 900:
        parser.error("--timeout-seconds must be between 30 and 900")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    junit, log = output.with_suffix(".junit.xml"), output.with_suffix(".pytest.log")
    # A prior report is never mistaken for evidence from a failed new invocation.
    junit.unlink(missing_ok=True)
    selectors = list(dict.fromkeys("tests/" + selector for plan in WORKFLOWS.values() for selector in plan["tests"]))
    started, failure, source_before = time.perf_counter(), None, source_digest()
    with tempfile.TemporaryDirectory(prefix="pricing-acceptance-") as temporary:
        command = [sys.executable, "-m", "pytest", "-q", *selectors, "--junitxml", str(junit),
                   "--basetemp", str(Path(temporary) / "pytest")]
        try:
            completed = subprocess.run(command, cwd=ROOT, env=fixture_environment(Path(temporary)),
                                       text=True, capture_output=True, timeout=args.timeout_seconds)
            code, text = completed.returncode, completed.stdout + completed.stderr
        except subprocess.TimeoutExpired:
            code, text, failure = 124, "The isolated acceptance suite exceeded its configured timeout.", "timeout"
        log.write_text(text, encoding="utf-8")
    cases = cases_from_junit(junit)
    workflows = workflow_results(cases)
    source_after = source_digest()
    changed = source_before["sha256"] != source_after["sha256"]
    if not cases and failure is None:
        failure = "missing_or_invalid_junit"
    if changed:
        failure = "source_changed_during_run"
    passed = code == 0 and bool(cases) and not changed and all(plan["status"] == "passed" for plan in workflows.values())
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "status": "passed" if passed else "failed",
              "scope": "W1–W9 isolated implementation acceptance demonstration", "python": platform.python_version(),
              "platform": platform.platform(), "seconds": round(time.perf_counter() - started, 3),
              "exit_code": code, "failure": failure, "case_count": len(cases), "workflows": workflows,
              "source": source_after, "source_changed_during_run": changed,
              "source_sha256_at_start": source_before["sha256"],
              "artifacts": {"junit": str(junit), "pytest_log": str(log)},
              "isolation": {"temporary_fixture_storage_removed": True, "live_services_contacted": False,
                            "inherited_gateway_tracing_proxy_configuration": "removed in child process"},
              "limitations": ["Typed model and lightweight embedding fixtures; no real gateway/model reliability or latency claim.",
                              "Mature aggregate-sales windows use an explicit isolated observation-clock fixture, not real business outcomes.",
                              "Backend HTTP/graph behavior only; native browser and Windows execution require their own acceptance evidence.",
                              "Passing does not establish revenue uplift, human acceptance/escalation precision, or production release readiness."]}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": len(cases), "seconds": report["seconds"],
                      "workflows": {key: value["status"] for key, value in workflows.items()}, "report": str(output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
