"""history_sorter — sole mutator of clinic.md, lab.ipynb, search.json, inbox/."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import history, store

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 0.5

_SECTION_HEADER_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^### ", re.MULTILINE)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_clinic(user_id: int | str, patient_id: str) -> str:
    store.ensure_patient_files(user_id, patient_id)
    return store.clinic_path(user_id, patient_id).read_text(encoding="utf-8")


def _write_clinic(user_id: int | str, patient_id: str, text: str) -> None:
    store.atomic_write_text(store.clinic_path(user_id, patient_id), text)


def _read_lab(user_id: int | str, patient_id: str) -> dict[str, Any]:
    store.ensure_patient_files(user_id, patient_id)
    return json.loads(store.lab_path(user_id, patient_id).read_text(encoding="utf-8"))


def _write_lab(user_id: int | str, patient_id: str, nb: dict[str, Any]) -> None:
    store.atomic_write_json(store.lab_path(user_id, patient_id), nb)


def _read_search(user_id: int | str, patient_id: str) -> dict[str, Any]:
    store.ensure_patient_files(user_id, patient_id)
    raw = json.loads(store.search_path(user_id, patient_id).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {"updated_at": "", "entries": []}
    raw.setdefault("entries", [])
    return raw


def _write_search(user_id: int | str, patient_id: str, obj: dict[str, Any]) -> None:
    obj = dict(obj)
    obj["updated_at"] = _now()
    store.atomic_write_json(store.search_path(user_id, patient_id), obj)


def _light_tokens(text: str, *, limit: int = 24) -> list[str]:
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_+]{1,}", text or "")
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        low = t.lower()
        if low in seen or len(low) < 2:
            continue
        seen.add(low)
        out.append(low)
        if len(out) >= limit:
            break
    return out


def _upsert_search_entries(
    user_id: int | str,
    patient_id: str,
    *,
    file: str,
    section: str,
    dois: list[str],
    title: str,
    offset: int,
    extra_text: str = "",
) -> None:
    search = _read_search(user_id, patient_id)
    entries: list[dict[str, Any]] = list(search.get("entries") or [])
    doi_set = {d.lower() for d in dois if d}
    # Drop prior entries for same file+section+doi
    kept: list[dict[str, Any]] = []
    for e in entries:
        edoi = str(e.get("doi") or "").lower()
        if e.get("file") == file and e.get("section") == section and edoi in doi_set:
            continue
        kept.append(e)
    tokens = _light_tokens(f"{title} {extra_text}")
    if dois:
        for doi in dois:
            kept.append(
                {
                    "doi": doi,
                    "file": file,
                    "section": section,
                    "offset": offset,
                    "title": title[:200],
                    "tokens": tokens,
                }
            )
    else:
        kept.append(
            {
                "doi": "",
                "file": file,
                "section": section,
                "offset": offset,
                "title": title[:200],
                "tokens": tokens,
            }
        )
    search["entries"] = kept
    _write_search(user_id, patient_id, search)


def _section_spans(md: str) -> list[tuple[str, int, int]]:
    """Return [(header_name, start_idx, end_idx), ...] for ## sections.

    start_idx is the index of the ## line; end_idx is start of next ## or EOF.
    The body of a section is md[start_idx:end_idx] including the header line.
    """
    matches = list(_SECTION_HEADER_RE.finditer(md))
    if not matches:
        return []
    spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        spans.append((name, start, end))
    return spans


def _get_section_body(md: str, header: str) -> tuple[str, int, int] | None:
    """Return (full_section_including_header, start, end) or None."""
    for name, start, end in _section_spans(md):
        if name == header:
            return md[start:end], start, end
    return None


def _replace_section(md: str, header: str, new_section: str) -> str:
    """Replace ## header section body (including header) with new_section text."""
    found = _get_section_body(md, header)
    if found is None:
        # Append section at end
        base = md.rstrip() + "\n\n"
        return base + new_section.rstrip() + "\n"
    _, start, end = found
    before = md[:start]
    after = md[end:]
    piece = new_section.rstrip() + "\n"
    if after and not after.startswith("\n") and not piece.endswith("\n\n"):
        # keep single newline separation
        pass
    return before + piece + after


