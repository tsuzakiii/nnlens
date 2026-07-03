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
