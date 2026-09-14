"""Clinical biometrics onboard Q&A — research-use secrets on the context card.

Locked field set and flow: docs/FEATURE-onboard-clinical-biometrics.md.
Values are never echoed in status, /load, fingerprints, research md, or Discord.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .context_card import CONTEXT_CARD_KEY, ContextCard, store_card

ONBOARD_KEY = "onboard"

FIELD_ORDER = ("age_years", "sex", "weight_kg", "height_cm")

QUESTIONS = {
    "age_years": "What is the patient’s age in whole years?",
    "sex": "Patient sex for research coding: F, M, or X?",
    "weight_kg": "What is the patient’s weight in kilograms?",
    "height_cm": "What is the patient’s height in centimetres?",
}

HINTS = {
    "age_years": "Please reply with a whole number from 0 to 120.",
    "sex": "Please reply with F, M, or X.",
    "weight_kg": "Please reply with a number of kilograms from 1 to 400.",
    "height_cm": "Please reply with a number of centimetres from 30 to 250.",
}

REFUSE_DIAGNOSE_BIOMETRICS = (
    "This request cannot be fulfilled. Biometrics collected here are for research "
    "context only. This bot does not diagnose, dose, or give clinical advice from "
    "age, sex, weight, height, or BMI."
)

_DIAGNOSE_RE_WORDS = (
    "diagnose",
    "diagnosis",
    "what disease",
    "what condition",
    "clinical advice",
    "prescribe",
    "treatment from",
    "based on bmi",
    "based on my weight",
    "based on weight",
    "from biometrics",
    "from my age",
)


def empty_patient() -> dict[str, Any]:
    return {
        "secret": True,
        "complete": False,
        "patient_id": str(uuid.uuid4()),  # stable id; never echo in status/card
        "age_years": None,
        "sex": None,
        "weight_kg": None,
        "height_cm": None,
        "bmi": None,
        "updated_at": _now(),
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_patient(user_data: dict[str, Any]) -> dict[str, Any] | None:
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return None
    patient = raw.get("patient")
    if not isinstance(patient, dict):
        return None
    return patient


def set_patient(user_data: dict[str, Any], patient: dict[str, Any]) -> None:
    """Attach patient secrets to the context_card dict without touching formal fields."""
    shell = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(shell, dict):
        # Minimal card shell so patient has a home; ContextCard.from_dict ignores patient.
        card = ContextCard(created_at=_now())
        store_card(user_data, card)
        shell = user_data[CONTEXT_CARD_KEY]
    patient = dict(patient)
    patient["secret"] = True
    patient["updated_at"] = _now()
    ensure_patient_id(patient)
    _recompute(patient)
    shell["patient"] = patient


def clear_patient(user_data: dict[str, Any]) -> bool:
    """Remove patient biometric secrets and patient_files. Returns True if patient was present."""
    end_onboard(user_data)
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return False
    had = "patient" in raw
    raw.pop("patient", None)
    raw.pop("patient_files", None)
    # Disarm any pending /note without requiring a circular import at module load.
    note_state = user_data.pop("note", None)
    _ = note_state  # files already dropped above
    return had


def _recompute(patient: dict[str, Any]) -> None:
    missing = missing_fields(patient)
    patient["complete"] = len(missing) == 0
    w = patient.get("weight_kg")
    h = patient.get("height_cm")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and h > 0:
        height_m = float(h) / 100.0
        patient["bmi"] = round(float(w) / (height_m * height_m), 2)
    else:
        patient["bmi"] = None


def missing_fields(patient: dict[str, Any] | None) -> list[str]:
    if not patient:
        return list(FIELD_ORDER)
    out: list[str] = []
    for key in FIELD_ORDER:
        val = patient.get(key)
        if val is None or val == "":
            out.append(key)
    return out


def next_field(patient: dict[str, Any] | None) -> str | None:
    miss = missing_fields(patient)
    return miss[0] if miss else None


def question_for(field: str) -> str:
    return QUESTIONS[field]


def hint_for(field: str) -> str:
    return HINTS[field]


def status_text(patient: dict[str, Any] | None) -> str:
    """Complete / incomplete — never include raw biometric values."""
    if not patient or all(patient.get(k) is None for k in FIELD_ORDER):
        return (
            "Patient biometrics are incomplete (missing: "
            + ", ".join(FIELD_ORDER)
            + "). Values are not shown."
        )
    miss = missing_fields(patient)
    if not miss and patient.get("complete"):
        return "Patient biometrics are complete."
    if not miss:
        return "Patient biometrics are complete."
    return (
        "Patient biometrics are incomplete (missing: "
        + ", ".join(miss)
        + "). Values are not shown."
    )


def patient_card_line(patient: dict[str, Any] | None) -> str:
    """One line for /load card display — never echo values."""
    if not patient or all(patient.get(k) is None for k in FIELD_ORDER):
        return "Patient: not on file."
    if patient.get("complete") and not missing_fields(patient):
        return "Patient: on file."
    return "Patient: incomplete."


def validate_field(field: str, raw: str) -> tuple[Any | None, str | None]:
    """Return (parsed_value, None) on success, or (None, hint) on failure."""
    text = (raw or "").strip()
    if field == "age_years":
        if "." in text or "e" in text.lower() or "+" in text:
            return None, hint_for(field)
        try:
            val = int(text)
        except ValueError:
            return None, hint_for(field)
        if val < 0 or val > 120:
            return None, hint_for(field)
        return val, None

    if field == "sex":
        letter = text.upper()
        if letter in ("F", "M", "X"):
            return letter, None
        return None, hint_for(field)

    if field == "weight_kg":
        try:
            val = float(text)
        except ValueError:
            return None, hint_for(field)
        if val < 1 or val > 400:
            return None, hint_for(field)
        return val, None

    if field == "height_cm":
        try:
            val = float(text)
        except ValueError:
            return None, hint_for(field)
        if val < 30 or val > 250:
            return None, hint_for(field)
        return val, None

    return None, "That field is not recognised."


def ensure_patient_id(patient: dict[str, Any]) -> str:
    """Generate uuid once on the patient block; never echo to users."""
    pid = patient.get("patient_id")
    if not isinstance(pid, str) or not pid.strip():
        pid = str(uuid.uuid4())
        patient["patient_id"] = pid
    return pid


def ensure_patient(user_data: dict[str, Any]) -> dict[str, Any]:
    patient = get_patient(user_data)
    if patient is None:
        patient = empty_patient()
        set_patient(user_data, patient)
        return get_patient(user_data) or patient
    return patient


def start_or_resume(user_data: dict[str, Any]) -> tuple[str, str | None]:
    """Init patient block if needed; activate Q&A at first missing field.

    Returns (reply_text, next_field_or_None).
    """
    patient = ensure_patient(user_data)
    field = next_field(patient)
    if field is None:
        user_data[ONBOARD_KEY] = {"active": False, "next_field": None}
        return (
            "Patient biometrics are complete. Send /onboard status for a summary "
            "without values, or /onboard clear to remove them.",
            None,
        )
    user_data[ONBOARD_KEY] = {"active": True, "next_field": field}
    return (question_for(field), field)


def end_onboard(user_data: dict[str, Any]) -> bool:
    """Clear onboard conversation state only. Returns whether it was active."""
    state = user_data.pop(ONBOARD_KEY, None)
    if isinstance(state, dict):
        return bool(state.get("active"))
    return False


def is_active(user_data: dict[str, Any]) -> bool:
    state = user_data.get(ONBOARD_KEY)
    return isinstance(state, dict) and bool(state.get("active"))


def current_field(user_data: dict[str, Any]) -> str | None:
    state = user_data.get(ONBOARD_KEY)
    if not isinstance(state, dict) or not state.get("active"):
        return None
    field = state.get("next_field")
    if field in FIELD_ORDER:
        return field
    return next_field(get_patient(user_data))


def apply_answer(user_data: dict[str, Any], text: str) -> str:
    """Parse plain-text answer while onboard is active. Never logs raw values."""
    field = current_field(user_data)
    if field is None:
        end_onboard(user_data)
        return "Patient biometrics are complete."

    value, err = validate_field(field, text)
    if err is not None:
        return f"{err}\n{question_for(field)}"

    patient = ensure_patient(user_data)
    patient[field] = value
    set_patient(user_data, patient)
    patient = get_patient(user_data) or patient

    nxt = next_field(patient)
    if nxt is None:
        user_data[ONBOARD_KEY] = {"active": False, "next_field": None}
        return "Patient biometrics are complete. Values are stored as secrets and are not shown."
    user_data[ONBOARD_KEY] = {"active": True, "next_field": nxt}
    return question_for(nxt)


def looks_like_diagnose_from_biometrics(text: str) -> bool:
    low = (text or "").lower()
    if "diagnos" in low or "prescribe" in low or "what disease" in low:
        bio_hints = (
            "bmi",
            "weight",
            "height",
            "age",
            "biometric",
            "patient",
            "sex",
            "kg",
            "cm",
        )
        if any(h in low for h in bio_hints):
            return True
    if "from biometrics" in low or "based on bmi" in low:
        return True
    return False
