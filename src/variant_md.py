"""Render the locked /variant Markdown brief. Thin wrapper on /evidence (MEDLINE).

Verbatim locked strings from docs/TEMPLATE-variant.md. Papers-first; no score block in v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .evidence_md import _finding_bullet
from .research_client import Record
from .research_md import harvard_reference

# --- Locked TEMPLATE-variant.md (verbatim) ---
SCOPE_DISCLAIMER = (
    "This brief summarises peer-reviewed literature for the gene and variant "
    "named above. It is for research use only. It is not a diagnosis, not a "
    "prognosis, and not treatment or dosing advice."
)

SCOPE_DISCLAIMER_ZERO = (
    "This brief is for research use only. It is not a diagnosis or treatment advice."
)

FINDINGS_ZERO = (
    "No peer-reviewed Europe PMC / MEDLINE articles matched this gene and "
    "variant at the time of search. No findings are listed, and no references "
    "are invented."
)

REFERENCES_ZERO = "None."

WHAT_NOT_PROVE = (
    "These articles do not establish a diagnosis or prognosis for any individual. "
    "They do not recommend a dose or treatment plan. Study designs, populations, "
    "and endpoints vary, so actionability cannot be inferred from this brief alone."
)

MSG_MISSING = (
    "Please name a gene and a variant. Example: /variant KRAS G12C"
)

MSG_FAIL_CLOSED = (
    "This request cannot proceed. The literature service did not respond safely, "
    "so no variant brief was written. Please try again shortly."
)

CAPTION = (
    "Variant brief for {gene} {change}: peer-reviewed literature only. "
    "Research use only; not a diagnosis."
)

DOCUMENT_TEMPLATE = """\
# Variant brief: {gene} {change}

{scope}

## What this variant is

{what_is}

## What the papers report

{papers_block}

## What the papers do not prove

{what_not}

## References

{references_block}
"""

DOCUMENT_TEMPLATE_ZERO = """\
# Variant brief: {gene} {change}

{scope}

## Findings

{findings}

## References

