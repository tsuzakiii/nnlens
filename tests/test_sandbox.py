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


def test_socket_c_module_is_also_blocked():
    # Codex-verified bypass: the C extension module was left unpatched.
    r = run_python("import _socket\n_socket.socket()")
    assert r["ok"] is False
    assert "network access is disabled" in r["stderr"]


def test_socket_alias_sockettype_is_blocked():
    r = run_python("import socket\nsocket.SocketType()")
    assert r["ok"] is False
    assert "network access is disabled" in r["stderr"]


def test_process_creation_is_blocked():
    # A spawned interpreter would carry none of the shims, so spawning is refused.
    r = run_python("import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])")
    assert r["ok"] is False
    assert "process creation is disabled" in r["stderr"]

    r2 = run_python("import os\nos.system('echo hi')")
    assert r2["ok"] is False
    assert "process creation is disabled" in r2["stderr"]


def test_sibling_module_import_works_like_a_script():
    # -I drops the script dir from sys.path; the boot shim restores just that dir.
    r = run_python("open('helper.py','w').write('value = 7')\nimport helper\nprint(helper.value)")
    assert r["ok"] is True, r["stderr"]
    assert "7" in r["stdout"]