def _set_demographics(md: str, on_file: bool) -> str:
    line = "Demographics: on file." if on_file else "Demographics: not on file."
    if re.search(r"^Demographics:.*$", md, re.MULTILINE):
        return re.sub(r"^Demographics:.*$", line, md, count=1, flags=re.MULTILINE)
    # Insert after title block disclaimer if missing
    return md.rstrip() + "\n\n" + line + "\n"


def _split_h3_units(section_body: str) -> tuple[str, list[str]]:
    """Split ## Evidence section into (header_line, [unit...]).

    section_body includes the ## Evidence line.
    """
    lines = section_body.splitlines(keepends=True)
    if not lines:
        return "## Evidence\n", []
    header = lines[0]
    rest = "".join(lines[1:])
    # Units start at ### 
    parts = re.split(r"(?=^### )", rest, flags=re.MULTILINE)
    units = [p for p in parts if p.strip()]
    return header, units


def _unit_has_doi(unit: str, doi: str) -> bool:
    return doi.lower() in unit.lower()


def _build_evidence_unit(brief_md: str, dois: list[str]) -> str:
    """Build one ### Evidence unit from a brief, preserving Harvard #### References."""
    # Prefer Findings bullets + References from the brief when present.
    findings = ""
    refs = ""
    m_find = re.search(
        r"## Findings\s*\n(.*?)(?=\n## |\Z)", brief_md, re.DOTALL | re.IGNORECASE
    )
    if m_find:
        findings = m_find.group(1).strip()
    m_ref = re.search(
        r"## References\s*\n(.*?)(?=\n## |\Z)", brief_md, re.DOTALL | re.IGNORECASE
    )
    if m_ref:
        refs = m_ref.group(1).strip()
    if not findings and not refs:
        # Use whole brief as findings; still try to keep a References footer if present.
        findings = brief_md.strip()
        refs = ""

    title_bit = "Evidence"
    if dois:
        title_bit = dois[0]
    sources = "Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded."
    parts = [f"### {title_bit}", "", findings, "", sources, ""]
    if refs:
        parts.extend(["#### References", "", refs, ""])
    elif dois:
        # Never invent Harvard lines; only list DOI URLs if brief had none.
        parts.extend(
            ["#### References", ""]
            + [f"https://doi.org/{d}" for d in dois]
            + [""]
        )
    return "\n".join(parts).rstrip() + "\n"


def apply_evidence(user_id: int | str, patient_id: str, payload: dict[str, Any]) -> None:
    brief = str(payload.get("brief_md") or payload.get("md") or "")
    dois = list(payload.get("dois") or []) or history.extract_dois(brief)
    md = _read_clinic(user_id, patient_id)
    found = _get_section_body(md, "Evidence")
    if found is None:
        header, units = "## Evidence\n", []
    else:
        section, _start, _end = found
        header, units = _split_h3_units(section)

    doi_set = {d.lower() for d in dois}
    kept = []
    for u in units:
        if doi_set and any(_unit_has_doi(u, d) for d in doi_set):
            continue
        kept.append(u)
    new_unit = _build_evidence_unit(brief, dois)
    kept.append(new_unit)
    new_section = header.rstrip() + "\n\n" + "\n".join(k.rstrip() + "\n" for k in kept)
    if not new_section.endswith("\n"):
        new_section += "\n"
    md2 = _replace_section(md, "Evidence", new_section)
    _write_clinic(user_id, patient_id, md2)
    offset = (_get_section_body(md2, "Evidence") or ("", 0, 0))[1]
    _upsert_search_entries(
        user_id,
        patient_id,
        file=store.CLINIC_NAME,
        section="Evidence",
        dois=dois,
        title="Evidence",
        offset=offset,
        extra_text=brief[:500],
    )


def apply_onboard(user_id: int | str, patient_id: str, _payload: dict[str, Any]) -> None:
    md = _read_clinic(user_id, patient_id)
    md2 = _set_demographics(md, True)
    _write_clinic(user_id, patient_id, md2)
    _upsert_search_entries(
        user_id,
        patient_id,
        file=store.CLINIC_NAME,
        section="Demographics",
        dois=[],
        title="Demographics: on file.",
        offset=md2.find("Demographics:"),
    )



