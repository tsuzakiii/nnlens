"""Run a code snippet and capture its output, inside a best-effort sandbox.

This exists so that view 4 (the naive implementation) is *proven* to run rather
than hallucinated: the host asks this tool to execute the code, and the real
stdout / success flag get embedded back into the explanation.

Sandbox (best-effort, accident-level — see the honest limits below):
  - the child runs ``python -I`` (isolated mode: no user site, no PYTHON* env);
  - its **environment is scrubbed** — API keys/tokens in the parent's env are
    simply not there; HOME/TEMP point into the throwaway working dir;
  - **network is disabled** (a boot shim stubs out ``socket``'s constructors
    before the snippet runs);
  - **resource caps**: memory / CPU-time / written-file-size via rlimits on
    POSIX, and a Job Object (memory + max processes + kill-on-close) on Windows;
  - stdout/stderr are drained on background threads and bounded; UTF-8 decoding
    regardless of the parent's locale; stdin is /dev/null (an inherited MCP
    stdio pipe used to deadlock the child on Windows);
  - on timeout the whole process *tree* is killed.

Honest limits: this raises the bar against prompt-injected or runaway snippets,
but it is NOT a hardened security boundary — code that really wants to can undo
the in-process shims (e.g. via ctypes). Keep your MCP host's permission prompt
on this tool for anything you don't trust; for real isolation run the whole
server in a container.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

STDOUT_CAP = 8000
STDERR_CAP = 4000
MEM_CAP_BYTES = 2 << 30  # 2 GiB per snippet
FSIZE_CAP_BYTES = 256 << 20  # snippets may write scratch files, but not fill the disk
MAX_PROCESSES = 8  # Windows Job Object: forkbomb stopper

# Applies the in-child restrictions, then runs the snippet with a clean argv and
# correct tracebacks (the snippet stays its own file; we never prepend to it).
_BOOT = """\
import os, runpy, sys

if os.name == "posix":
    try:
        import resource
        _mem = int(os.environ.pop("NNLENS_SB_MEM", "0"))
        _cpu = int(os.environ.pop("NNLENS_SB_CPU", "0"))
        _fsz = int(os.environ.pop("NNLENS_SB_FSIZE", "0"))
        if _mem:
            resource.setrlimit(resource.RLIMIT_AS, (_mem, _mem))
        if _cpu:
            resource.setrlimit(resource.RLIMIT_CPU, (_cpu, _cpu))
        if _fsz:
            resource.setrlimit(resource.RLIMIT_FSIZE, (_fsz, _fsz))
    except Exception:
        pass
else:
    for _k in ("NNLENS_SB_MEM", "NNLENS_SB_CPU", "NNLENS_SB_FSIZE"):
        os.environ.pop(_k, None)

import socket as _socket

def _no_net(*_a, **_k):
    raise OSError("nnlens sandbox: network access is disabled")

for _name in (
    "socket", "socketpair", "create_connection", "create_server",
    "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr",
):
    if hasattr(_socket, _name):
        setattr(_socket, _name, _no_net)
del _socket

