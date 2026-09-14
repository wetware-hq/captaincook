"""Europe PMC peer-reviewed (MEDLINE) search. Separate from /research preprint filter."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .research_client import (
    EUROPE_PMC_SEARCH,
    Author,
    Record,
    _authors_of,
    _date_of,
    _doi_url,
    _plain_text,
    _year_of,
)

USER_AGENT = "captaincook-evidence"
TIMEOUT_SEC = 20
PAGE_SIZE = 25
RESULT_CAP = 5

# Peer-reviewed MEDLINE path only. Do not use research_client.QUERY_FILTER (SRC:PPR).
QUERY_FILTER = "SRC:MED NOT SRC:PPR"

_PREPRINT_MARKERS = frozenset(
    {
        "biorxiv",
        "medrxiv",
        "researchsquare",
        "preprint",
        "chemrxiv",
        "arxiv",
        "ssrn",
    }
)


class EvidenceServiceError(Exception):
    """Lit API down, timed out, or returned an unparseable body. Fail-closed."""


def build_query(question: str) -> str:
    """Europe PMC query: (question) AND SRC:MED NOT SRC:PPR."""
    cleaned = _sanitize_question(question)
    if not cleaned:
        cleaned = "medicine"
    return f"({cleaned}) AND {QUERY_FILTER}"


def search_peer_reviewed(question: str) -> list[Record]:
    """GET Europe PMC; return at most five peer-reviewed MEDLINE records.

    Raises EvidenceServiceError on HTTP failure, timeout, or unparseable JSON.
    An honest empty list means the service answered and found no matching articles.
    """
    query = build_query(question)
    params = {
        "query": query,
        "format": "json",
        "pageSize": str(PAGE_SIZE),
        "resultType": "core",
    }
    url = f"{EUROPE_PMC_SEARCH}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urlopen(req, timeout=TIMEOUT_SEC) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read()
    except HTTPError as exc:
        raise EvidenceServiceError("Europe PMC HTTP error") from exc
    except TimeoutError as exc:
        raise EvidenceServiceError("Europe PMC timed out") from exc
    except URLError as exc:
        raise EvidenceServiceError("Europe PMC was unreachable") from exc
    except OSError as exc:
        raise EvidenceServiceError("Europe PMC request failed") from exc

    if status is not None and int(status) != 200:
        raise EvidenceServiceError("Europe PMC returned a non-success status")

    return parse_search_body(raw)


def parse_search_body(raw: bytes | str) -> list[Record]:
    """Parse a Europe PMC search JSON body. Drop PPR / preprint-looking hits. Fail-closed."""
    if raw is None:
        raise EvidenceServiceError("Europe PMC returned an empty body")
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceServiceError("Europe PMC body was not UTF-8") from exc
    else:
        text = raw
    text = text.strip()
    if not text:
        raise EvidenceServiceError("Europe PMC returned an empty body")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvidenceServiceError("Europe PMC body was not JSON") from exc
    if not isinstance(data, dict):
        raise EvidenceServiceError("Europe PMC JSON was not an object")
    if "hitCount" not in data and "resultList" not in data:
        raise EvidenceServiceError("Europe PMC JSON lacked search fields")

    result_list = data.get("resultList")
    if result_list is None:
        if data.get("hitCount") == 0:
            return []
        raise EvidenceServiceError("Europe PMC JSON lacked a result list")
    if not isinstance(result_list, dict):
        raise EvidenceServiceError("Europe PMC result list was unparseable")
    rows = result_list.get("result")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise EvidenceServiceError("Europe PMC result rows were unparseable")

    records: list[Record] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        rec = _record_from_row(row, relevance=idx)
        if rec is not None:
            records.append(rec)

    return _sorted_records(_records_with_doi(records))[:RESULT_CAP]


def _records_with_doi(records: list[Record]) -> list[Record]:
    """Keep only records that have a real DOI string. Prefer fewer hits over no-DOI lines."""
    out: list[Record] = []
    for rec in records:
        doi = (rec.doi or "").strip()
        if doi:
            out.append(rec)
    return out


def _sanitize_question(question: str) -> str:
    cleaned = (question or "").strip()
    cleaned = re.sub(r'[:()"]', " ", cleaned)
    cleaned = re.sub(r"\b(AND|OR|NOT)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _looks_like_preprint(row: dict[str, Any]) -> bool:
    """Drop anything that still looks like a preprint (source=PPR or known servers)."""
    source = _plain_text(row.get("source")).upper()
    if source == "PPR":
        return True
    candidates: list[str] = []
    book = row.get("bookOrReportDetails") or {}
    if isinstance(book, dict):
        candidates.append(str(book.get("publisher") or ""))
    journal = row.get("journalInfo") or {}
    if isinstance(journal, dict):
        inner = journal.get("journal") or {}
        if isinstance(inner, dict):
            candidates.append(str(inner.get("title") or ""))
        candidates.append(str(journal.get("journalTitle") or ""))
    candidates.append(str(row.get("journalTitle") or ""))
    candidates.append(str(row.get("publisher") or ""))
    for raw in candidates:
        key = re.sub(r"[^a-z]", "", raw.lower())
        if key in _PREPRINT_MARKERS or "preprint" in key:
            return True
    return False


def _journal_of(row: dict[str, Any]) -> str:
    journal = row.get("journalInfo") or {}
    if isinstance(journal, dict):
        inner = journal.get("journal") or {}
        if isinstance(inner, dict):
            title = _plain_text(inner.get("title"))
            if title:
                return title
        title = _plain_text(journal.get("journalTitle"))
        if title:
            return title
    title = _plain_text(row.get("journalTitle"))
    if title:
        return title
    return "Journal"


def _url_of(row: dict[str, Any], doi: str | None) -> str | None:
    if doi:
        return _doi_url(doi)
    urls = (
        ((row.get("fullTextUrlList") or {}).get("fullTextUrl") or [])
        if isinstance(row.get("fullTextUrlList"), dict)
        else []
    )
    if isinstance(urls, dict):
        urls = [urls]
    if isinstance(urls, list):
        for item in urls:
            if isinstance(item, dict) and item.get("url"):
                return _plain_text(item.get("url"))
    pmid = _plain_text(row.get("pmid") or row.get("id"))
    if pmid and pmid.isdigit():
        return f"https://europepmc.org/article/MED/{pmid}"
    if pmid and not pmid.startswith("http"):
        return f"https://europepmc.org/article/MED/{pmid}"
    return None


def _record_from_row(row: dict[str, Any], *, relevance: int) -> Record | None:
    if _looks_like_preprint(row):
        return None
    title = _plain_text(row.get("title"))
    if not title:
        return None
    authors = _authors_of(row)
    year = _year_of(row)
    date = _date_of(row)
    doi = _plain_text(row.get("doi")) or None
    url = _url_of(row, doi)
    abstract = _plain_text(row.get("abstractText")) or None
    journal = _journal_of(row)
    return Record(
        authors=tuple(authors),
        year=year,
        title=title,
        server=journal,
        doi=doi,
        url=url,
        date=date,
        abstract=abstract,
        relevance=relevance,
    )


def _recency_key(rec: Record) -> tuple[int, str, int]:
    date = rec.date or ""
    year = rec.year or ""
    if date:
        stamp = date
        present = 1
    elif year:
        stamp = f"{year}-12-31"
        present = 1
    else:
        stamp = ""
        present = 0
    return (present, stamp, -rec.relevance)


def _sorted_records(records: list[Record]) -> list[Record]:
    return sorted(records, key=_recency_key, reverse=True)


# Re-export for callers/tests that expect Author on this module.
__all__ = [
    "Author",
    "EvidenceServiceError",
    "QUERY_FILTER",
    "RESULT_CAP",
    "Record",
    "build_query",
    "parse_search_body",
    "search_peer_reviewed",
]
