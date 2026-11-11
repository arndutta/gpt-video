"""Release evidence cannot pass when cases fail, skip, disappear, or never collect."""

import json
import os
from pathlib import Path
import subprocess

from scripts import acceptance_demo


def test_junit_evidence_requires_all_workflow_cases_to_pass(tmp_path):
    junit = tmp_path / "cases.xml"
    junit.write_text('<testsuites><testsuite><testcase classname="tests.test_demo" name="test_pass" time="0.1" />'
                     '<testcase classname="tests.test_demo" name="test_fail"><failure /></testcase>'
                     '<testcase classname="tests.test_demo" name="test_skip"><skipped /></testcase>'
                     '</testsuite></testsuites>')
    cases = acceptance_demo.cases_from_junit(junit)
    assert len(cases) == 3 and cases[0]["seconds"] == .1
    plans = {key: {"description": key, "tests": [f"test_demo.py::{function}"]}
             for key, function in (("passing", "test_pass"), ("failure", "test_fail"),
                                   ("skipped", "test_skip"), ("missing", "test_missing"))}
    result = acceptance_demo.workflow_results(cases, plans)
    assert result["passing"]["status"] == "passed"
    assert all(result[key]["status"] == "failed" for key in ("failure", "skipped", "missing"))
    junit.write_text("<truncated")
    assert acceptance_demo.cases_from_junit(junit) == []


def test_fixture_subprocess_cannot_inherit_gateway_or_tracing_secrets(tmp_path, monkeypatch):
    for key in ("GATEWAY_API_KEY", "LANGFUSE_SECRET_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_API_KEY", "HTTPS_PROXY"):
        monkeypatch.setenv(key, "fixture-secret-must-not-leave-parent")
    environment = acceptance_demo.fixture_environment(tmp_path)
    assert not any("fixture-secret-must-not-leave-parent" == value for value in environment.values())
    assert environment["DATA_DIR"] == str(tmp_path / "runtime") and environment["PRICING_STARTUP_MODE"] == "preview"
    assert environment["PATH"] == os.environ["PATH"]


def test_failed_collection_produces_failed_json_instead_of_a_false_demo_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance_demo.platform, "platform", lambda: "isolated-test-platform")
    monkeypatch.setattr(acceptance_demo, "source_digest", lambda: {"sha256": "fixed-fixture", "python_files": 0})
    monkeypatch.setattr(acceptance_demo.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 5, stdout="No tests collected", stderr=""))
    output = tmp_path / "acceptance.json"
    assert acceptance_demo.main(["--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert report["status"] == "failed" and report["failure"] == "missing_or_invalid_junit" and report["case_count"] == 0
    assert all(plan["status"] == "failed" for plan in report["workflows"].values())
    assert not report["isolation"]["live_services_contacted"]
