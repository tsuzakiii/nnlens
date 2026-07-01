"""Network-dependent tests. Skipped automatically when offline / rate-limited."""

import pytest

from layerlens import sources
from layerlens.sources import _extract_arxiv_id


def test_extract_arxiv_id_variants():
    # Pure/offline: no network needed.
    assert _extract_arxiv_id("1706.03762") == "1706.03762"
    assert _extract_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762"
    assert _extract_arxiv_id("https://arxiv.org/abs/1706.03762/") == "1706.03762"
    assert _extract_arxiv_id("https://arxiv.org/pdf/1706.03762v2.pdf") == "1706.03762v2"
    assert _extract_arxiv_id("hep-th/9711200") == "hep-th/9711200"
    assert _extract_arxiv_id("attention is all you need") is None


def _skip_if_error(result: dict):
    if result.get("error"):
        pytest.skip(f"network unavailable: {result['error']}")


def test_fetch_paper_attention():
    r = sources.fetch_paper("1706.03762")
    _skip_if_error(r)
    assert "Attention" in r.get("title", "")
    assert r.get("summary")


def test_find_official_repo():
    r = sources.find_official_repo("pytorch")
    _skip_if_error(r)
    assert r.get("candidates"), "expected at least one candidate"
    assert any("pytorch" in c["full_name"].lower() for c in r["candidates"])


def test_fetch_repo_code():
    r = sources.fetch_repo_code("pytorch/pytorch", "README.md")
    _skip_if_error(r)
    assert r.get("content")
    assert r["url"].startswith("https://github.com/pytorch/pytorch/blob/")