{references}
"""

# Telegram short-text threshold (FEATURE: reply_document or short text if tiny).
SHORT_BODY_MAX = 1200

# Protein / DNA change patterns (specialty-agnostic).
_CHANGE_RE = re.compile(
    r"(?:"
    r"p\.\s*[A-Za-z]{3}\d+[A-Za-z]{3}"  # p.Gly12Cys
    r"|p\.\s*[A-Z]\d+[A-Z*]"  # p.G12C
    r"|[A-Za-z]{3}\d+[A-Za-z]{3}"  # Gly12Cys
    r"|[A-Z]\d+[A-Z*]"  # G12C
    r"|c\.\d+[ACGT]>[ACGT]"  # c.35G>A
    r"|rs\d+"  # rs7412 (rare; still a 'change' token)
    r")",
    re.IGNORECASE,
)

# Gene symbol-ish token: letter start, 2–15 alnum / hyphen (not a change).
_GENE_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9-]{1,14})\b")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "for",
        "to",
        "with",
        "about",
        "what",
        "is",
        "are",
        "does",
        "do",
        "gene",
        "genes",
        "variant",
        "variants",
        "mutation",
        "mutations",
        "mutant",
        "protein",
        "amino",
        "acid",
        "change",
        "changes",
        "please",
        "tell",
        "me",
        "brief",
        "literature",
        "papers",
        "report",
        "reports",
        "wt",
        "wild",
        "type",
        "wildtype",
        "missense",
        "nonsense",
        "frameshift",
        "deletion",
        "insertion",
        "substitution",
        "snp",
        "snv",
        "dna",
        "rna",
        "cds",
        "exon",
        "intron",
        "codon",
        "residue",
        "position",
        "patient",
        "clinical",
        "oncology",
        "cancer",
        "disease",
        "therapy",
        "treatment",
        "inhibitor",
        "inhibitors",
    }
)

_ONE_LETTER_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")


@dataclass(frozen=True)
class ParsedVariant:
    gene: str
    change: str


def caption_for(gene: str, change: str) -> str:
    return CAPTION.format(gene=gene, change=change)


def parse_variant_args(
    args: list[str] | None,
    *,
    card_gene: str | None = None,
    card_variant: str | None = None,
) -> ParsedVariant | None:
    """Parse gene + change from structured/NL args, else card fields if both present.

    Bare /variant (no args) uses card gene/variant when both are set.
    Missing either → None (caller shows MSG_MISSING).
    """
    text = " ".join(args or []).strip()
    if not text:
        g = (card_gene or "").strip()
        c = (card_variant or "").strip()
        if g and c:
            return ParsedVariant(gene=_normalize_gene(g), change=_normalize_change(c))
        return None

    # Structured: first token gene-like, second change-like.
    tokens = text.split()
    if len(tokens) >= 2:
        g_cand = tokens[0]
        c_cand = tokens[1]
        if _looks_like_gene(g_cand) and _looks_like_change(c_cand):
            return ParsedVariant(
                gene=_normalize_gene(g_cand),
                change=_normalize_change(c_cand),
            )

    # NL: find a change token, then a gene token elsewhere (or before it).
    change_m = _CHANGE_RE.search(text)
    if change_m:
        change = _normalize_change(change_m.group(0))
        remainder = (text[: change_m.start()] + " " + text[change_m.end() :]).strip()
        gene = _find_gene_token(remainder)
        if gene:
            return ParsedVariant(gene=gene, change=change)

    # Two-token fallback when change regex missed (e.g. unusual notation).
    if len(tokens) == 2 and _looks_like_gene(tokens[0]):
        return ParsedVariant(
            gene=_normalize_gene(tokens[0]),
            change=_normalize_change(tokens[1]),
        )

    return None


def evidence_question(gene: str, change: str) -> str:
    """Query string for evidence_client.search_peer_reviewed."""
    return f"{gene} {change}"


def render_variant_md(gene: str, change: str, records: list[Record]) -> str:
    """Papers-first variant brief. No score / AlphaMissense / ClinVar block in v1."""
    records = [r for r in records if (r.doi or "").strip()]
    if not records:
        return DOCUMENT_TEMPLATE_ZERO.format(
            gene=gene,
            change=change,
            scope=SCOPE_DISCLAIMER_ZERO,
            findings=FINDINGS_ZERO,
            references=REFERENCES_ZERO,
        )
    papers = "\n".join(_finding_bullet(rec) for rec in records)
    refs = "\n".join(harvard_reference(rec) for rec in records)
    return DOCUMENT_TEMPLATE.format(
        gene=gene,
        change=change,
        scope=SCOPE_DISCLAIMER,
        what_is=_what_this_variant_is(gene, change),
        papers_block=papers,
        what_not=WHAT_NOT_PROVE,
        references_block=refs,
    )


def body_is_short(body: str) -> bool:
    return len(body or "") <= SHORT_BODY_MAX


def has_score_block(body: str) -> bool:
    """True if a v1-forbidden computational score subsection appears."""
    lower = (body or "").lower()
    if "## computational estimate" in lower:
        return True
    for needle in (
        "alphamissense",
        "clinvar",
        "esm variant",
        "pathogenicity score",
        "fm score",
    ):
        if needle in lower:
            return True
    return False


def _what_this_variant_is(gene: str, change: str) -> str:
    """One or two full sentences; molecular class from notation only — no clinical assertion."""
    kind = _molecular_class(change)
    if kind:
        return (
            f"This brief concerns {gene} with the change {change}, "
            f"described here as a {kind} notation at the sequence level. "
            f"No clinical meaning is asserted from the notation alone."
        )
    return (
        f"This brief concerns {gene} with the change {change}. "
        f"No clinical meaning is asserted from the notation alone."
    )


def _molecular_class(change: str) -> str | None:
    c = (change or "").strip()
    if not c:
        return None
    # p.Gly12Cys / Gly12Cys
    m3 = re.fullmatch(r"(?:p\.)?([A-Za-z]{3})(\d+)([A-Za-z]{3})", c, re.IGNORECASE)
    if m3:
        a, _pos, b = m3.group(1), m3.group(2), m3.group(3)
        if a.lower() != b.lower():
            return "protein substitution (missense-style)"
        return "protein notation"
    # p.G12C / G12C / G12*
    m1 = re.fullmatch(r"(?:p\.)?([A-Z])(\d+)([A-Z*])", c, re.IGNORECASE)
    if m1:
        a, _pos, b = m1.group(1).upper(), m1.group(2), m1.group(3).upper()
        if b == "*":
            return "protein nonsense-style"
        if a in _ONE_LETTER_AA and b in _ONE_LETTER_AA and a != b:
            return "protein substitution (missense-style)"
        return "protein notation"
    if re.fullmatch(r"c\.\d+[ACGTacgt]>[ACGTacgt]", c):
        return "coding DNA substitution"
    if re.fullmatch(r"rs\d+", c, re.IGNORECASE):
        return "dbSNP identifier"
    return None


def _normalize_gene(raw: str) -> str:
    g = (raw or "").strip().upper().replace("_", "-")
    # Collapse accidental spaces.
    g = re.sub(r"\s+", "", g)
    return g


def _normalize_change(raw: str) -> str:
    c = (raw or "").strip()
    c = re.sub(r"\s+", "", c)
    # Prefer canonical p. prefix spacing: p.G12C
    if c.lower().startswith("p."):
        rest = c[2:]
        # Three-letter HGVS keeps mixed case; one-letter uppercases.
        if re.fullmatch(r"[A-Za-z]{3}\d+[A-Za-z]{3}", rest):
            return "p." + _title_three_letter(rest)
        return "p." + rest.upper()
    if re.fullmatch(r"[A-Za-z]{3}\d+[A-Za-z]{3}", c):
        return _title_three_letter(c)
    if re.fullmatch(r"c\.\d+[ACGTacgt]>[ACGTacgt]", c):
        return "c." + c[2:].upper()
    if re.fullmatch(r"rs\d+", c, re.IGNORECASE):
        return c.lower()
    # Default: uppercase protein one-letter forms.
    return c.upper()


def _title_three_letter(raw: str) -> str:
    m = re.fullmatch(r"([A-Za-z]{3})(\d+)([A-Za-z]{3})", raw)
    if not m:
        return raw
    a, pos, b = m.group(1), m.group(2), m.group(3)
    return f"{a.capitalize()}{pos}{b.capitalize()}"


def _looks_like_change(token: str) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    if _CHANGE_RE.fullmatch(t):
        return True
    # Accept bare tokens that are clearly protein changes even if regex edge-misses.
    return bool(re.fullmatch(r"(?:p\.)?[A-Z]\d+[A-Z*]", t, re.IGNORECASE))


def _looks_like_gene(token: str) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    if _looks_like_change(t):
        return False
    key = t.lower().replace("-", "")
    if key in _STOPWORDS:
        return False
    if not _GENE_TOKEN_RE.fullmatch(t):
        return False
    # Reject pure numbers / very short.
    if t.isdigit() or len(t) < 2:
        return False
    return True


def _find_gene_token(text: str) -> str | None:
    for m in _GENE_TOKEN_RE.finditer(text or ""):
        tok = m.group(1)
        if _looks_like_gene(tok):
            return _normalize_gene(tok)
    return None


# Re-export for tests / callers that introspect card-shaped dicts.
def gene_change_from_card(card: Any) -> ParsedVariant | None:
    if card is None:
        return None
    gene = getattr(card, "gene", None) or (card.get("gene") if isinstance(card, dict) else None)
    variant = getattr(card, "variant", None) or (
        card.get("variant") if isinstance(card, dict) else None
    )
    return parse_variant_args([], card_gene=gene, card_variant=variant)


__all__ = [
    "CAPTION",
    "FINDINGS_ZERO",
    "MSG_FAIL_CLOSED",
    "MSG_MISSING",
    "ParsedVariant",
    "REFERENCES_ZERO",
    "WHAT_NOT_PROVE",
    "body_is_short",
    "caption_for",
    "evidence_question",
    "gene_change_from_card",
    "has_score_block",
    "parse_variant_args",
    "render_variant_md",
]
