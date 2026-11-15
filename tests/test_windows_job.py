"""Job ownership persists when a wrapper exits; these seams do not execute Win32."""

import subprocess
from types import SimpleNamespace

import pytest

from scripts.windows_job import OwnedJob, Win32, StartupInfoEx
import scripts.windows_job as module


class Api:
    def __init__(self, *, resume_error=False, kill_error=False):
        self.events, self.count, self.exited = [], 0, False
        self.resume_error, self.kill_error = resume_error, kill_error

    def create_job(self):
        self.events.append("create-kill-on-close-job")
        return "job"

    def start_suspended(self, job, command, cwd, environment):
        assert job == "job"
        self.events.append("create-suspended-already-in-job")
        self.count = 1
        return "process", "thread", 12345

    def resume(self, thread):
        assert thread == "thread"
        self.events.append("resume-primary-thread")
        if self.resume_error:
            raise OSError("explicit resume seam")

    def close(self, handle):
        self.events.append(("close", handle))
        if handle == "job":
            self.count, self.exited = 0, True

    def terminate_process(self, handle):
        self.events.append(("terminate-suspended-process", handle))
        self.count, self.exited = 0, True

    def active(self, job):
        assert job == "job"
        return self.count

    def terminate_job(self, handle):
        self.events.append(("terminate-job-by-handle", handle))
        if self.kill_error:
            raise OSError("explicit termination seam")
        self.count, self.exited = 0, True

    def wait(self, handle, timeout):
        if not self.exited:
            raise subprocess.TimeoutExpired("owned fixture", timeout)
        return 0


def start(api):
    job = OwnedJob(api)
    process = job.start(["cmd.exe", "/c", "startup.bat"], cwd="fixture", environment={})
    return job, process


def test_job_owns_suspended_root_before_its_primary_thread_can_execute():
    api = Api()
    job, _process = start(api)
    assert api.events[:3] == ["create-kill-on-close-job", "create-suspended-already-in-job", "resume-primary-thread"]
    api.count, api.exited = 0, True
    report = job.close(drain_seconds=0)
    assert report == {"job_closed": True, "forced_job_cleanup": False, "all_processes_exited": True, "active_at_close": 0}


def test_exited_wrapper_with_live_descendants_is_cleaned_by_job_handle():
    api = Api()
    job, process = start(api)
    api.exited, api.count = True, 2  # Root exited; two descendants remain owned.
    assert process.poll() == 0
    report = job.close(drain_seconds=0)
    assert ("terminate-job-by-handle", "job") in api.events
    assert report["forced_job_cleanup"] and report["all_processes_exited"]
    assert ("close", "job") in api.events and ("close", "process") in api.events


def test_resume_failure_closes_primary_thread_and_leaves_no_unowned_process():
    api, job = Api(resume_error=True), None
    job = OwnedJob(api)
    with pytest.raises(OSError, match="resume seam"):
        job.start(["cmd.exe", "/c", "startup.bat"], cwd="fixture", environment={})
    assert ("terminate-suspended-process", "process") in api.events
    assert ("close", "thread") in api.events
    report = job.close(drain_seconds=0)
    assert report["all_processes_exited"] and report["job_closed"]


def test_failed_job_termination_still_closes_kill_on_close_handle_and_does_not_claim_drain():
    api = Api(kill_error=True)
    job, _process = start(api)
    report = job.close(drain_seconds=0)
    assert report["forced_job_cleanup"] and not report["all_processes_exited"]
    assert report["job_closed"] and api.count == 0
    assert ("close", "job") in api.events


def test_native_create_sets_atomic_job_list_suspended_primary_and_explicit_environment():
    events = []
    def initialize(attributes, count, flags, size):
        size._obj.value = 64
        return attributes is not None
    def update(_attributes, _flags, key, jobs, size, _previous, _returned):
        assert key == 0x2000D and jobs._obj[0] == 101
        events.append("atomic-job-list")
        return True
    def create(application, line, _process_security, _thread_security, inherit, flags, env, cwd, startup, process):
        assert application == "cmd.exe" and cwd == "fixture"
        assert inherit and flags & 0x4 and flags & 0x80000 and flags & 0x200 and flags & 0x400
        assert isinstance(startup._obj, StartupInfoEx)
        assert startup._obj.startup.cb == module.C.sizeof(StartupInfoEx)
        assert startup._obj.startup.stdin == startup._obj.startup.stdout == startup._obj.startup.stderr == 20
        assert "PATH=fixture" in "".join(env)
        assert events == ["atomic-job-list"]
        events.append("create-suspended-owned-root")
        process._obj.process, process._obj.thread, process._obj.pid = 2, 3, 99
        return True
    api = Win32.__new__(Win32)
    api.kernel = SimpleNamespace(CreateFileW=lambda *_args: 20, InitializeProcThreadAttributeList=initialize,
        UpdateProcThreadAttribute=update, CreateProcessW=create,
        DeleteProcThreadAttributeList=lambda *_args: events.append("delete-attributes"),
        CloseHandle=lambda handle: events.append(("close", handle)) or True)
    assert api.start_suspended(101, ["cmd.exe", "/c", "startup.bat"], "fixture", {"PATH": "fixture"}) == (2, 3, 99)
    assert events == ["atomic-job-list", "create-suspended-owned-root", "delete-attributes", ("close", 20)]


def test_job_enables_kill_on_close_without_breakaway_flags():
    events = []
    def configure(handle, kind, limits, size):
        assert handle == 101 and kind == 9
        assert limits._obj.basic.flags == 0x2000
        events.append("kill-on-close-no-breakaway")
        return True
    api = Win32.__new__(Win32)
    api.kernel = SimpleNamespace(CreateJobObjectW=lambda *_args: 101, SetInformationJobObject=configure)
    assert api.create_job() == 101
    assert events == ["kill-on-close-no-breakaway"]


def test_unsupported_atomic_job_attribute_cannot_start_any_process(monkeypatch):
    closed = []
    monkeypatch.setattr(module.C, "get_last_error", lambda: 50, raising=False)
    def initialize(attributes, count, flags, size):
        size._obj.value = 64
        return attributes is not None
    api = Win32.__new__(Win32)
    api.kernel = SimpleNamespace(CreateFileW=lambda *_args: 20, InitializeProcThreadAttributeList=initialize,
        UpdateProcThreadAttribute=lambda *_args: False,
        CreateProcessW=lambda *_args: pytest.fail("An unsupported job attribute must fail before creation."),
        DeleteProcThreadAttributeList=lambda *_args: None, CloseHandle=lambda handle: closed.append(handle) or True)
    with pytest.raises(OSError):
        api.start_suspended(101, ["cmd.exe", "/c", "startup.bat"], "fixture", {})
    assert closed == [20]
