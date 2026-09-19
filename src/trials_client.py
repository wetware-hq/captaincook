"""ClinicalTrials.gov API v2 public search. Fail-closed; never invent studies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = "captaincook-trials"
TIMEOUT_SEC = 20
DEFAULT_CAP = 5
MAX_CAP = 10

# Request only public registry modules we need (no PHI).
_FIELDS = (
    "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,"
    "EligibilityModule,Condition"
)


class TrialsServiceError(Exception):
    """CT.gov down, timed out, or returned an unparseable body. Fail-closed."""


@dataclass(frozen=True)
class TrialStudy:
    nct_id: str
    title: str
    status: str
    phase: str | None
    conditions: tuple[str, ...]
    eligibility_raw: str | None
    inclusion_themes: tuple[str, ...]
    exclusion_themes: tuple[str, ...]


def search_trials(term: str, *, limit: int = DEFAULT_CAP) -> list[TrialStudy]:
    """GET ClinicalTrials.gov v2 studies for query.term.

    Raises TrialsServiceError on HTTP failure, timeout, or unparseable JSON.
    An honest empty list means the service answered and found no matching studies.
    Never invents NCT ids or titles.
    """
    cleaned = _sanitize_term(term)
    if not cleaned:
        raise TrialsServiceError("empty search term")
    cap = _clamp_limit(limit)
    params = {
        "query.term": cleaned,
        "pageSize": str(cap),
        "format": "json",
        "fields": _FIELDS,
    }
    url = f"{STUDIES_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urlopen(req, timeout=TIMEOUT_SEC) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read()
    except HTTPError as exc:
        raise TrialsServiceError("ClinicalTrials.gov HTTP error") from exc
    except TimeoutError as exc:
        raise TrialsServiceError("ClinicalTrials.gov timed out") from exc
    except URLError as exc:
        raise TrialsServiceError("ClinicalTrials.gov was unreachable") from exc
    except OSError as exc:
        raise TrialsServiceError("ClinicalTrials.gov request failed") from exc

    if status is not None and int(status) != 200:
        raise TrialsServiceError("ClinicalTrials.gov returned a non-success status")

    return parse_search_body(raw, limit=cap)


def parse_search_body(raw: bytes | str, *, limit: int = DEFAULT_CAP) -> list[TrialStudy]:
    """Parse a CT.gov v2 studies JSON body. Fail-closed on malformed payloads."""
    if raw is None:
        raise TrialsServiceError("ClinicalTrials.gov returned an empty body")
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrialsServiceError("ClinicalTrials.gov body was not UTF-8") from exc
    else:
        text = raw
    text = text.strip()
    if not text:
        raise TrialsServiceError("ClinicalTrials.gov returned an empty body")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrialsServiceError("ClinicalTrials.gov body was not JSON") from exc
    if not isinstance(data, dict):
        raise TrialsServiceError("ClinicalTrials.gov JSON was not an object")
    if "studies" not in data:
        raise TrialsServiceError("ClinicalTrials.gov JSON lacked studies")
    rows = data.get("studies")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise TrialsServiceError("ClinicalTrials.gov studies were unparseable")

    cap = _clamp_limit(limit)
    out: list[TrialStudy] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        study = _study_from_row(row)
        if study is not None:
            out.append(study)
        if len(out) >= cap:
            break
    return out


def _clamp_limit(limit: int) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_CAP
    if n < 1:
        return DEFAULT_CAP
    return min(n, MAX_CAP)


def _sanitize_term(term: str) -> str:
    cleaned = (term or "").strip()
    # Keep alnum, spaces, and common gene/variant punctuation; drop the rest.
    cleaned = re.sub(r"[^\w\s.+*/\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:200]


def _study_from_row(row: dict[str, Any]) -> TrialStudy | None:
    proto = row.get("protocolSection")
    if not isinstance(proto, dict):
        return None
    ident = proto.get("identificationModule") or {}
    status_mod = proto.get("statusModule") or {}
    design = proto.get("designModule") or {}
    elig = proto.get("eligibilityModule") or {}
    cond_mod = proto.get("conditionsModule") or {}

    if not isinstance(ident, dict):
        return None
    nct = _plain(ident.get("nctId"))
    if not nct or not re.fullmatch(r"NCT\d+", nct, re.IGNORECASE):
        return None
    nct = nct.upper()
    title = _plain(ident.get("briefTitle")) or _plain(ident.get("officialTitle"))
    if not title:
        return None
    status = _plain(status_mod.get("overallStatus")) if isinstance(status_mod, dict) else ""
    if not status:
        status = "UNKNOWN"
    phase = _phase_of(design if isinstance(design, dict) else {})
    conditions = _conditions_of(cond_mod if isinstance(cond_mod, dict) else {})
    elig_raw = None
    if isinstance(elig, dict):
        elig_raw = _plain(elig.get("eligibilityCriteria")) or None
    inclusion, exclusion = _eligibility_themes(elig_raw)
    return TrialStudy(
        nct_id=nct,
        title=title,
        status=status,
        phase=phase,
        conditions=conditions,
        eligibility_raw=elig_raw,
        inclusion_themes=inclusion,
        exclusion_themes=exclusion,
    )


def _phase_of(design: dict[str, Any]) -> str | None:
    phases = design.get("phases")
    if isinstance(phases, list) and phases:
        labels: list[str] = []
        for p in phases:
            label = _format_phase(p)
            if label:
                labels.append(label)
        if labels:
            return ", ".join(labels)
    singular = _plain(design.get("phase"))
    if singular:
        return _format_phase(singular) or singular
    return None


def _format_phase(raw: Any) -> str | None:
    s = _plain(raw)
    if not s:
        return None
    key = s.upper().replace(" ", "")
    mapping = {
        "NA": "Not applicable",
        "NOTAPPLICABLE": "Not applicable",
        "EARLYPHASE1": "Early Phase 1",
        "PHASE1": "Phase 1",
        "PHASE2": "Phase 2",
        "PHASE3": "Phase 3",
        "PHASE4": "Phase 4",
    }
    if key in mapping:
        return mapping[key]
    m = re.fullmatch(r"PHASE\s*([1-4])", s, re.IGNORECASE)
    if m:
        return f"Phase {m.group(1)}"
    return s


def _conditions_of(cond_mod: dict[str, Any]) -> tuple[str, ...]:
    raw = cond_mod.get("conditions")
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        t = _plain(item)
        if t and t not in out:
            out.append(t)
        if len(out) >= 8:
            break
    return tuple(out)


def _eligibility_themes(raw: str | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract short inclusion/exclusion theme bullets from registry criteria text.

    Themes only — never frame as a determination that a person qualifies.
    """
    if not raw:
        return (), ()
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    inc_part = ""
    exc_part = ""
    lower = text.lower()
    inc_idx = lower.find("inclusion criteria")
    exc_idx = lower.find("exclusion criteria")
    if inc_idx >= 0 and exc_idx > inc_idx:
        inc_part = text[inc_idx:exc_idx]
        exc_part = text[exc_idx:]
    elif inc_idx >= 0:
        inc_part = text[inc_idx:]
    elif exc_idx >= 0:
        exc_part = text[exc_idx:]
    else:
        inc_part = text

    return (
        _theme_bullets(inc_part, limit=4),
        _theme_bullets(exc_part, limit=3),
    )


