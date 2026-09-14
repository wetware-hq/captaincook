"""Locked biolang copy and Markdown skeleton for /scribe.

Verbatim from docs/TEMPLATE-scribe.md (and COPY-scribe.md). Research-use only.
Unlinked: never read or write context card, biometric secrets, or patient files.
"""

from __future__ import annotations

import re
from pathlib import Path

SOURCE_MAX_CHARS = 12_000
SCRIBE_KEY = "scribe"

# --- Locked TEMPLATE-scribe.md (verbatim) ---
DISCLAIMER = (
    "This document organises user-supplied meeting text for research and "
    "documentation use only. It is not a legal medical record and is not clinical advice."
)

SOURCE_NOTE = (
    "Organised from user-supplied text; items not stated in the source were not added."
)

SYSTEM_PROMPT_CORE = (
    "You organise biomedical meeting notes into Markdown. Use only information "
    "present in the source text. Do not invent attendees, decisions, action items, "
    "clinical conclusions, or data. Write clear, complete sentences that a clinician "
    "and a well-educated patient can both understand. Prefer concise paragraphs and "
    "short bullets. Follow the user’s section skeleton exactly. Research-use / "
    "documentation aid only — not clinical advice and not a legal medical record. "
    "If something is uncertain or missing, state that plainly."
)

DOCUMENT_SKELETON = """\
# Meeting minutes

{disclaimer}

## Summary

{{summary_paragraph}}

## Decisions

{{decisions_block}}

## Action items

{{actions_block}}

## Discussion

{{discussion_block}}

## Open questions

{{questions_block}}

## Source note

{source_note}
""".format(disclaimer=DISCLAIMER, source_note=SOURCE_NOTE)

SYSTEM_PROMPT = (
    SYSTEM_PROMPT_CORE
    + "\n\nUse this section skeleton exactly. Always keep Summary and Source note. "
    "Omit Decisions, Action items, Discussion, or Open questions entirely when the "
    "source has no material for that section — do not write “None.” Action items: "
    "{who} — {what} — {when} only when those parts appear in the source; otherwise {what} alone.\n\n"
    + DOCUMENT_SKELETON
)

CAPTION = (
    "Meeting minutes organised from your text. Research use only; not a clinical record."
)

MSG_ARMED = (
    "Send the meeting notes or transcript in your next message. /scribe does not use "
    "the context card, biometric secrets, or patient files."
)

MSG_CANCELLED = "Scribe cancelled. No minutes were written."

MSG_EMPTY = (
    "Please provide meeting notes or a transcript. Example: /scribe then paste the text, "
    "or /scribe followed by a short note."
)

MSG_TOO_LONG = (
    "This text is too long for one pass. Please shorten it to 12000 characters or fewer "
    "and try again."
)

# Combined unset / down (TEMPLATE-scribe.md fail-closed)
MSG_FAIL_CLOSED = (
    "This request cannot proceed. The scribe service is not configured or did not "
    "respond safely, so no minutes were written. Please try again shortly or contact "
    "the operator."
)
MSG_NOT_CONFIGURED = MSG_FAIL_CLOSED

REQUIRED_SECTIONS = ("Summary", "Source note")
OPTIONAL_SECTIONS = ("Decisions", "Action items", "Discussion", "Open questions")
ALL_SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS

_SECTION_RE = re.compile(
    r"^##\s+(Summary|Decisions|Action items|Discussion|Open questions|Source note)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _docs_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    root = here.parent
    workspace = Path("/workspace")
    return [
        root / "docs" / "TEMPLATE-scribe.md",
        root / "docs" / "COPY-scribe.md",
        workspace / "TEMPLATE-scribe.md",
        workspace / "COPY-scribe.md",
        Path("docs/TEMPLATE-scribe.md"),
        Path("docs/COPY-scribe.md"),
    ]


def load_biolang_override() -> str | None:
    """Return verbatim TEMPLATE/COPY text if present (lock confirmation)."""
    for path in _docs_candidates():
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None


def system_prompt() -> str:
    """Fixed system prompt from TEMPLATE-scribe.md (+ skeleton)."""
    # Constants already mirror the template verbatim; override file is for audit/lock.
    return SYSTEM_PROMPT


def source_error(source: str) -> str | None:
    """Return locked refuse string, or None if source is usable."""
    text = source if source is not None else ""
    if not text.strip():
        return MSG_EMPTY
    if len(text) > SOURCE_MAX_CHARS:
        return MSG_TOO_LONG
    return None


def arm_scribe(user_data: dict) -> None:
    user_data[SCRIBE_KEY] = {"armed": True}


def end_scribe(user_data: dict) -> bool:
    """Disarm scribe without touching card/patient/files. Returns whether it was armed."""
    state = user_data.pop(SCRIBE_KEY, None)
    if isinstance(state, dict):
        return bool(state.get("armed"))
    return False


def is_armed(user_data: dict) -> bool:
    state = user_data.get(SCRIBE_KEY)
    return isinstance(state, dict) and bool(state.get("armed"))


def _norm_heading(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip().lower())
    mapping = {
        "summary": "Summary",
        "decisions": "Decisions",
        "action items": "Action items",
        "discussion": "Discussion",
        "open questions": "Open questions",
        "source note": "Source note",
    }
    return mapping.get(key, name.strip())


def _split_sections(body: str) -> dict[str, str]:
    """Parse ## sections from LLM Markdown. Keys are canonical section titles."""
    text = (body or "").strip()
    if not text:
        return {}
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        title = _norm_heading(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        out[title] = content
    return out


def _section_nonempty(content: str) -> bool:
    c = (content or "").strip()
    if not c:
        return False
    if re.fullmatch(r"(?i)(-?\s*)?(none\.?|n/?a\.?|—|-)", c):
        return False
    if re.fullmatch(r"(?i)(-\s*(none\.?|n/?a\.?)\s*)+", c):
        return False
    # Drop skeleton placeholders
    if re.fullmatch(r"(?i)\{[a-z_]+\}", c):
        return False
    return True


def ensure_skeleton(llm_markdown: str, *, source_excerpt: str | None = None) -> str:
    """Normalise LLM output into the locked TEMPLATE skeleton.

    Always keeps Summary and Source note. Omits empty optional sections.
    Does not invent decisions or attendees.
    """
    raw = (llm_markdown or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:markdown|md)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

    sections = _split_sections(raw)

    summary = sections.get("Summary", "").strip()
    if not summary or re.fullmatch(r"(?i)\{summary_paragraph\}", summary):
        paragraphs = [
            p.strip()
            for p in re.split(r"\n\s*\n", raw)
            if p.strip()
            and not p.strip().startswith("#")
            and p.strip() != DISCLAIMER
        ]
        summary = paragraphs[0] if paragraphs else (
            "The source text was organised without a separate summary block from the language service."
        )

    source_note = sections.get("Source note", "").strip() or SOURCE_NOTE
    if re.fullmatch(r"(?i)\{source_note\}", source_note):
        source_note = SOURCE_NOTE

    parts: list[str] = [
        "# Meeting minutes",
        "",
        DISCLAIMER,
        "",
        "## Summary",
        "",
        summary,
    ]

    for title in OPTIONAL_SECTIONS:
        content = sections.get(title, "").strip()
        if _section_nonempty(content):
            parts.extend(["", f"## {title}", "", content])

    parts.extend(["", "## Source note", "", source_note])
    return "\n".join(parts).rstrip() + "\n"
