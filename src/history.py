"""Append-only typed event bus. Handlers emit; sorter is the sole file mutator."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import store

logger = logging.getLogger(__name__)

# Event kinds (v1 bar + stubs).
KIND_RESEARCH = "research"
KIND_EVIDENCE = "evidence"
KIND_ONBOARD = "onboard_complete"
KIND_NOTE = "note"
KIND_MEASURE = "measure"
KIND_SCRIBE = "scribe"
KIND_BIOSECURITY = "bioscreen"
KIND_ESM = "esm"
KIND_BOLTZ = "boltz"
KIND_DESIGN = "design"
KIND_CONFIRM = "confirm"

_DOI_RE = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)

# Never allow these keys in payloads (defense in depth).
_BLOCKED_PAYLOAD_KEYS = frozenset(
    {
        "age_years",
        "sex",
        "weight_kg",
        "height_cm",
        "bmi",
        "sequence",
        "dna",
        "rna",
        "aa_sequence",
        "protein_sequence",
        "note_body",
        "text",  # note body must not ride as "text"
        "body",
        "value",  # measure values must not ride in history payloads
        "measurements",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_dois(text: str) -> list[str]:
    """Return unique DOIs in order of first appearance. Never invents."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _DOI_RE.finditer(text or ""):
        doi = m.group(1).rstrip(").,;")
        key = doi.lower()
        if key not in seen:
            seen.add(key)
            out.append(doi)
    return out


def _scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop biometric / sequence / full-body keys. Keep safe typed fields."""
    clean: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if k in _BLOCKED_PAYLOAD_KEYS:
            continue
        if k == "decision" and isinstance(v, str):
            clean[k] = v.upper()
            continue
        if k in ("brief_md", "minutes_md", "md") and isinstance(v, str):
            # Brief/minutes md is intentional; still strip absurdly long DNA-like runs.
            clean[k] = v
            continue
        if k in (
            "dois",
            "note_id",
            "patient_id",
            "ts",
            "artifact_paths",
            "kind_hint",
            "measure_keys",
            "measure_key",
            "n",
            "n_secret",
        ):
            clean[k] = v
            continue
        if k == "linked":
            clean[k] = bool(v)
            continue
        # Allow small scalar metadata only.
        if isinstance(v, (str, int, float, bool)) or v is None:
            if isinstance(v, str) and len(v) > 4000:
                continue
            clean[k] = v
    return clean


def emit(user_id: int | str, kind: str, payload: dict[str, Any] | None = None) -> str:
    """Append typed event {id, ts, kind, payload} to per-user queue. Returns event id.

    Failures raise; callers that must not fail the Telegram reply should catch.
    """
    store.ensure_user_dirs(user_id)
    event_id = uuid.uuid4().hex
    event = {
        "id": event_id,
        "ts": _now(),
        "kind": kind,
        "payload": _scrub_payload(dict(payload or {})),
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"
    qpath = store.queue_path(user_id)
    with qpath.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return event_id


def read_queue(user_id: int | str) -> list[dict[str, Any]]:
    """Read all queued events (including already-processed)."""
    store.ensure_user_dirs(user_id)
    qpath = store.queue_path(user_id)
    events: list[dict[str, Any]] = []
    text = qpath.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("skip malformed queue line user=%s", user_id)
            continue
        if isinstance(obj, dict) and obj.get("id"):
            events.append(obj)
    return events


def pending_events(user_id: int | str) -> list[dict[str, Any]]:
    done = store.load_processed(user_id)
    return [e for e in read_queue(user_id) if e["id"] not in done]
