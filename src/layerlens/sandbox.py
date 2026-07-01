"""Run a code snippet and capture its output.

This exists so that view 4 (the naive implementation) is *proven* to run rather
than hallucinated: the host asks this tool to execute the code, and the real
stdout / success flag get embedded back into the explanation.

Hardening (per review):
  - stdout/stderr are decoded as UTF-8 (``errors="replace"``) regardless of the
    parent's locale, so Japanese/Greek output isn't lost on a cp932 Windows host.
  - output is drained on background threads and bounded, so a runaway ``print``
    loop can't exhaust memory.
  - on timeout the whole process *tree* is killed (new process group / session),
    so orphaned children don't survive.

Security note: this is NOT a hardened sandbox. It runs code your own host LLM
produced, on your machine, with a timeout. Do not point it at untrusted input;
networked/filesystem side effects are possible.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading

STDOUT_CAP = 8000
STDERR_CAP = 4000


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
    """Execute ``code`` with the current interpreter, returning a result dict."""
    with tempfile.TemporaryDirectory(prefix="layerlens-") as d:
        path = os.path.join(d, "snippet.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)

        kwargs: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=d,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen([sys.executable, path], **kwargs)
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
