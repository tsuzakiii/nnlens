from nnlens.sandbox import run_python


def test_success_captures_stdout():
    r = run_python("print('hello', 1 + 1)")
    assert r["ok"] is True
    assert r["returncode"] == 0
    assert "hello 2" in r["stdout"]


def test_failure_reports_error():
    r = run_python("raise ValueError('boom')")
    assert r["ok"] is False
    assert r["returncode"] != 0
    assert "boom" in r["stderr"]


def test_timeout():
    r = run_python("import time; time.sleep(5)", timeout=0.5)
    assert r["ok"] is False
    assert "Timed out" in r["stderr"]


def test_utf8_output_survives_on_any_locale():
    # Regression: on a cp932 Windows host, non-ASCII stdout used to come back empty.
    r = run_python("print('日本語 α β √')")
    assert r["ok"] is True
    assert "日本語" in r["stdout"]
    assert "α" in r["stdout"]


def test_output_is_bounded():
    # A runaway print loop must not blow up memory; stdout is capped.
    r = run_python("print('x' * 100000)")
    assert r["ok"] is True
    assert len(r["stdout"]) <= 8100  # STDOUT_CAP (+ a little slack)


def test_network_is_disabled():
    r = run_python("import socket\nsocket.socket()")
    assert r["ok"] is False
    assert "network access is disabled" in r["stderr"]


def test_parent_env_is_scrubbed(monkeypatch):
    monkeypatch.setenv("NNLENS_FAKE_SECRET", "leak-me")
    r = run_python("import os; print(repr(os.environ.get('NNLENS_FAKE_SECRET')))")
    assert r["ok"] is True
    assert "leak-me" not in r["stdout"]
    assert "None" in r["stdout"]


def test_sandbox_control_vars_not_visible_to_snippet():
    r = run_python("import os; print(repr(os.environ.get('NNLENS_SB_MEM')))")
    assert r["ok"] is True
    assert "None" in r["stdout"]


def test_memory_cap_stops_huge_allocation():
    # 3 GiB > the 2 GiB cap: rlimit (POSIX) or Job Object (Windows) must stop it.
    r = run_python("x = bytearray(3 * 1024**3)\nprint('allocated')")
    assert r["ok"] is False
    assert "allocated" not in r["stdout"]


def test_numpy_still_importable_in_sandbox():
    r = run_python("import numpy; print('np', numpy.__version__)")
    assert r["ok"] is True, r["stderr"]
    assert "np" in r["stdout"]
