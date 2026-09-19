"""Render the locked /trials Markdown shortlist.

Verbatim strings from docs/TEMPLATE-trials.md. Never invents studies.
Never frames eligibility themes as a determination that someone qualifies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .trials_client import DEFAULT_CAP, MAX_CAP, TrialStudy

# --- Locked TEMPLATE-trials.md (verbatim) ---
SCOPE_DISCLAIMER = 'This document lists public studies from ClinicalTrials.gov that may relate to the query or card context below. It is for research use only. A human must review every study. This bot does not determine eligibility, does not enroll anyone, and does not contact sponsors.'

STUDIES_ZERO = 'No public ClinicalTrials.gov studies matched this query at the time of search. No studies are listed, and none are invented.'

SOURCE_NOTE = 'Retrieved from ClinicalTrials.gov API v2 at search time. Counts are capped (≤10). Status and eligibility text can change on the registry — always open the study link before acting.'

MSG_MISSING = 'Please name a condition, gene, or variant, or /load a card first. Example: /trials KRAS G12C'

MSG_FAIL_CLOSED = 'This request cannot proceed. The clinical trials registry did not respond safely, so no shortlist was written. Please try again shortly.'

CAPTION_HITS = 'Trials shortlist: {n} public ClinicalTrials.gov study(ies). Research use only; human review required; this bot does not enroll.'

CAPTION_ZERO = 'Trials shortlist: no matching public studies found. Research use only; this bot does not enroll.'

HELP_LINE = '/trials [condition or gene variant] — Shortlist public ClinicalTrials.gov studies for the card or query. Eligibility themes only. Research use only; human review required; this bot does not enroll.'

DOCUMENT_TEMPLATE = '# Trials shortlist\n\nThis document lists public studies from ClinicalTrials.gov that may relate to the query or card context below. It is for research use only. A human must review every study. This bot does not determine eligibility, does not enroll anyone, and does not contact sponsors.\n\n**Query / context:** {query_summary}\n\n## Studies\n\n{studies_block}\n\n## Source note\n\nRetrieved from ClinicalTrials.gov API v2 at search time. Counts are capped (≤10). Status and eligibility text can change on the registry — always open the study link before acting.'

STUDY_UNIT = '### {n}. {official_title}\n\n- **NCT:** {nct_id}\n- **Status:** {overall_status}\n- **Phase:** {phase_or_not_applicable}\n- **Why it matched:** {why_matched}\n- **Eligibility themes:** {eligibility_themes}\n- **Registry:** https://clinicaltrials.gov/study/{nct_id}'

PHASE_NOT_APPLICABLE = "Not applicable"

# Telegram short-text threshold (FEATURE: reply_document or short text if tiny).
SHORT_BODY_MAX = 1200

_BANNED_PHRASE_RE = re.compile(
    r"you are eligible|you qualify|enroll now|we will enroll|"
    r"recommended trial for this patient",
    re.IGNORECASE,
)

_CHANGE_RE = re.compile(
    r"(?:"
    r"p\.\s*[A-Za-z]{3}\d+[A-Za-z]{3}"
    r"|p\.\s*[A-Z]\d+[A-Z*]"
    r"|[A-Za-z]{3}\d+[A-Za-z]{3}"
    r"|[A-Z]\d+[A-Z*]"
    r"|c\.\d+[ACGT]>[ACGT]"
    r"|rs\d+"
    r")",
    re.IGNORECASE,
)

_GENE_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9-]{1,14})\b")

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with",
        "about", "what", "is", "are", "gene", "genes", "variant", "variants",
        "mutation", "mutations", "mutant", "condition", "disease", "trial",
        "trials", "study", "studies", "clinical", "please", "find", "show",
        "list", "search", "patient", "therapy", "treatment",
    }
)


@dataclass(frozen=True)
class ParsedTrialsQuery:
    """Themes used for CT.gov query.term — never biometrics / PHI."""

    term: str
    gene: str | None = None
    variant: str | None = None
    condition: str | None = None
    summary: str = ""


def caption_for(n_studies: int) -> str:
    if n_studies <= 0:
        return CAPTION_ZERO
    return CAPTION_HITS.format(n=n_studies)


def parse_trials_args(
    args: list[str] | None,
    *,
    card_gene: str | None = None,
    card_variant: str | None = None,
    card_condition: str | None = None,
) -> ParsedTrialsQuery | None:
    """Parse NL condition / gene+variant, else card gene/variant/condition if present.

    Bare /trials uses card fields when any of gene, variant, or condition is set.
    Missing all → None (caller shows MSG_MISSING).
    """
    text = " ".join(args or []).strip()
    if text:
        return _parse_nl(text)

    gene = (card_gene or "").strip() or None
    variant = (card_variant or "").strip() or None
    condition = (card_condition or "").strip() or None
    if not gene and not variant and not condition:
        return None

    parts: list[str] = []
    if gene:
        parts.append(_normalize_gene(gene))
    if variant:
        parts.append(_normalize_change(variant))
    if condition and condition.lower() not in {p.lower() for p in parts}:
        parts.append(condition)
    term = " ".join(parts).strip()
    if not term:
        return None
    summary = _summary_from_parts(
        gene=_normalize_gene(gene) if gene else None,
        variant=_normalize_change(variant) if variant else None,
        condition=condition,
        source="card",
    )
    return ParsedTrialsQuery(
        term=term,
        gene=_normalize_gene(gene) if gene else None,
        variant=_normalize_change(variant) if variant else None,
        condition=condition,
        summary=summary,
    )


def render_trials_md(query: ParsedTrialsQuery, studies: list[TrialStudy]) -> str:
    """Locked TEMPLATE document. Never invents studies; never eligibility determinations."""
    studies = list(studies or [])[:MAX_CAP]
    if not studies:
        studies_block = STUDIES_ZERO
    else:
        units = [
            _render_study_unit(i + 1, study, query) for i, study in enumerate(studies)
        ]
        studies_block = "\n\n".join(units)
    body = DOCUMENT_TEMPLATE.format(
        query_summary=query.summary or query.term,
        studies_block=studies_block,
    )
    if _BANNED_PHRASE_RE.search(body):
        body = _BANNED_PHRASE_RE.sub("[redacted]", body)
    return body


def body_is_short(body: str) -> bool:
    return len(body or "") <= SHORT_BODY_MAX


def has_enroll_language(body: str) -> bool:
    """True if banned enroll / eligibility-determination phrasing appears."""
    return bool(_BANNED_PHRASE_RE.search(body or ""))


def clamp_limit(raw: int | None = None) -> int:
    if raw is None:
        return DEFAULT_CAP
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CAP
    if n < 1:
        return DEFAULT_CAP
    return min(n, MAX_CAP)


def _render_study_unit(n: int, study: TrialStudy, query: ParsedTrialsQuery) -> str:
    phase = study.phase or PHASE_NOT_APPLICABLE
    why = _why_matched(study, query)
    elig = _eligibility_themes_md(study)
    return STUDY_UNIT.format(
        n=n,
        official_title=study.title.strip(),
        nct_id=study.nct_id,
        overall_status=study.status,
        phase_or_not_applicable=phase,
        why_matched=why,
        eligibility_themes=elig,
    )


def _why_matched(study: TrialStudy, query: ParsedTrialsQuery) -> str:
    """One or two full sentences on gene/variant/condition themes — no eligibility verdict."""
    bits: list[str] = []
    if query.gene and query.variant:
        bits.append(f"The search themes were {query.gene} and {query.variant}.")
    elif query.gene:
        bits.append(f"The search theme included the gene {query.gene}.")
    elif query.variant:
        bits.append(f"The search theme included the change {query.variant}.")
    if query.condition:
        bits.append(f"A condition theme was {query.condition}.")
    if not bits:
        bits.append(f"The search theme was {query.term}.")

    conds = [c for c in study.conditions if c]
    if conds:
        shown = ", ".join(conds[:3])
        bits.append(f"The registry lists related condition theme(s): {shown}.")
    else:
        bits.append(
            "The registry title or keywords aligned with those search themes."
        )
    text = " ".join(bits)
    if _BANNED_PHRASE_RE.search(text):
        return "The registry entry aligned with the stated search themes."
    return text


def _eligibility_themes_md(study: TrialStudy) -> str:
    """Short bullets of inclusion/exclusion themes — never 'you qualify'."""
    lines: list[str] = []
    for theme in study.inclusion_themes:
        if theme and not _BANNED_PHRASE_RE.search(theme):
            lines.append(f"inclusion theme — {theme}")
    for theme in study.exclusion_themes:
        if theme and not _BANNED_PHRASE_RE.search(theme):
            lines.append(f"exclusion theme — {theme}")
    if not lines:
        return (
            "Registry eligibility text did not yield short themes at parse time; "
            "open the study link for the full criteria."
        )
    return "; ".join(lines)


def _parse_nl(text: str) -> ParsedTrialsQuery:
    tokens = text.split()
    gene: str | None = None
    variant: str | None = None
    condition: str | None = None

    if len(tokens) >= 2 and _looks_like_gene(tokens[0]) and _looks_like_change(tokens[1]):
        gene = _normalize_gene(tokens[0])
        variant = _normalize_change(tokens[1])
        rest = " ".join(tokens[2:]).strip()
        if rest:
            condition = rest
    else:
        change_m = _CHANGE_RE.search(text)
        if change_m:
            variant = _normalize_change(change_m.group(0))
            remainder = (text[: change_m.start()] + " " + text[change_m.end() :]).strip()
            gene = _find_gene_token(remainder)
            leftover = remainder
            if gene:
                leftover = re.sub(re.escape(gene), " ", leftover, flags=re.IGNORECASE)
            leftover = _strip_stopwords(leftover)
            if leftover:
                condition = leftover
        else:
            condition = text.strip()
            maybe_gene = _find_gene_token(text)
            if maybe_gene and len(tokens) <= 3:
                gene = maybe_gene

    parts: list[str] = []
    if gene:
        parts.append(gene)
    if variant:
        parts.append(variant)
    if condition:
        cond_bits = [
            w
            for w in condition.split()
            if w.upper() not in {p.upper() for p in parts}
        ]
        if cond_bits:
            parts.extend(cond_bits)
        elif not parts:
            parts.append(condition)
    term = " ".join(parts).strip() or text.strip()
    summary = _summary_from_parts(
        gene=gene, variant=variant, condition=condition, source="query"
    )
    return ParsedTrialsQuery(
        term=term,
        gene=gene,
        variant=variant,
        condition=condition,
        summary=summary,
    )


def _summary_from_parts(
    *,
    gene: str | None,
    variant: str | None,
    condition: str | None,
    source: str,
) -> str:
    bits: list[str] = []
    if gene and variant:
        bits.append(f"{gene} {variant}")
    elif gene:
        bits.append(gene)
    elif variant:
        bits.append(variant)
    if condition:
        bits.append(condition)
    joined = "; ".join(bits) if bits else "unspecified"
    if source == "card":
        return f"card context — {joined}"
    return f"query — {joined}"


def _normalize_gene(raw: str) -> str:
    g = (raw or "").strip().upper().replace("_", "-")
    return re.sub(r"\s+", "", g)


def _normalize_change(raw: str) -> str:
    c = (raw or "").strip()
    c = re.sub(r"\s+", "", c)
    if c.lower().startswith("p."):
        rest = c[2:]
        if re.fullmatch(r"[A-Za-z]{3}\d+[A-Za-z]{3}", rest):
            return "p." + _title_three_letter(rest)
        return "p." + rest.upper()
    if re.fullmatch(r"[A-Za-z]{3}\d+[A-Za-z]{3}", c):
        return _title_three_letter(c)
    if re.fullmatch(r"c\.\d+[ACGTacgt]>[ACGTacgt]", c):
        return "c." + c[2:].upper()
    if re.fullmatch(r"rs\d+", c, re.IGNORECASE):
        return c.lower()
    return c.upper()


def _title_three_letter(raw: str) -> str:
    m = re.fullmatch(r"([A-Za-z]{3})(\d+)([A-Za-z]{3})", raw)
    if not m:
        return raw
    return f"{m.group(1).capitalize()}{m.group(2)}{m.group(3).capitalize()}"


def _looks_like_change(token: str) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    if _CHANGE_RE.fullmatch(t):
        return True
    return bool(re.fullmatch(r"(?:p\.)?[A-Z]\d+[A-Z*]", t, re.IGNORECASE))


def _looks_like_gene(token: str) -> bool:
    t = (token or "").strip()
    if not t or _looks_like_change(t):
        return False
    key = t.lower().replace("-", "")
    if key in _STOPWORDS:
        return False
    if not _GENE_TOKEN_RE.fullmatch(t):
        return False
    if t.isdigit() or len(t) < 2:
        return False
    return True


def _find_gene_token(text: str) -> str | None:
    for m in _GENE_TOKEN_RE.finditer(text or ""):
        tok = m.group(1)
        if _looks_like_gene(tok):
            return _normalize_gene(tok)
    return None


def _strip_stopwords(text: str) -> str:
    words = [
        w
        for w in (text or "").split()
        if w.lower().replace("-", "") not in _STOPWORDS and not _looks_like_gene(w)
    ]
    return " ".join(words).strip()


def query_from_card(card: Any) -> ParsedTrialsQuery | None:
    if card is None:
        return None
    gene = getattr(card, "gene", None) or (
        card.get("gene") if isinstance(card, dict) else None
    )
    variant = getattr(card, "variant", None) or (
        card.get("variant") if isinstance(card, dict) else None
    )
    condition = getattr(card, "condition", None) or (
        card.get("condition") if isinstance(card, dict) else None
    )
    return parse_trials_args(
        [], card_gene=gene, card_variant=variant, card_condition=condition
    )


__all__ = [
    "CAPTION_HITS",
    "CAPTION_ZERO",
    "HELP_LINE",
    "MSG_FAIL_CLOSED",
    "MSG_MISSING",
    "PHASE_NOT_APPLICABLE",
    "SCOPE_DISCLAIMER",
    "SOURCE_NOTE",
    "STUDIES_ZERO",
    "ParsedTrialsQuery",
    "body_is_short",
    "caption_for",
    "clamp_limit",
    "has_enroll_language",
    "parse_trials_args",
    "query_from_card",
    "render_trials_md",
]
