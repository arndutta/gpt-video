"""Owned Windows Job Object; children cannot execute before assignment.

CreateProcessW(JOB_LIST + CREATE_SUSPENDED) -> ResumeThread.
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE also protects exception/interpreter teardown.
Native APIs: learn.microsoft.com/en-us/windows/win32/procthread/job-objects.
"""

import ctypes as C
from ctypes import wintypes as W
import subprocess
import time


class SecurityAttributes(C.Structure):
    _fields_ = [("length", W.DWORD), ("descriptor", W.LPVOID), ("inherit", W.BOOL)]


class StartupInfo(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR), ("title", W.LPWSTR),
                ("x", W.DWORD), ("y", W.DWORD), ("width", W.DWORD), ("height", W.DWORD),
                ("xchars", W.DWORD), ("ychars", W.DWORD), ("fill", W.DWORD), ("flags", W.DWORD),
                ("show", W.WORD), ("reserved_size", W.WORD), ("reserved_bytes", C.POINTER(C.c_byte)),
                ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


class StartupInfoEx(C.Structure):
    _fields_ = [("startup", StartupInfo), ("attributes", W.LPVOID)]


class BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_longlong), ("job_time", C.c_longlong), ("flags", W.DWORD),
                ("min_working_set", C.c_size_t), ("max_working_set", C.c_size_t),
                ("active_limit", W.DWORD), ("affinity", C.c_size_t),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters), ("process_memory", C.c_size_t),
                ("job_memory", C.c_size_t), ("peak_process_memory", C.c_size_t), ("peak_job_memory", C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [("user_time", C.c_longlong), ("kernel_time", C.c_longlong),
                ("period_user_time", C.c_longlong), ("period_kernel_time", C.c_longlong),
                ("page_faults", W.DWORD), ("total", W.DWORD), ("active", W.DWORD), ("terminated", W.DWORD)]


class Win32:
    def __init__(self):
        kernel = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": (W.HANDLE, [W.LPVOID, W.LPCWSTR]),
            "SetInformationJobObject": (W.BOOL, [W.HANDLE, C.c_int, W.LPVOID, W.DWORD]),
            "QueryInformationJobObject": (W.BOOL, [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, W.LPVOID]),
            "TerminateJobObject": (W.BOOL, [W.HANDLE, W.UINT]),
            "InitializeProcThreadAttributeList": (W.BOOL, [W.LPVOID, W.DWORD, W.DWORD, W.LPVOID]),
            "UpdateProcThreadAttribute": (W.BOOL, [W.LPVOID, W.DWORD, C.c_size_t, W.LPVOID,
                                                  C.c_size_t, W.LPVOID, W.LPVOID]),
            "DeleteProcThreadAttributeList": (None, [W.LPVOID]),
            "CloseHandle": (W.BOOL, [W.HANDLE]),
            "CreateFileW": (W.HANDLE, [W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD, W.HANDLE]),
            "CreateProcessW": (W.BOOL, [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL,
                                       W.DWORD, W.LPVOID, W.LPCWSTR, W.LPVOID, W.LPVOID]),
            "ResumeThread": (W.DWORD, [W.HANDLE]),
            "TerminateProcess": (W.BOOL, [W.HANDLE, W.UINT]),
            "WaitForSingleObject": (W.DWORD, [W.HANDLE, W.DWORD]),
            "GetExitCodeProcess": (W.BOOL, [W.HANDLE, W.LPVOID]),
            "GenerateConsoleCtrlEvent": (W.BOOL, [W.DWORD, W.DWORD]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(kernel, name)
            function.restype, function.argtypes = result, arguments
        self.kernel = kernel

    @staticmethod
    def check(value):
        if not value:
            raise OSError(C.get_last_error(), "Owned Windows job operation failed")
        return value

    def close(self, handle):
        self.check(self.kernel.CloseHandle(handle))

    def create_job(self):
        handle = self.check(self.kernel.CreateJobObjectW(None, None))
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway flags.
            self.check(self.kernel.SetInformationJobObject(handle, 9, C.byref(limits), C.sizeof(limits)))
            return handle
        except BaseException:
            self.close(handle)
            raise

    def start_suspended(self, job, command, cwd, environment):
        attributes = SecurityAttributes(C.sizeof(SecurityAttributes), None, True)
        null = self.kernel.CreateFileW("NUL", 0xC0000000, 3, C.byref(attributes), 3, 0, None)
        if null == W.HANDLE(-1).value:
            self.check(False)
        attribute_list, initialized, info = None, False, ProcessInfo()
        try:
            size = C.c_size_t()
            self.kernel.InitializeProcThreadAttributeList(None, 1, 0, C.byref(size))
            self.check(size.value)
            attribute_list = C.create_string_buffer(size.value)
            self.check(self.kernel.InitializeProcThreadAttributeList(attribute_list, 1, 0, C.byref(size)))
            initialized = True
            jobs = (W.HANDLE * 1)(job)
            # ProcThreadAttributeJobList=13 plus PROC_THREAD_ATTRIBUTE_INPUT=0x20000.
            self.check(self.kernel.UpdateProcThreadAttribute(attribute_list, 0, 0x2000D,
                       C.byref(jobs), C.sizeof(jobs), None, None))
            startup = StartupInfoEx()
            startup.startup.cb, startup.startup.flags = C.sizeof(startup), 0x100
            startup.startup.stdin = startup.startup.stdout = startup.startup.stderr = null
            startup.attributes = C.cast(attribute_list, W.LPVOID)
            line = C.create_unicode_buffer(subprocess.list2cmdline(command))
            block = C.create_unicode_buffer("\0".join(f"{key}={environment[key]}" for key in sorted(environment, key=str.upper)) + "\0\0")
            # Atomic job assignment, suspended thread, console group, Unicode environment.
            self.check(self.kernel.CreateProcessW(command[0], line, None, None, True,
                       0x80000 | 0x4 | 0x200 | 0x400, block, str(cwd), C.byref(startup), C.byref(info)))
            return info.process, info.thread, info.pid
        finally:
            if initialized:
                self.kernel.DeleteProcThreadAttributeList(attribute_list)
            try:
                self.close(null)
            except OSError:
                # Any created root is already in the job and cannot outlive job cleanup.
                if info.thread:
                    self.kernel.CloseHandle(info.thread)
                if info.process:
                    self.kernel.CloseHandle(info.process)
                raise

    def resume(self, thread):
        if self.kernel.ResumeThread(thread) != 1:
            self.check(False)

    def terminate_process(self, process):
        self.check(self.kernel.TerminateProcess(process, 1))

    def active(self, job):
        info = Accounting()
        self.check(self.kernel.QueryInformationJobObject(job, 1, C.byref(info), C.sizeof(info), None))
        return info.active

    def terminate_job(self, job):
        self.check(self.kernel.TerminateJobObject(job, 1))

    def wait(self, process, timeout):
        outcome = self.kernel.WaitForSingleObject(process, int(timeout * 1000))
        if outcome == 258:
            raise subprocess.TimeoutExpired("owned Windows wrapper", timeout)
        if outcome != 0:
            self.check(False)
        code = W.DWORD()
        self.check(self.kernel.GetExitCodeProcess(process, C.byref(code)))
        return code.value

    def send_break(self, pid):
        self.check(self.kernel.GenerateConsoleCtrlEvent(1, pid))


class OwnedProcess:
    def __init__(self, api, handle, pid):
        self.api, self.handle, self.pid = api, handle, pid
        self.returncode = None

    def poll(self):
        if self.handle is None:
            return self.returncode
        try:
            self.returncode = self.api.wait(self.handle, 0)
            return self.returncode
        except subprocess.TimeoutExpired:
            return None

    def wait(self, timeout):
        self.returncode = self.api.wait(self.handle, timeout)
        return self.returncode

    def send_signal(self, number):
        if number != 1:
            raise ValueError("Only CTRL_BREAK_EVENT is supported for the owned group")
        self.api.send_break(self.pid)

    def close(self):
        if self.handle is not None:
            try:
                self.poll()
            finally:
                handle, self.handle = self.handle, None
                self.api.close(handle)


class OwnedJob:
    def __init__(self, api=None):
        self.api = api or Win32()
        self.handle = self.api.create_job()
        self.process = None

    def start(self, command, *, cwd, environment):
        handle, thread, pid = self.api.start_suspended(self.handle, command, cwd, environment)
        self.process = OwnedProcess(self.api, handle, pid)
        try:
            self.api.resume(thread)
            return self.process
        except BaseException:
            # The root is already owned and suspended when resume fails.
            self.api.terminate_process(handle)
            self.api.wait(handle, 5)
            raise
        finally:
            self.api.close(thread)

    def close(self, drain_seconds=5):
        result = {"job_closed": False, "forced_job_cleanup": False,
                  "all_processes_exited": False, "active_at_close": None}
        if self.handle is None:
            return result
        try:
            deadline = time.monotonic() + drain_seconds
            while self.api.active(self.handle) and time.monotonic() < deadline:
                time.sleep(.05)
            if self.api.active(self.handle):
                result["forced_job_cleanup"] = True
                self.api.terminate_job(self.handle)
                deadline = time.monotonic() + 5
                while self.api.active(self.handle) and time.monotonic() < deadline:
                    time.sleep(.05)
            result["active_at_close"] = self.api.active(self.handle)
            result["all_processes_exited"] = result["active_at_close"] == 0
        except (OSError, subprocess.SubprocessError):
            result["forced_job_cleanup"] = True
        finally:
            handle, self.handle = self.handle, None
            try:
                self.api.close(handle)  # KILL_ON_JOB_CLOSE protects every remaining descendant.
                result["job_closed"] = True
            finally:
                if self.process:
                    self.process.close()
        return result