def apply_measure(user_id: int | str, patient_id: str, payload: dict[str, Any]) -> None:
    """Index non-secret measure:<key> into search.json. Never stores values."""
    keys = payload.get("measure_keys") or []
    if isinstance(keys, str):
        keys = [keys]
    keys = [str(k).strip() for k in keys if str(k).strip()]
    # Single-key form
    one = payload.get("measure_key")
    if one:
        keys.append(str(one).strip())
    # Dedupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        ordered.append(k)
    if not ordered:
        return
    store.ensure_patient_files(user_id, patient_id)
    search = _read_search(user_id, patient_id)
    entries: list[dict[str, Any]] = list(search.get("entries") or [])
    # Drop prior measure:<key> entries for keys we are upserting
    titles = {f"measure:{k}" for k in ordered}
    kept = [e for e in entries if str(e.get("title") or "") not in titles]
    for k in ordered:
        title = f"measure:{k}"
        kept.append(
            {
                "doi": "",
                "file": store.CLINIC_NAME,
                "section": "Measurements",
                "offset": 0,
                "title": title,
                "tokens": _light_tokens(title),
            }
        )
    search["entries"] = kept
    _write_search(user_id, patient_id, search)


def apply_note(user_id: int | str, patient_id: str, payload: dict[str, Any]) -> None:
    note_id = str(payload.get("note_id") or "")
    ts = str(payload.get("ts") or _now())
    line = (
        f"- {ts}: note on file (id `{note_id}`). "
        "Body retained in session patient files; not repeated here.\n"
    )
    md = _read_clinic(user_id, patient_id)
    found = _get_section_body(md, "Notes")
    if found is None:
        section = "## Notes\n\n" + line
        md2 = md.rstrip() + "\n\n" + section
    else:
        section, _s, _e = found
        # Avoid duplicate same note id
        if note_id and f"(id `{note_id}`)" in section:
            return
        new_section = section.rstrip() + "\n" + line
        if not new_section.endswith("\n"):
            new_section += "\n"
        md2 = _replace_section(md, "Notes", new_section)
    _write_clinic(user_id, patient_id, md2)
    offset = (_get_section_body(md2, "Notes") or ("", 0, 0))[1]
    _upsert_search_entries(
        user_id,
        patient_id,
        file=store.CLINIC_NAME,
        section="Notes",
        dois=[],
        title=f"note {note_id}",
        offset=offset,
    )


def apply_bioscreen(user_id: int | str, patient_id: str, payload: dict[str, Any]) -> None:
    decision = str(payload.get("decision") or "").upper()
    if decision not in ("REVIEW", "BLOCK"):
        decision = "REVIEW"
    ts = str(payload.get("ts") or _now())
    line = (
        f"- {ts}: pre-compute screen returned {decision}. "
        "No sequence or score is recorded. Compute was not started.\n"
    )
    md = _read_clinic(user_id, patient_id)
    found = _get_section_body(md, "Biosecurity")
    if found is None:
        section = "## Biosecurity\n\n" + line
        md2 = md.rstrip() + "\n\n" + section
    else:
        section, _s, _e = found
        new_section = section.rstrip() + "\n" + line
        if not new_section.endswith("\n"):
            new_section += "\n"
        md2 = _replace_section(md, "Biosecurity", new_section)
    # Guard: never leave sequence-like long AA runs from payload (payload should not have them)
    _write_clinic(user_id, patient_id, md2)
    offset = (_get_section_body(md2, "Biosecurity") or ("", 0, 0))[1]
    _upsert_search_entries(
        user_id,
        patient_id,
        file=store.CLINIC_NAME,
        section="Biosecurity",
        dois=[],
        title=f"bioscreen {decision}",
        offset=offset,
    )