_BULLET_RE = re.compile(
    r"(?:^|\n)\s*(?:[\*\-•]|\d+[.)])\s*(.+?)(?=(?:\n\s*(?:[\*\-•]|\d+[.)]))|\n\n|$)",
    re.DOTALL,
)


def _theme_bullets(section: str, *, limit: int) -> tuple[str, ...]:
    if not section:
        return ()
    body = re.sub(
        r"(?i)^\s*(inclusion|exclusion)\s+criteria\s*:?\s*",
        "",
        section.strip(),
        count=1,
    )
    themes: list[str] = []
    for m in _BULLET_RE.finditer(body):
        theme = _compress_theme(m.group(1))
        if theme and theme not in themes:
            themes.append(theme)
        if len(themes) >= limit:
            break
    if not themes:
        chunk = _compress_theme(body)
        if chunk:
            themes.append(chunk)
    return tuple(themes[:limit])


def _compress_theme(raw: str) -> str:
    t = _plain(raw)
    t = re.sub(r"\s+", " ", t).strip(" .;")
    if not t:
        return ""
    if len(t) > 160:
        t = t[:157].rstrip() + "…"
    lower = t.lower()
    for banned in (
        "you are eligible",
        "you qualify",
        "enroll now",
        "we will enroll",
    ):
        if banned in lower:
            return ""
    return t


def _plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


__all__ = [
    "DEFAULT_CAP",
    "MAX_CAP",
    "TIMEOUT_SEC",
    "TrialStudy",
    "TrialsServiceError",
    "parse_search_body",
    "search_trials",
]
