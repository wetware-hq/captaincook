"""Render the locked biolang /research Markdown document. Do not invent strings."""

from __future__ import annotations

from .research_client import Author, Record, _doi_url

TOPIC_MAX_LEN = 300

SCOPE_DISCLAIMER = (
    "This brief summarises up to five recent bioRxiv or medRxiv preprints "
    "retrieved for the topic above. It is for research use only and is not clinical advice."
)

SOCIAL_SIGNAL_LINE = "Social (X) signal was not available in this version."

FINDINGS_ZERO = (
    "No recent bioRxiv or medRxiv preprints matched this topic in Europe PMC "
    "at the time of search. No findings are listed, and no references are invented."
)

REFERENCES_ZERO = "None."

MSG_MISSING_TOPIC = (
    "Please provide a research topic. Example: /research KRAS G12C covalent inhibitors"
)

MSG_TOPIC_TOO_LONG = (
    "This topic is too long for a single search. Please shorten it to a few clear "
    "phrases and try again."
)

MSG_FAIL_CLOSED = (
    "This request cannot proceed. The literature service did not respond safely, "
    "so no research brief was written. Please try again shortly."
)

CAPTION_HITS = (
    "Research brief for “{topic}”: {n} recent preprint(s). "
    "Research use only; not clinical advice."
)

CAPTION_ZERO = (
    "Research brief for “{topic}”: no matching preprints found. "
    "Research use only; not clinical advice."
)

DOCUMENT_TEMPLATE = """\
# Research brief: {topic}

{scope}

## Findings

{findings_block}

## Social signal

{social}

## References

{references_block}
"""


def topic_error(topic: str) -> str | None:
    """Return the locked chat refuse string, or None if the topic is usable."""
    if not (topic or "").strip():
        return MSG_MISSING_TOPIC
    if len(topic.strip()) > TOPIC_MAX_LEN:
        return MSG_TOPIC_TOO_LONG
    return None


def caption_for(topic: str, n: int) -> str:
    if n <= 0:
        return CAPTION_ZERO.format(topic=topic)
    return CAPTION_HITS.format(topic=topic, n=n)


def render_research_md(topic: str, records: list[Record]) -> str:
    if not records:
        findings = FINDINGS_ZERO
        refs = REFERENCES_ZERO
    else:
        findings = "\n".join(_finding_bullet(rec) for rec in records)
        refs = "\n".join(harvard_reference(rec) for rec in records)
    return DOCUMENT_TEMPLATE.format(
        topic=topic,
        scope=SCOPE_DISCLAIMER,
        findings_block=findings,
        social=SOCIAL_SIGNAL_LINE,
        references_block=refs,
    )


def harvard_reference(rec: Record) -> str:
    """{Family}, {Initials}., {Year}. {Title}. {Server}. {DOI_or_URL}"""
    authors = _harvard_authors(rec.authors)
    title = rec.title.rstrip()
    if title and not title.endswith("."):
        title_part = f"{title}."
    else:
        title_part = title or "Untitled."
    loc = _doi_or_url(rec)
    server = rec.server or "preprint"
    if rec.year:
        head = f"{authors}, {rec.year}. {title_part} {server}."
    elif authors:
        head = f"{authors}. {title_part} {server}."
    else:
        head = f"{title_part} {server}."
    if loc:
        return f"{head} {loc}"
    return head


def in_text_cite(rec: Record) -> str:
    """Harvard author–year pointer, e.g. (Smith et al., 2024)."""
    year = rec.year
    if not rec.authors:
        who = "Anonymous"
    elif len(rec.authors) == 1:
        who = rec.authors[0].family
    elif len(rec.authors) == 2:
        who = f"{rec.authors[0].family} and {rec.authors[1].family}"
    else:
        who = f"{rec.authors[0].family} et al."
    if year:
        return f"({who}, {year})"
    return f"({who})"


def _harvard_authors(authors: tuple[Author, ...] | list[Author]) -> str:
    people = list(authors)
    if not people:
        return "Anonymous"
    extra = False
    if len(people) > 3:
        people = people[:3]
        extra = True
    parts: list[str] = []
    for person in people:
        family = person.family.strip() or "Anonymous"
        initials = (person.initials or "").strip().rstrip(".")
        if initials:
            parts.append(f"{family}, {initials}.")
        else:
            parts.append(f"{family}")
    body = ", ".join(parts)
    if extra:
        body = f"{body}, et al."
    return body


def _doi_or_url(rec: Record) -> str:
    if rec.doi:
        return _doi_url(rec.doi)
    return (rec.url or "").strip()


_JUNK_PREFIXES = (
    "summary",
    "abstract",
    "in this work, we",
    "in this work we",
    "here we",
    "here, we",
)


def _strip_leading_junk(text: str) -> str:
    """Drop leading summary/abstract boilerplate. Do not invent content."""
    t = (text or "").strip()
    changed = True
    while t and changed:
        changed = False
        low = t.lower()
        for prefix in _JUNK_PREFIXES:
            if low.startswith(prefix):
                t = t[len(prefix) :].lstrip(" :-")
                changed = True
                break
    return t


def _first_clause(text: str) -> str:
    t = _strip_leading_junk(text)
    if not t:
        return ""
    return t.split(".")[0].strip()


def _as_claim(clause: str) -> str:
    c = clause.rstrip(".").strip()
    if not c:
        return ""
    if c[0].islower():
        return c[0].upper() + c[1:]
    return c


def _finding_bullet(rec: Record) -> str:
    """Result claim → cite. Never 'This preprint is about {title}'."""
    cite = in_text_cite(rec)
    abstract_clause = _first_clause(rec.abstract or "")
    if 20 <= len(abstract_clause) <= 280:
        return f"- {_as_claim(abstract_clause)} {cite}."
    title_clause = _first_clause(rec.title or "")
    if title_clause:
        return f"- {_as_claim(title_clause)} is reported {cite}."
    return f"- A matching preprint was retrieved {cite}."
