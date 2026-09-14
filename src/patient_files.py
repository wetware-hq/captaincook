"""Patient files (/note) on the context card — separate from biometric secrets.

Locked behaviour: docs/FEATURE-note-patient-files.md.
Locked copy: docs/COPY-note.md (verbatim).
Notes are never passed into research Markdown, captions, Discord helpers, or LM prompts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .context_card import CONTEXT_CARD_KEY
from . import onboard as onboard_mod

NOTE_KEY = "note"
NOTE_MAX_CHARS = 2000

# --- Locked COPY-note.md (verbatim) ---
MSG_ARMED = (
    "Send your note in the next message. It will be saved to patient files on this card. "
    "Biometric secrets from /onboard are separate and are not changed."
)
MSG_SAVED = "Note saved to patient files ({n} on file). Biometric secrets are unchanged."
MSG_LIST = (
    "Patient files on this card: {n}. Contents are not shown. Biometric secrets are separate."
)
MSG_LIST_ZERO = (
    "No patient files on this card. Biometric secrets, if any, are separate."
)
MSG_CLEAR = "Patient files have been cleared. Biometric secrets are unchanged."
MSG_NO_PATIENT = (
    "This request cannot proceed. There is no patient on the current card. "
    "Complete /onboard first, then use /note to add patient files. "
    "Biometric secrets and patient files are separate stores."
)
MSG_TOO_LONG = (
    "This note is too long. Please shorten it to 2000 characters or fewer and send it again."
)
MSG_REFUSE_LM = (
    "This request cannot be fulfilled. Patient files and biometric secrets stay on this "
    "chat’s card for research context only. They are not sent to language models, "
    "research briefs, or Discord, and this bot does not diagnose from them."
)

MSG_EMPTY = "Please send a non-empty note as the next message."
MSG_BAD_OPTION = "Unrecognised /note option. Use /note, /note list, or /note clear."

# Hard-block markers: never feed these into research/caption/Discord/LM builders.
BLOCKED_DOWNSTREAM_KEYS = frozenset(
    {
        "patient",
        "patient_files",
        "age_years",
        "sex",
        "weight_kg",
        "height_cm",
        "bmi",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_patient_files(user_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return []
    files = raw.get("patient_files")
    if not isinstance(files, list):
        return []
    return [f for f in files if isinstance(f, dict)]


def set_patient_files(user_data: dict[str, Any], files: list[dict[str, Any]]) -> None:
    """Write patient_files onto the card shell. Does not create a patient block."""
    shell = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(shell, dict):
        return
    shell["patient_files"] = list(files)


def clear_patient_files(user_data: dict[str, Any]) -> bool:
    """Drop patient_files only. Biometrics untouched. Returns True if key was present."""
    end_note(user_data)
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict) or "patient_files" not in raw:
        return False
    raw.pop("patient_files", None)
    return True


def patient_present(user_data: dict[str, Any]) -> bool:
    """True when a biometric patient block exists (from /onboard). Does not create one."""
    return onboard_mod.get_patient(user_data) is not None


def arm_note(user_data: dict[str, Any]) -> None:
    user_data[NOTE_KEY] = {"armed": True}


def end_note(user_data: dict[str, Any]) -> bool:
    """Disarm note arming without deleting files. Returns whether it was armed."""
    state = user_data.pop(NOTE_KEY, None)
    if isinstance(state, dict):
        return bool(state.get("armed"))
    return False


def is_armed(user_data: dict[str, Any]) -> bool:
    state = user_data.get(NOTE_KEY)
    return isinstance(state, dict) and bool(state.get("armed"))


def start_note(user_data: dict[str, Any]) -> str:
    """Arm next plain message as a note, or refuse if no patient block."""
    if not patient_present(user_data):
        end_note(user_data)
        return MSG_NO_PATIENT
    arm_note(user_data)
    return MSG_ARMED


def list_text(user_data: dict[str, Any]) -> str:
    n = len(get_patient_files(user_data))
    if n == 0:
        return MSG_LIST_ZERO
    return MSG_LIST.format(n=n)


def clear_text(user_data: dict[str, Any]) -> str:
    clear_patient_files(user_data)
    return MSG_CLEAR


def append_note(user_data: dict[str, Any], text: str) -> str:
    """Append one note while armed. Rejects overlength/empty and keeps arming.

    Never creates a patient block. Never echoes the note body in the ack.
    """
    if not patient_present(user_data):
        end_note(user_data)
        return MSG_NO_PATIENT

    body = (text or "").strip()
    if not body:
        return MSG_EMPTY
    if len(body) > NOTE_MAX_CHARS:
        return MSG_TOO_LONG

    files = get_patient_files(user_data)
    entry = {
        "id": uuid.uuid4().hex,
        "text": body,
        "created_at": _now(),
    }
    files.append(entry)
    set_patient_files(user_data, files)
    end_note(user_data)
    return MSG_SAVED.format(n=len(files))


def looks_like_diagnose_from_files_or_biometrics(text: str) -> bool:
    """Detect diagnose / LM-from-notes-or-biometrics asks for the locked refuse."""
    if onboard_mod.looks_like_diagnose_from_biometrics(text):
        return True
    low = (text or "").lower()
    if "diagnos" in low or "prescribe" in low:
        if any(h in low for h in ("note", "patient file", "files on")):
            return True
    if "from my notes" in low or "from patient files" in low:
        return True
    if "send my notes to" in low or "embed my notes" in low:
        return True
    return False


def assert_no_secret_payload(payload: Any, *, where: str = "downstream") -> None:
    """Raise if a dict tree contains biometric or note fields destined for LM/Discord/research."""
    stack: list[Any] = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for key, val in cur.items():
                if key in BLOCKED_DOWNSTREAM_KEYS:
                    raise ValueError(
                        f"Hard block: refusing to pass {key!r} into {where}."
                    )
                stack.append(val)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
