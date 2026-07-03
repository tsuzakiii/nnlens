from pathlib import Path

from nnlens import config


def test_store_dir_migrates_legacy_stores(tmp_path, monkeypatch):
    # Path.home() honors USERPROFILE on Windows (and HOME on POSIX).
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NNLENS_STORE", raising=False)

    # Earlier project names, in migration-priority order: .layerlore then .layerlens.
    legacy = tmp_path / ".layerlore" / "store" / "e"
    legacy.mkdir(parents=True)
    (legacy / "old-page.html").write_text("<!doctype html>", encoding="utf-8")

    store = Path(config.store_dir())
    assert store == tmp_path / ".nnlens" / "store"
    assert (store / "e" / "old-page.html").exists(), "legacy explanations migrated"


def test_store_dir_migrates_oldest_legacy_when_newer_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NNLENS_STORE", raising=False)

    legacy = tmp_path / ".layerlens" / "store" / "e"
    legacy.mkdir(parents=True)
    (legacy / "oldest.html").write_text("<!doctype html>", encoding="utf-8")

    store = Path(config.store_dir())
    assert (store / "e" / "oldest.html").exists()


def test_store_dir_env_override_skips_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    override = tmp_path / "custom-store"
    monkeypatch.setenv("NNLENS_STORE", str(override))

    legacy = tmp_path / ".layerlore" / "store"
    legacy.mkdir(parents=True)

    store = Path(config.store_dir())
    assert store == override
    assert legacy.exists(), "explicit override must not touch the legacy store"