def apply_research(user_id: int | str, patient_id: str, payload: dict[str, Any]) -> None:
    brief = str(payload.get("brief_md") or payload.get("md") or "")
    dois = list(payload.get("dois") or []) or history.extract_dois(brief)
    nb = _read_lab(user_id, patient_id)
    cells: list[dict[str, Any]] = list(nb.get("cells") or [])
    doi_set = {d.lower() for d in dois}

    def cell_dois(cell: dict[str, Any]) -> set[str]:
        meta = cell.get("metadata") or {}
        raw = meta.get("dois") or []
        out = {str(x).lower() for x in raw}
        src = cell.get("source")
        if isinstance(src, list):
            text = "".join(src)
        else:
            text = str(src or "")
        for d in history.extract_dois(text):
            out.add(d.lower())
        return out

    kept: list[dict[str, Any]] = []
    for cell in cells:
        meta = cell.get("metadata") or {}
        tags = meta.get("tags") or []
        if "literature-preprint" in tags and doi_set and cell_dois(cell) & doi_set:
            continue  # replace
        kept.append(cell)

    source_lines = [
        "## Literature (preprint)\n",
        "\n",
        "Preprint brief (not peer-reviewed). Tone fence: do not upgrade to peer-reviewed language.\n",
        "\n",
        brief.rstrip() + "\n",
    ]
    new_cell = {
        "cell_type": "markdown",
        "metadata": {
            "tags": ["literature-preprint"],
            "dois": dois,
        },
        "source": source_lines,
    }
    kept.append(new_cell)
    nb["cells"] = kept
    _write_lab(user_id, patient_id, nb)
    _upsert_search_entries(
        user_id,
        patient_id,
        file=store.LAB_NAME,
        section="Literature (preprint)",
        dois=dois,
        title="Literature (preprint)",
        offset=len(kept) - 1,
        extra_text=brief[:500],
    )


def apply_scribe_inbox(user_id: int | str, payload: dict[str, Any]) -> Path:
    """v1 unlinked scribe → user inbox/. Never clinic.md minutes."""
    store.ensure_user_dirs(user_id)
    minutes = str(payload.get("minutes_md") or payload.get("md") or "")
    ts = str(payload.get("ts") or _now()).replace(":", "").replace("+", "p")
    fname = f"scribe-{ts}-{history.extract_dois(minutes) and 'x' or uuid_short()}.md"
    # Prefer event id if present in payload
    eid = str(payload.get("event_id") or uuid_short())
    path = store.inbox_dir(user_id) / f"scribe-{eid}.md"
    store.atomic_write_text(path, minutes if minutes.endswith("\n") else minutes + "\n")
    return path


def uuid_short() -> str:
    import uuid as _uuid

    return _uuid.uuid4().hex[:12]


def apply_lab_stub(
    user_id: int | str,
    patient_id: str,
    *,
    tag: str,
    title: str,
    artifact_paths: list[str] | None = None,
) -> None:
    """Minimum stub cell for /esm /boltz /design /confirm — do not block ship."""
    nb = _read_lab(user_id, patient_id)
    cells = list(nb.get("cells") or [])
    paths = artifact_paths or []
    lines = [f"## {title}\n", "\n"]
    if paths:
        lines.append("Artifacts:\n")
        for p in paths:
            lines.append(f"- `{p}`\n")
    else:
        lines.append("Stub cell (artifact paths not recorded in this event).\n")
    cells.append(
        {
            "cell_type": "markdown",
            "metadata": {"tags": [tag]},
            "source": lines,
        }
    )
    nb["cells"] = cells
    _write_lab(user_id, patient_id, nb)
    _upsert_search_entries(
        user_id,
        patient_id,
        file=store.LAB_NAME,
        section=title,
        dois=[],
        title=title,
        offset=len(cells) - 1,
    )


