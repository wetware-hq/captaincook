"""Assemble /board Markdown packet from session stores.

Verbatim locked strings from docs/TEMPLATE-board.md. Research-use only.
Never echo biometric secrets, note bodies, or secret measure values. Never invent evidence or designs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import onboard as onboard_mod
from . import patient_files as patient_files_mod
from . import measure as measure_mod
from . import store
from .context_card import CONTEXT_CARD_KEY, ContextCard, load_card

# --- Locked TEMPLATE-board.md (verbatim) ---
DISCLAIMER = (
    "This packet assembles the current session stores for a case conference or "
    "molecular board discussion. It is for research use only. It is not a clinical "
    "record, not a diagnosis, and not treatment advice."
)

SOURCE_NOTE = (
    "Assembled from session stores only; nothing was inferred beyond the listed fields."
)

EVIDENCE_NONE = (
    "None yet. Run /evidence with a clear clinical or scientific question."
)

EVIDENCE_PREPRINT_ONLY = (
    "No peer-reviewed evidence brief on file yet. A preprint research brief is "
    "available from /research (not a substitute for /evidence)."
)

LAB_NONE = (
    "None yet. Run /design ligand or /design binder after /load "
    "(and a structure for binders)."
)

OPEN_NONE_GAPS = (
    "No open session gaps were detected from the stores listed above."
)

CAPTION = (
    "Board packet for this session. Research use only; not a clinical record."
)

# --- Locked TEMPLATE-measure.md board stubs (verbatim) ---
BOARD_MEASURE_NONE = "None yet. Paste observations with /measure."
BOARD_MEASURE_SECRET_STUB = "Secret measures on file: {n} (values not shown)."

MSG_REFUSE = (
    "This request cannot proceed. There is no context card and no patient on "
    "file to assemble a board packet. Please /load a case or /onboard a patient first."
)

LAB_RESEARCH_LINE = (
    "In-silico design for research use only; not a validated therapeutic and "
    "not laboratory guidance."
)

_DESIGN_TAG_RE = re.compile(r"^(ligand|binder):(.+)$", re.IGNORECASE)
_SECTION_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def has_board_inputs(user_data: dict[str, Any] | None) -> bool:
    """True when a context card shell or patient block exists (enough to assemble)."""
    if not user_data:
        return False
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return False
    # Formal card fields or patient block both count.
    card = load_card(user_data)
    if card is not None and (
        (card.raw_text or "").strip()
        or card.gene
        or card.variant
        or card.sequence
        or card.intent != "unspecified"
        or card.last_run
    ):
        return True
    patient = raw.get("patient")
    if isinstance(patient, dict):
        return True
    files = raw.get("patient_files")
    if isinstance(files, list) and files:
        return True
    measures = raw.get("measurements")
    if isinstance(measures, list) and measures:
        return True
    return False


def biometrics_label(user_data: dict[str, Any] | None) -> str:
    """Return on file | incomplete | none — never raw values."""
    if not user_data:
        return "none"
    patient = onboard_mod.get_patient(user_data)
    if not patient or all(patient.get(k) is None for k in onboard_mod.FIELD_ORDER):
        return "none"
    if patient.get("complete") and not onboard_mod.missing_fields(patient):
        return "on file"
    return "incomplete"


def patient_files_count(user_data: dict[str, Any] | None) -> int:
    if not user_data:
        return 0
    return len(patient_files_mod.get_patient_files(user_data))


def _gene_variant_line(card: ContextCard | None) -> str:
    if card is None:
        return "none"
    gene = (card.gene or "").strip()
    variant = (card.variant or "").strip()
    if gene and variant:
        return f"{gene} {variant}"
    if gene:
        return gene
    if variant:
        return variant
    return "none"


def _intent_line(card: ContextCard | None) -> str:
    if card is None:
        return "none"
    intent = (card.intent or "").strip()
    if not intent or intent == "unspecified":
        # Fall back to raw_text snippet if present (no inventing).
        raw = (card.raw_text or "").strip()
        if raw:
            return raw if len(raw) <= 120 else raw[:117] + "..."
        return "none"
    return intent.replace("_", " ")


def _section_body(md: str, header: str) -> str | None:
    matches = list(_SECTION_HEADER_RE.finditer(md))
    if not matches:
        return None
    for i, m in enumerate(matches):
        if m.group(1).strip() == header:
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
            return md[start:end].strip()
    return None


def _evidence_from_clinic(user_id: int | str | None, patient_id: str | None) -> str | None:
    if user_id is None or not patient_id:
        return None
    path = store.clinic_path(user_id, patient_id)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    body = _section_body(text, "Evidence")
    if not body:
        return None
    # Empty section skeleton → treat as none.
    stripped = body.strip()
    if not stripped or stripped in ("_", "-", "None.", "None"):
        return None
    # Require at least one bullet, DOI heading, or reference-ish content.
    if not re.search(r"(^|\n)\s*([-*]|\d+\.|###|DOI|10\.\d{4,})", stripped):
        # Still allow multi-line prose findings.
        if len(stripped) < 40:
            return None
    return stripped


def _evidence_from_last_run(card: ContextCard | None) -> str | None:
    if card is None or not isinstance(card.last_run, dict):
        return None
    lr = card.last_run
    kind = str(lr.get("kind") or "").lower()
    brief = lr.get("evidence_brief_md") or lr.get("brief_md")
    if kind in ("evidence", "evidence_brief") and isinstance(brief, str) and brief.strip():
        return brief.strip()
    if isinstance(brief, str) and brief.strip() and "peer-reviewed" in brief.lower():
        return brief.strip()
    return None


def _research_on_file(user_id: int | str | None, patient_id: str | None, card: ContextCard | None) -> bool:
    if card is not None and isinstance(card.last_run, dict):
        lr = card.last_run
        kind = str(lr.get("kind") or "").lower()
        if kind in ("research", "research_brief"):
            return True
        brief = lr.get("research_brief_md")
        if isinstance(brief, str) and brief.strip():
            return True
    if user_id is None or not patient_id:
        return False
    path = store.lab_path(user_id, patient_id)
    if not path.is_file():
        return False
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for cell in nb.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        tags = [str(t) for t in (cell.get("metadata") or {}).get("tags") or []]
        if any(t.lower().startswith("research") for t in tags):
            return True
        src = cell.get("source") or []
        text = "".join(src) if isinstance(src, list) else str(src)
        if "preprint" in text.lower() and "research" in text.lower():
            return True
    return False


def _designs_from_lab(user_id: int | str | None, patient_id: str | None) -> list[tuple[str, str]]:
    """Return [(mode, design_id), ...] from lab.ipynb cell tags."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    if user_id is None or not patient_id:
        return out
    path = store.lab_path(user_id, patient_id)
    if not path.is_file():
        return out
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for cell in nb.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        tags = [str(t) for t in (cell.get("metadata") or {}).get("tags") or []]
        for tag in tags:
            m = _DESIGN_TAG_RE.match(tag.strip())
            if not m:
                continue
            mode = m.group(1).lower()
            design_id = m.group(2).strip()
            if not design_id or design_id in ("design", "confirm"):
                # Prefer real design-ids; skip kind-only stubs unless nothing else.
                key = f"{mode}:{design_id}"
                if key in seen:
                    continue
                seen.add(key)
                out.append((mode, design_id))
                continue
            key = f"{mode}:{design_id}"
            if key in seen:
                continue
            seen.add(key)
            out.append((mode, design_id))
    return out