_path = sys.argv[1]
sys.argv = [_path]
runpy.run_path(_path, run_name="__main__")
"""


def _python_interpreter() -> str:
    """Return a real Python interpreter to run snippets with.

    When nnlens is launched via its console-script wrapper (``nnlens.exe``),
    ``sys.executable`` is that wrapper, NOT an interpreter — running ``[sys.executable,
    snippet]`` would re-launch the MCP server (which hangs on stdio) and every snippet
    would "time out". So if ``sys.executable`` isn't a python binary, recover the real
    interpreter from the (venv) prefix.
    """
    exe = sys.executable or ""
    if os.path.basename(exe).lower().startswith("python"):
        return exe
    names = ("python.exe", "pythonw.exe") if os.name == "nt" else ("python3", "python")
    subdir = "Scripts" if os.name == "nt" else "bin"
    for root in (sys.prefix, getattr(sys, "base_prefix", sys.prefix)):
        for name in names:
            for cand in (os.path.join(root, subdir, name), os.path.join(root, name)):
                if os.path.isfile(cand):
                    return cand
    return shutil.which("python3") or shutil.which("python") or exe


def _child_env(tmpdir: str, interp: str, timeout: float) -> dict:
    """A minimal environment: nothing from the parent's env (API keys, tokens,
    proxies, ...) leaks into snippet code. Only what the interpreter needs to
    start, plus the sandbox caps the boot shim consumes."""
    env = {
        "PYTHONIOENCODING": "utf-8",
        "TEMP": tmpdir,
        "TMP": tmpdir,
        "TMPDIR": tmpdir,
        "HOME": tmpdir,
        "NNLENS_SB_MEM": str(MEM_CAP_BYTES),
        "NNLENS_SB_CPU": str(max(1, int(timeout) + 5)),
        "NNLENS_SB_FSIZE": str(FSIZE_CAP_BYTES),
    }
    if os.name == "nt":
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS"):
            if key in os.environ:
                env[key] = os.environ[key]
        env["USERPROFILE"] = tmpdir
        system32 = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32")
        # The venv python.exe needs the base install's python3xx.dll on PATH.
        env["PATH"] = os.pathsep.join(
            [os.path.dirname(interp), getattr(sys, "base_prefix", sys.prefix), system32]
        )
    else:
        env["PATH"] = "/usr/bin:/bin"
        env["LANG"] = os.environ.get("LANG", "C.UTF-8")
    return env


def _assign_windows_job(proc: subprocess.Popen) -> object | None:
    """Cap the child (memory / process count) with a Job Object; kill-on-close.

    Best-effort: returns the job handle to keep alive, or None. There is a tiny
    window between spawn and assignment — acceptable for the accident-level
    threat model (the snippet is still starting the interpreter at that point).
    """
    try:
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
        JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JobObjectExtendedLimitInformation = 9

        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.BasicLimitInformation.ActiveProcessLimit = MAX_PROCESSES
        info.ProcessMemoryLimit = MEM_CAP_BYTES
        ok = kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok or not kernel32.AssignProcessToJobObject(job, int(proc._handle)):
            kernel32.CloseHandle(job)
            return None
        return job
    except Exception:  # noqa: BLE001 — hardening must never break the feature
        return None


def _drain(stream, cap: int, out: list[str]) -> None:
    """Read a text stream to EOF, keeping at most ``cap`` chars (drains the rest)."""
    total = 0
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if total < cap:
                take = chunk[: cap - total]
                out.append(take)
                total += len(take)
    except Exception:  # noqa: BLE001 — reader thread must never raise
        pass
    finally:
        try:
            stream.close()
        except Exception:  # noqa: BLE001
            pass


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def run_python(code: str, timeout: float = 15.0) -> dict:
    """Execute ``code`` in the sandbox, returning a result dict."""
    with tempfile.TemporaryDirectory(prefix="nnlens-") as d:
        snippet = os.path.join(d, "snippet.py")
        with open(snippet, "w", encoding="utf-8") as fh:
            fh.write(code)
        boot = os.path.join(d, "_sandbox_boot.py")
        with open(boot, "w", encoding="utf-8") as fh:
            fh.write(_BOOT)

        interp = _python_interpreter()
        kwargs: dict = dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=d,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_child_env(d, interp, timeout),
        )
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        # -I ignores PYTHON* env vars (that's the point), which also drops
        # PYTHONIOENCODING — so force UTF-8 stdio via the -X utf8 flag instead.
        proc = subprocess.Popen([interp, "-I", "-X", "utf8", boot, snippet], **kwargs)
        job = _assign_windows_job(proc) if os.name == "nt" else None
        out: list[str] = []
        err: list[str] = []
        t_out = threading.Thread(target=_drain, args=(proc.stdout, STDOUT_CAP, out), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, STDERR_CAP, err), daemon=True)
        t_out.start()
        t_err.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        finally:
            if job is not None:  # kill-on-close reaps any stragglers in the job
                try:
                    import ctypes

                    ctypes.windll.kernel32.CloseHandle(job)
                except Exception:  # noqa: BLE001
                    pass
        t_out.join(timeout=2)
        t_err.join(timeout=2)

        stdout = "".join(out)
        stderr = "".join(err)
        if timed_out:
            stderr = (stderr + f"\nTimed out after {timeout}s.").strip()
        return {
            "ok": (not timed_out) and proc.returncode == 0,
            "returncode": None if timed_out else proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