def _resolve_patient_id(payload: dict[str, Any]) -> str | None:
    pid = payload.get("patient_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return None


def _write_to_inbox(user_id: int | str, event: dict[str, Any], reason: str) -> None:
    store.ensure_user_dirs(user_id)
    eid = event.get("id") or uuid_short()
    path = store.inbox_dir(user_id) / f"event-{eid}.json"
    blob = {"reason": reason, "event": event}
    store.atomic_write_json(path, blob)


def apply_event(user_id: int | str, event: dict[str, Any]) -> None:
    """Apply one typed event. Idempotent if caller skips processed ids."""
    kind = event.get("kind")
    payload = dict(event.get("payload") or {})
    payload.setdefault("ts", event.get("ts") or _now())
    payload["event_id"] = event.get("id")

    if kind == history.KIND_SCRIBE:
        # v1: always unlinked → inbox (even if patient_id present)
        apply_scribe_inbox(user_id, payload)
        return

    patient_id = _resolve_patient_id(payload)
    needs_patient = kind in {
        history.KIND_EVIDENCE,
        history.KIND_RESEARCH,
        history.KIND_ONBOARD,
        history.KIND_NOTE,
        history.KIND_MEASURE,
        history.KIND_BIOSECURITY,
        history.KIND_ESM,
        history.KIND_BOLTZ,
        history.KIND_DESIGN,
        history.KIND_CONFIRM,
    }
    if needs_patient and not patient_id:
        _write_to_inbox(user_id, event, "no_patient")
        return

    if kind == history.KIND_EVIDENCE:
        assert patient_id
        apply_evidence(user_id, patient_id, payload)
    elif kind == history.KIND_RESEARCH:
        assert patient_id
        apply_research(user_id, patient_id, payload)
    elif kind == history.KIND_ONBOARD:
        assert patient_id
        apply_onboard(user_id, patient_id, payload)
    elif kind == history.KIND_NOTE:
        assert patient_id
        apply_note(user_id, patient_id, payload)
    elif kind == history.KIND_MEASURE:
        assert patient_id
        apply_measure(user_id, patient_id, payload)
    elif kind == history.KIND_BIOSECURITY:
        assert patient_id
        apply_bioscreen(user_id, patient_id, payload)
    elif kind == history.KIND_ESM:
        assert patient_id
        apply_lab_stub(
            user_id,
            patient_id,
            tag="esm",
            title="ESMFold structure",
            artifact_paths=list(payload.get("artifact_paths") or []),
        )
    elif kind == history.KIND_BOLTZ:
        assert patient_id
        apply_lab_stub(
            user_id,
            patient_id,
            tag="boltz",
            title="Boltz structure",
            artifact_paths=list(payload.get("artifact_paths") or []),
        )
    elif kind in (history.KIND_DESIGN, history.KIND_CONFIRM):
        assert patient_id
        # TODO(design-namespace): when design events are emitted, key search.json
        # entries with ligand:<design-id> / binder:<design-id> prefixes. Binder
        # refuse paths must not write fake lab cells.
        mode = str(payload.get("mode") or "ligand")
        title = (
            "Protein-binder design"
            if mode == "binder"
            else "Small-molecule design"
        )
        # Prefer namespaced tag when design_id present; otherwise keep kind tag.
        design_id = payload.get("design_id")
        if design_id:
            tag = f"{mode}:{design_id}"
        else:
            tag = f"{mode}:{kind}"
        apply_lab_stub(
            user_id,
            patient_id,
            tag=tag,
            title=title,
            artifact_paths=list(payload.get("artifact_paths") or []),
        )
    else:
        logger.info("sorter skip unknown kind=%s id=%s", kind, event.get("id"))


def process_user(user_id: int | str) -> int:
    """Dequeue and apply pending events for one user. Returns count applied."""
    pending = history.pending_events(user_id)
    n = 0
    for event in pending:
        eid = event["id"]
        try:
            apply_event(user_id, event)
            store.mark_processed(user_id, eid)
            n += 1
        except Exception:  # noqa: BLE001
            logger.exception("sorter failed user=%s event=%s", user_id, eid)
            # Leave unprocessed for retry; do not half-mark.
    return n


def list_store_user_ids() -> list[str]:
    if not store.STORE_ROOT.exists():
        return []
    out: list[str] = []
    for p in store.STORE_ROOT.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            out.append(p.name)
    return sorted(out)


def process_all() -> int:
    total = 0
    for uid in list_store_user_ids():
        total += process_user(uid)
    return total


async def run_forever(*, interval: float = POLL_INTERVAL_SEC, stop_event: asyncio.Event | None = None) -> None:
    """Background asyncio task: poll queues and apply events."""
    logger.info("history_sorter started interval=%.2fs root=%s", interval, store.STORE_ROOT)
    store.STORE_ROOT.mkdir(parents=True, exist_ok=True)
    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("history_sorter stopping")
            return
        try:
            n = await asyncio.to_thread(process_all)
            if n:
                logger.info("history_sorter applied %s event(s)", n)
        except Exception:  # noqa: BLE001
            logger.exception("history_sorter loop error")
        try:
            if stop_event is not None:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            await asyncio.sleep(interval)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            logger.info("history_sorter cancelled")
            raise