def _designs_from_search(user_id: int | str | None, patient_id: str | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    if user_id is None or not patient_id:
        return out
    path = store.search_path(user_id, patient_id)
    if not path.is_file():
        return out
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for entry in obj.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for field in ("title", "section", "doi", "id", "key"):
            val = str(entry.get(field) or "")
            m = _DESIGN_TAG_RE.search(val)
            if m:
                mode = m.group(1).lower()
                design_id = m.group(2).strip()
                key = f"{mode}:{design_id}"
                if design_id and key not in seen:
                    seen.add(key)
                    out.append((mode, design_id))
        tokens = entry.get("tokens") or []
        joined = " ".join(str(t) for t in tokens)
        for m in _DESIGN_TAG_RE.finditer(joined):
            mode = m.group(1).lower()
            design_id = m.group(2).strip().split()[0]
            key = f"{mode}:{design_id}"
            if design_id and key not in seen:
                seen.add(key)
                out.append((mode, design_id))
    return out


def _designs_from_last_run(card: ContextCard | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if card is None or not isinstance(card.last_run, dict):
        return out
    lr = card.last_run
    kind = str(lr.get("kind") or "").lower()
    run_id = lr.get("run_id") or lr.get("design_id")
    if not run_id:
        return out
    design_id = str(run_id).strip()
    if not design_id:
        return out
    if kind in ("binder_design", "binder", "bindcraft"):
        out.append(("binder", design_id))
    elif kind in ("design", "ligand_design", "small_molecule_design", "ligand"):
        out.append(("ligand", design_id))
    elif "binder" in kind:
        out.append(("binder", design_id))
    elif "ligand" in kind or "design" in kind:
        out.append(("ligand", design_id))
    return out


def collect_designs(
    user_data: dict[str, Any] | None,
    *,
    user_id: int | str | None = None,
    patient_id: str | None = None,
) -> list[tuple[str, str]]:
    """Latest ligand:/binder: design-ids from card last_run, lab, and search.json."""
    card = load_card(user_data) if user_data else None
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source in (
        _designs_from_last_run(card),
        _designs_from_lab(user_id, patient_id),
        _designs_from_search(user_id, patient_id),
    ):
        for mode, design_id in source:
            key = f"{mode}:{design_id}"
            if key in seen:
                continue
            seen.add(key)
            merged.append((mode, design_id))
    return merged


def _format_lab_block(designs: list[tuple[str, str]]) -> str:
    if not designs:
        return LAB_NONE
    lines: list[str] = []
    for mode, design_id in designs:
        lines.append(f"- `{mode}:{design_id}` — {LAB_RESEARCH_LINE}")
    return "\n".join(lines)


def _format_evidence_block(
    *,
    evidence_text: str | None,
    research_only: bool,
) -> str:
    if evidence_text:
        return evidence_text
    if research_only:
        return EVIDENCE_PREPRINT_ONLY
    return EVIDENCE_NONE


def _format_open_questions(
    *,
    biometrics: str,
    files_n: int,
    has_evidence: bool,
    has_designs: bool,
    card: ContextCard | None,
) -> str:
    gaps: list[str] = []
    if card is None or (
        not (card.gene or card.variant or (card.raw_text or "").strip())
        and (card.intent or "unspecified") == "unspecified"
    ):
        gaps.append("- No context card with a clear case intent, gene, or variant is loaded yet.")
    if biometrics == "none":
        gaps.append("- Patient biometrics are not on file yet.")
    elif biometrics == "incomplete":
        gaps.append("- Patient biometrics are incomplete.")
    if files_n == 0:
        # Count-only gap is optional; FEATURE says from notes count / missing fields.
        # Only mention if we already have other patient context, else keep lean.
        pass
    if not has_evidence:
        gaps.append("- No peer-reviewed evidence brief is on file yet.")
    if not has_designs:
        gaps.append("- No in-silico ligand or binder designs are on file yet.")
    if not gaps:
        return OPEN_NONE_GAPS
    return "\n".join(gaps)


def render_board_md(
    user_data: dict[str, Any] | None,
    *,
    user_id: int | str | None = None,
) -> str:
    """Build the board packet Markdown from current stores. Caller must refuse first if empty."""
    card = load_card(user_data) if user_data else None
    patient_id = _peek_patient_id(user_data) if user_data else None

    biometrics = biometrics_label(user_data)
    files_n = patient_files_count(user_data)

    evidence_text = _evidence_from_last_run(card) or _evidence_from_clinic(user_id, patient_id)
    research_only = False
    if not evidence_text:
        research_only = _research_on_file(user_id, patient_id, card)

    designs = collect_designs(user_data, user_id=user_id, patient_id=patient_id)
    evidence_block = _format_evidence_block(
        evidence_text=evidence_text,
        research_only=research_only,
    )
    lab_block = _format_lab_block(designs)
    open_block = _format_open_questions(
        biometrics=biometrics,
        files_n=files_n,
        has_evidence=bool(evidence_text),
        has_designs=bool(designs),
        card=card,
    )
    measure_block = measure_mod.board_measurements_block(user_data)

    return (
        "# Board packet\n"
        "\n"
        f"{DISCLAIMER}\n"
        "\n"
        "## Case context\n"
        "\n"
        f"- Intent: {_intent_line(card)}\n"
        f"- Gene / variant: {_gene_variant_line(card)}\n"
        f"- Patient biometrics: {biometrics}\n"
        f"- Patient files: {files_n} on file (contents not shown)\n"
        "\n"
        "## Measurements\n"
        "\n"
        f"{measure_block}\n"
        "\n"
        "## Evidence\n"
        "\n"
        f"{evidence_block}\n"
        "\n"
        "## Laboratory designs\n"
        "\n"
        f"{lab_block}\n"
        "\n"
        "## Open questions\n"
        "\n"
        f"{open_block}\n"
        "\n"
        "## Source note\n"
        "\n"
        f"{SOURCE_NOTE}\n"
    )


def _peek_patient_id(user_data: dict[str, Any]) -> str | None:
    """Read-only patient_id peek — does not create or mutate patient."""
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return None
    patient = raw.get("patient")
    if not isinstance(patient, dict):
        return None
    pid = patient.get("patient_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return None


def stash_board_path_on_card(
    user_data: dict[str, Any],
    path: str | Path,
) -> None:
    """Optional: record board md path on card last_run without wiping prior fields."""
    from .context_card import store_card

    card = load_card(user_data)
    if card is None:
        return
    prior = dict(card.last_run) if isinstance(card.last_run, dict) else {}
    prior["board_md"] = str(path)
    if "kind" not in prior:
        prior["kind"] = prior.get("kind") or "board"
    card.last_run = prior
    store_card(user_data, card)
