"""Retrieval helpers: papers (arXiv), official repos (GitHub), and file excerpts.

All calls use only the standard library so the MCP server has no heavy deps.
Every function returns a plain dict and degrades gracefully (``error`` key) instead
of raising, so a flaky network never crashes a tool call.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_UA = {"User-Agent": "nnlens/0.1 (+https://github.com/; educational explainer)"}
_TIMEOUT = 20
_ATOM = "{http://www.w3.org/2005/Atom}"

# new-style: 1706.03762 / 1706.03762v3 ; old-style: hep-th/9711200, math.AG/0309136
_OLD_ID = re.compile(r"[a-z-]+(?:\.[A-Z]{2})?/\d{7}", re.I)
_NEW_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?")
_GH = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _extract_repos(text: str) -> list[str]:
    """Pull github.com/owner/repo URLs out of free text (abstracts, links)."""
    return [m.rstrip(".,);:]") for m in _GH.findall(text or "")]


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _get(url: str, headers: dict | None = None, timeout: int = _TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted hosts)
        return resp.read().decode("utf-8", "replace")


def _extract_arxiv_id(query: str) -> str | None:
    q = query.strip()
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", q, re.I)
    if m:
        cand = m.group(1).rstrip("/")
        return cand[:-4] if cand.lower().endswith(".pdf") else cand
    m = _OLD_ID.search(q)
    if m:
        return m.group(0)
    m = _NEW_ID.search(q)
    if m:
        return m.group(0)
    return None


def fetch_paper(query: str) -> dict:
    """Resolve an arXiv id / url / free-text query to a paper's title, abstract, and url."""
    arxiv_id = _extract_arxiv_id(query)
    if arxiv_id:
        api = "http://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id, safe="/.")
    else:
        api = (
            "http://export.arxiv.org/api/query?search_query="
            + urllib.parse.quote("all:" + query)
            + "&max_results=1"
        )
    try:
        xml = _get(api)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"arxiv fetch failed: {exc}", "query": query}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return {"error": f"arxiv parse failed: {exc}", "query": query}

    entry = root.find(_ATOM + "entry")
    if entry is None:
        return {"error": "no_results", "query": query}

    def text(tag: str) -> str:
        node = entry.find(_ATOM + tag)
        return re.sub(r"\s+", " ", node.text).strip() if node is not None and node.text else ""

    title, summary, url = text("title"), text("summary"), text("id")
    # Papers usually link their official code in the abstract (and sometimes in a
    # <link>). Surfacing these lets the host build view 5 from the *real* repo even
    # when find_official_repo would be defeated by a name collision (e.g. "PRISM").
    repos = _extract_repos(title + " " + summary)
    for link in entry.findall(_ATOM + "link"):
        href = link.get("href", "")
        if "github.com" in href:
            repos.extend(_extract_repos(href))
    return {"title": title, "summary": summary, "url": url, "repos": _dedupe(repos), "query": query}


def find_official_repo(name: str) -> dict:
    """Search GitHub for candidate official repositories for a technique/architecture."""
    q = urllib.parse.quote(name)
    api = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5"
    try:
        data = json.loads(_get(api, headers={"Accept": "application/vnd.github+json"}))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"github search failed: {exc}", "candidates": []}
    candidates = [
        {
            "full_name": r.get("full_name", ""),
            "url": r.get("html_url", ""),
            "stars": r.get("stargazers_count", 0),
            "description": r.get("description") or "",
        }
        for r in data.get("items", [])
    ]
    return {"candidates": candidates}


def fetch_repo_code(full_name: str, path: str, ref: str = "HEAD", max_chars: int = 20000) -> dict:
    """Fetch a single source file from a GitHub repo (raw), reading at most ~max_chars."""
    path = path.lstrip("/")
    raw_url = (
        "https://raw.githubusercontent.com/"
        + urllib.parse.quote(full_name, safe="/")
        + "/"
        + urllib.parse.quote(ref, safe="/")
        + "/"
        + urllib.parse.quote(path, safe="/")
    )
    try:
        req = urllib.request.Request(raw_url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            # Cap the read (utf-8 is up to 4 bytes/char) so huge files don't blow memory.
            raw = resp.read((max_chars + 1) * 4)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"raw fetch failed: {exc}", "content": "", "url": raw_url}
    content = raw.decode("utf-8", "replace")
    truncated = len(content) > max_chars
    blob = f"https://github.com/{full_name}/blob/{ref}/{path}"
    return {"content": content[:max_chars], "truncated": truncated, "url": blob}
