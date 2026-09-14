"""Render the locked /evidence Markdown brief. Peer-reviewed; Harvard refs at bottom."""

from __future__ import annotations

from .research_client import Record
from .research_md import (
    _as_claim,
    _first_clause,
    harvard_reference,
    in_text_cite,
)

QUESTION_MAX_LEN = 400

SCOPE_DISCLAIMER = (
    "This brief summarises up to five peer-reviewed articles retrieved for the "
    "question above. It is for research use only and is not clinical advice."
)

SOURCES_LINE = (
    "Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded."
)

FINDINGS_ZERO = (
    "No peer-reviewed Europe PMC / MEDLINE articles matched this question "
    "at the time of search. No findings are listed, and no references are invented."
)

REFERENCES_ZERO = "None."

MSG_MISSING_QUESTION = (
    "Please provide a clinical or scientific question. "
    "Example: /evidence KRAS G12C inhibitors in NSCLC"
)

MSG_QUESTION_TOO_LONG = (
    "This question is too long for a single search. Please shorten it to a few clear "
    "phrases and try again."
)

MSG_FAIL_CLOSED = (
    "This request cannot proceed. The literature service did not respond safely, "
    "so no evidence brief was written. Please try again shortly."
)

CAPTION_HITS = (
    "Evidence brief for “{question}”: {n} peer-reviewed article(s). "
    "Research use only; not clinical advice."
)

CAPTION_ZERO = (
    "Evidence brief for “{question}”: no matching peer-reviewed articles found. "
    "Research use only; not clinical advice."
)

DOCUMENT_TEMPLATE = """\
# Evidence brief: {question}

{scope}
{sources}

## Findings

{findings_block}

## References

{references_block}
"""


def question_error(question: str) -> str | None:
    """Return the locked chat refuse string, or None if the question is usable."""
    if not (question or "").strip():
        return MSG_MISSING_QUESTION
    if len(question.strip()) > QUESTION_MAX_LEN:
        return MSG_QUESTION_TOO_LONG
    return None


def caption_for(question: str, n: int) -> str:
    if n <= 0:
        return CAPTION_ZERO.format(question=question)
    return CAPTION_HITS.format(question=question, n=n)


def render_evidence_md(question: str, records: list[Record]) -> str:
    # DOI lock: drop no-DOI from the rendered list (prefer fewer; never invent DOIs).
    records = [r for r in records if (r.doi or "").strip()]
    if not records:
        findings = FINDINGS_ZERO
        refs = REFERENCES_ZERO
    else:
        findings = "\n".join(_finding_bullet(rec) for rec in records)
        refs = "\n".join(harvard_reference(rec) for rec in records)
    return DOCUMENT_TEMPLATE.format(
        question=question,
        scope=SCOPE_DISCLAIMER,
        sources=SOURCES_LINE,
        findings_block=findings,
        references_block=refs,
    )


def _finding_bullet(rec: Record) -> str:
    """Result claim → cite. Never invent papers; never say preprint."""
    cite = in_text_cite(rec)
    abstract_clause = _first_clause(rec.abstract or "")
    if 20 <= len(abstract_clause) <= 280:
        return f"- {_as_claim(abstract_clause)} {cite}."
    title_clause = _first_clause(rec.title or "")
    if title_clause:
        return f"- {_as_claim(title_clause)} is reported {cite}."
    return f"- A matching peer-reviewed article was retrieved {cite}."
