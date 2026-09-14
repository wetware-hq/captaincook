"""Europe PMC preprint search (bioRxiv / medRxiv). One HTTP GET. Research-use only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
USER_AGENT = "captaincook-research"
TIMEOUT_SEC = 20
PAGE_SIZE = 25
RESULT_CAP = 5

# Topic keywords AND preprint corpus AND bioRxiv/medRxiv publisher or journal.
# Ranked locally: first-online / pub year desc; Europe PMC order is the relevance tie-break.
QUERY_FILTER = (
    'SRC:PPR AND (PUBLISHER:"bioRxiv" OR PUBLISHER:"medRxiv" '
    'OR JOURNAL:"bioRxiv" OR JOURNAL:"medRxiv")'
)


class ResearchServiceError(Exception):
    """Lit API down, timed out, or returned an unparseable body. Fail-closed."""


@dataclass(frozen=True)
class Author:
    family: str
    initials: str  # dotted, no trailing period, e.g. "J.A" or "K"


@dataclass(frozen=True)
class Record:
    authors: tuple[Author, ...]
    year: str | None
    title: str
    server: str
    doi: str | None
    url: str | None
    date: str | None
    abstract: str | None = None
    relevance: int = 0


def build_query(topic: str) -> str:
    """Europe PMC query string for a user topic (filter locked)."""
    cleaned = _sanitize_topic(topic)
    if not cleaned:
        cleaned = "preprint"
    return f"({cleaned}) AND {QUERY_FILTER}"


def search_preprints(topic: str) -> list[Record]:
    """GET Europe PMC search JSON; return at most five bioRxiv/medRxiv records.

    Raises ResearchServiceError on HTTP failure, timeout, or unparseable JSON.
    An honest empty list means the service answered and found no matching preprints.
    """
    query = build_query(topic)
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
        raise ResearchServiceError("Europe PMC HTTP error") from exc
    except TimeoutError as exc:
        raise ResearchServiceError("Europe PMC timed out") from exc
    except URLError as exc:
        raise ResearchServiceError("Europe PMC was unreachable") from exc
    except OSError as exc:
        raise ResearchServiceError("Europe PMC request failed") from exc

    if status is not None and int(status) != 200:
        raise ResearchServiceError("Europe PMC returned a non-success status")

    return parse_search_body(raw)


def parse_search_body(raw: bytes | str) -> list[Record]:
    """Parse a Europe PMC search JSON body. Fail-closed on garbage."""
    if raw is None:
        raise ResearchServiceError("Europe PMC returned an empty body")
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ResearchServiceError("Europe PMC body was not UTF-8") from exc
    else:
        text = raw
    text = text.strip()
    if not text:
        raise ResearchServiceError("Europe PMC returned an empty body")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResearchServiceError("Europe PMC body was not JSON") from exc
    if not isinstance(data, dict):
        raise ResearchServiceError("Europe PMC JSON was not an object")
    if "hitCount" not in data and "resultList" not in data:
        raise ResearchServiceError("Europe PMC JSON lacked search fields")

    result_list = data.get("resultList")
    if result_list is None:
        if data.get("hitCount") == 0:
            return []
        raise ResearchServiceError("Europe PMC JSON lacked a result list")
    if not isinstance(result_list, dict):
        raise ResearchServiceError("Europe PMC result list was unparseable")
    rows = result_list.get("result")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ResearchServiceError("Europe PMC result rows were unparseable")

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


def _recency_key(rec: Record) -> tuple[int, str, int]:
    """Newest first; missing dates last; lower relevance idx wins ties."""
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


def _sanitize_topic(topic: str) -> str:
    cleaned = (topic or "").strip()
    cleaned = re.sub(r'[:()"]', " ", cleaned)
    cleaned = re.sub(r"\b(AND|OR|NOT)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _record_from_row(row: dict[str, Any], *, relevance: int) -> Record | None:
    server = _server_of(row)
    if server is None:
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
    return Record(
        authors=tuple(authors),
        year=year,
        title=title,
        server=server,
        doi=doi,
        url=url,
        date=date,
        abstract=abstract,
        relevance=relevance,
    )


_SERVER_NAMES = {
    "biorxiv": "bioRxiv",
    "medrxiv": "medRxiv",
}


def _server_of(row: dict[str, Any]) -> str | None:
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
        if key in _SERVER_NAMES:
            return _SERVER_NAMES[key]
    return None


def _authors_of(row: dict[str, Any]) -> list[Author]:
    out: list[Author] = []
    block = row.get("authorList") or {}
    people = block.get("author") if isinstance(block, dict) else None
    if isinstance(people, dict):
        people = [people]
    if isinstance(people, list):
        for person in people:
            if not isinstance(person, dict):
                continue
            family = _plain_text(person.get("lastName") or person.get("fullName"))
            if not family:
                continue
            # If we only have fullName "Smith JA", split trailing initials.
            initials = _format_initials(_plain_text(person.get("initials")))
            if not initials and person.get("lastName") is None:
                family, initials = _split_fullname(family)
            elif person.get("lastName") and not initials:
                initials = _format_initials(_plain_text(person.get("firstName")))
            if family:
                out.append(Author(family=family, initials=initials))
    if out:
        return out
    return _authors_from_string(_plain_text(row.get("authorString")))


def _authors_from_string(blob: str) -> list[Author]:
    if not blob:
        return []
    out: list[Author] = []
    for part in blob.split(","):
        family, initials = _split_fullname(part.strip().rstrip("."))
        if family:
            out.append(Author(family=family, initials=initials))
    return out


def _split_fullname(name: str) -> tuple[str, str]:
    bits = name.split()
    if not bits:
        return "", ""
    if len(bits) == 1:
        return bits[0], ""
    last = bits[-1]
    if re.fullmatch(r"[A-Za-z.]{1,4}", last):
        return " ".join(bits[:-1]), _format_initials(last)
    return name, ""


def _format_initials(raw: str) -> str:
    compact = re.sub(r"[^A-Za-z]", "", raw or "")
    if not compact:
        return ""
    return ".".join(ch.upper() for ch in compact)


def _year_of(row: dict[str, Any]) -> str | None:
    year = _plain_text(row.get("pubYear"))
    if year.isdigit() and len(year) == 4:
        return year
    date = _date_of(row)
    if date and len(date) >= 4 and date[:4].isdigit():
        return date[:4]
    book = row.get("bookOrReportDetails") or {}
    if isinstance(book, dict):
        yop = book.get("yearOfPublication")
        if yop is not None:
            text = str(yop).strip()
            if text.isdigit() and len(text) == 4:
                return text
    return None


def _date_of(row: dict[str, Any]) -> str | None:
    for key in ("firstPublicationDate", "firstIndexDate", "dateOfCreation"):
        val = _plain_text(row.get(key))
        if val:
            return val
    return None


def _url_of(row: dict[str, Any], doi: str | None) -> str | None:
    if doi:
        return _doi_url(doi)
    urls = ((row.get("fullTextUrlList") or {}).get("fullTextUrl") or []) if isinstance(row.get("fullTextUrlList"), dict) else []
    if isinstance(urls, dict):
        urls = [urls]
    if isinstance(urls, list):
        for item in urls:
            if isinstance(item, dict) and item.get("url"):
                return _plain_text(item.get("url"))
    pmcid = _plain_text(row.get("id") or row.get("pmcid"))
    if pmcid:
        return f"https://europepmc.org/article/PPR/{pmcid}" if not pmcid.startswith("http") else pmcid
    return None


def _doi_url(doi: str) -> str:
    doi = doi.strip()
    if doi.lower().startswith("http"):
        return doi
    return f"https://doi.org/{doi.lstrip('/')}"


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()
