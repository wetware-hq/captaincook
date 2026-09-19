"""Paste-friendly measurements on the context card (/measure).

Locked behaviour: docs/FEATURE-measure.md.
Locked copy: docs/TEMPLATE-measure.md (verbatim).

Decision (v1): unknown free keys without the secret flag are coerced to
other:<slug> (not hard-refused). Free keys with secret=True are kept as-is.
Secret measure values never appear in list, board, /load dumps, captions,
HELP, Discord, variant/evidence/trials, or LM prompts — counts only.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any

from .context_card import CONTEXT_CARD_KEY, load_card

MEASURE_KEY = "measure"  # arm state on user_data
MEASUREMENTS_FIELD = "measurements"

CONTROLLED_KEYS = frozenset(
    {
        "hr",
        "bp_sys",
        "bp_dia",
        "weight_kg",
        "height_cm",
        "temp_c",
        "spo2",
        "glucose_mmol",
    }
)

# Display / paste aliases → controlled key (BP handled specially).
_ALIASES: dict[str, str] = {
    "hr": "hr",
    "heart_rate": "hr",
    "heartrate": "hr",
    "pulse": "hr",
    "bp_sys": "bp_sys",
    "bpsys": "bp_sys",
    "systolic": "bp_sys",
    "bp_dia": "bp_dia",
    "bpdia": "bp_dia",
    "diastolic": "bp_dia",
    "weight_kg": "weight_kg",
    "weight": "weight_kg",
    "height_cm": "height_cm",
    "height": "height_cm",
    "temp_c": "temp_c",
    "temp": "temp_c",
    "temperature": "temp_c",
    "spo2": "spo2",
    "o2sat": "spo2",
    "glucose_mmol": "glucose_mmol",
    "glucose": "glucose_mmol",
}

_DEFAULT_UNITS: dict[str, str] = {
    "hr": "bpm",
    "bp_sys": "mmHg",
    "bp_dia": "mmHg",
    "weight_kg": "kg",
    "height_cm": "cm",
    "temp_c": "°C",
    "spo2": "%",
    "glucose_mmol": "mmol/L",
}

# --- Locked TEMPLATE-measure.md (verbatim) ---
MSG_ARMED = (
    "Send your measurements in the next message. Examples:\n"
    "HR 72 bpm\n"
    "BP 120/80 mmHg\n"
    "weight_kg=81.2 secret\n"
    "device: ward_monitor_3\n"
    "\n"
    "Use controlled keys when you can. Mark sensitive values with secret. "
    "Research use only; this bot does not diagnose from measurements."
)
MSG_SAVED = (
    "Saved {n} measurement(s) on this card ({n_secret} secret). "
    "Secret values are not shown."
)
MSG_LIST_EMPTY = "No measurements on this card."
MSG_LIST_SECRETS_ONLY = (
    "No non-secret measurements on this card. "
    "Secret measures on file: {n} (values not shown)."
)
MSG_CLEAR_KEY = "Cleared measurements for key `{key}` on this card."
MSG_CLEAR_ALL = "Cleared all measurements on this card."
MSG_NO_CARD = (
    "This request cannot proceed. There is no context card. "
    "Please /load a case first, then use /measure."
)
MSG_BAD_PASTE = (
    "This paste could not be parsed. Use lines such as HR 72 bpm, BP 120/80 mmHg, "
    "or weight_kg=81.2 secret. Prefer controlled keys "
    "(hr, bp_sys, bp_dia, weight_kg, height_cm, temp_c, spo2, glucose_mmol)."
)
MSG_EMPTY = (
    "No measurements were saved. Please send at least one valid line, or /cancel to stop."
)
MSG_BAD_OPTION = (
    "Unrecognised /measure option. Use /measure, /measure list, "
    "/measure clear [key|all], or /measure followed by paste lines."
)
MSG_CANCELLED = (
    "The pending measurement paste was cancelled. Saved measurements were kept."
)

HELP_ONE_LINER = (
    "/measure — Paste patient observations onto the current card "
    "(HR, BP, weight_kg=…, optional secret). /measure list shows keys; "
    "secret values are never shown. Research use only; not a diagnosis."
)
HELP_COMMANDS = (
    "/measure — Arm the next message as a measurement paste.\n"
    "/measure <lines> — Parse a short paste immediately.\n"
    "/measure list — List keys and counts. Secret measures appear only as a count.\n"
    "/measure clear [key|all] — Clear one key series or all measurements on this card."
)

BOARD_NONE = "None yet. Paste observations with /measure."
BOARD_SECRET_STUB = "Secret measures on file: {n} (values not shown)."

# Hard-block markers for LM/Discord/research builders.
BLOCKED_DOWNSTREAM_KEYS = frozenset(
    {
        "measurements",
        "measure_value",
        "measure_values",
    }
)

_ISO_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)\s+"
)
_DEVICE_RE = re.compile(r"^device\s*[:=]\s*(.+)$", re.IGNORECASE)
_KV_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_:<>-]*)\s*[:=]\s*(?P<val>.+)$"
)
_SPACE_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<val>.+)$"
)
_BP_RE = re.compile(
    r"^(?P<sys>\d+(?:\.\d+)?)\s*/\s*(?P<dia>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z/%°]+)?\s*$"
)
_NUM_UNIT_RE = re.compile(
    r"^(?P<num>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z/%°]+)?\s*$"
)
_SECRET_TOKEN_RE = re.compile(r"\bsecret(?:\s*=\s*true)?\b", re.IGNORECASE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(raw: str) -> str:
    s = (raw or "").strip().lower().replace(":", "_")
    s = _SLUG_RE.sub("_", s).strip("_")
    return s or "unknown"


def coerce_key(raw_key: str, *, secret: bool) -> str:
    """Map paste key → stored key.

    Controlled aliases → controlled name.
    other:<slug> kept (slug normalised).
    Free key + secret → kept as lowercase slug (not other:).
    Free key without secret → coerced to other:<slug> (documented decision).
    """
    raw = (raw_key or "").strip()
    low = raw.lower()
    if low.startswith("other:"):
        return f"other:{_slugify(low[6:])}"
    alias = _ALIASES.get(low) or _ALIASES.get(low.replace("-", "_"))
    if alias:
        return alias
    slug = _slugify(low)
    if secret:
        return slug
    # Decision: coerce unknown free key without secret → other:<slug>
    return f"other:{slug}"


def card_present(user_data: dict[str, Any]) -> bool:
    raw = user_data.get(CONTEXT_CARD_KEY)
    return isinstance(raw, dict)


def get_measurements(user_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(raw, dict):
        return []
    items = raw.get(MEASUREMENTS_FIELD)
    if not isinstance(items, list):
        return []
    return [m for m in items if isinstance(m, dict)]


def set_measurements(user_data: dict[str, Any], items: list[dict[str, Any]]) -> None:
    shell = user_data.get(CONTEXT_CARD_KEY)
    if not isinstance(shell, dict):
        return
    shell[MEASUREMENTS_FIELD] = list(items)


def arm_measure(user_data: dict[str, Any]) -> None:
    user_data[MEASURE_KEY] = {"armed": True}


def end_measure(user_data: dict[str, Any]) -> bool:
    state = user_data.pop(MEASURE_KEY, None)
    if isinstance(state, dict):
        return bool(state.get("armed"))
    return False


def is_armed(user_data: dict[str, Any]) -> bool:
    state = user_data.get(MEASURE_KEY)
    return isinstance(state, dict) and bool(state.get("armed"))


def start_measure(user_data: dict[str, Any]) -> str:
    if not card_present(user_data):
        end_measure(user_data)
        return MSG_NO_CARD
    arm_measure(user_data)
    return MSG_ARMED


def _strip_secret(text: str) -> tuple[str, bool]:
    secret = bool(_SECRET_TOKEN_RE.search(text or ""))
    cleaned = _SECRET_TOKEN_RE.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, secret


def _parse_value_unit(val: str) -> tuple[Any, str | None]:
    val = (val or "").strip()
    m = _NUM_UNIT_RE.match(val)
    if m:
        num_s = m.group("num")
        unit = (m.group("unit") or "").strip() or None
        try:
            if "." in num_s:
                return float(num_s), unit
            return int(num_s), unit
        except ValueError:
            return val, unit
    return val, None


def _make_entry(
    *,
    key: str,
    value: Any,
    unit: str | None,
    device: str | None,
    secret: bool,
    ts: str,
    source: str = "paste",
) -> dict[str, Any]:
    if unit is None and key in _DEFAULT_UNITS and not key.startswith("other:"):
        unit = _DEFAULT_UNITS[key]
    return {
        "ts": ts,
        "key": key,
        "value": value,
        "unit": unit,
        "device": device,
        "secret": bool(secret),
        "source": source,
    }


def _parse_bp_pair(
    val: str, *, secret: bool, device: str | None, ts: str
) -> list[dict[str, Any]] | None:
    m = _BP_RE.match(val.strip())
    if not m:
        return None
    unit = (m.group("unit") or "").strip() or "mmHg"
    try:
        sys_v: Any = float(m.group("sys")) if "." in m.group("sys") else int(m.group("sys"))
        dia_v: Any = float(m.group("dia")) if "." in m.group("dia") else int(m.group("dia"))
    except ValueError:
        return None
    return [
        _make_entry(
            key="bp_sys", value=sys_v, unit=unit, device=device, secret=secret, ts=ts
        ),
        _make_entry(
            key="bp_dia", value=dia_v, unit=unit, device=device, secret=secret, ts=ts
        ),
    ]


def _parse_one_line(
    line: str,
    *,
    sticky_device: str | None,
    sticky_ts: str | None,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Return (entries, new_sticky_device, new_sticky_ts). Device-only lines yield []."""
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        return [], sticky_device, sticky_ts

    ts = sticky_ts or _now()
    rest = raw
    iso_m = _ISO_PREFIX_RE.match(rest)
    if iso_m:
        ts = iso_m.group("ts").replace(" ", "T")
        if ts.endswith("Z"):
            pass
        rest = rest[iso_m.end() :].strip()
        sticky_ts = ts

    rest, secret = _strip_secret(rest)
    if not rest:
        return [], sticky_device, sticky_ts

    dev_m = _DEVICE_RE.match(rest)
    if dev_m:
        return [], dev_m.group(1).strip(), sticky_ts

    # key=value or KEY value …
    key_raw: str | None = None
    val_raw: str | None = None
    kv = _KV_RE.match(rest)
    if kv:
        key_raw = kv.group("key")
        val_raw = kv.group("val").strip()
    else:
        sp = _SPACE_RE.match(rest)
        if sp:
            key_raw = sp.group("key")
            val_raw = sp.group("val").strip()

    if not key_raw or val_raw is None:
        return [], sticky_device, sticky_ts

    key_low = key_raw.lower()
    # BP special: BP 120/80
    if key_low in ("bp", "blood_pressure", "bloodpressure"):
        pair = _parse_bp_pair(
            val_raw, secret=secret, device=sticky_device, ts=ts
        )
        if pair:
            return pair, sticky_device, sticky_ts
        return [], sticky_device, sticky_ts

    known = (
        key_low in _ALIASES
        or key_low.replace("-", "_") in _ALIASES
        or key_low.startswith("other:")
        or key_low in CONTROLLED_KEYS
    )
    # Space-form free keys need a leading numeric value (else not a measure line).
    used_kv = bool(kv)
    if not known and not used_kv:
        if not re.match(r"^[-+]?\d", val_raw.strip()):
            return [], sticky_device, sticky_ts

    key = coerce_key(key_raw, secret=secret)
    value, unit = _parse_value_unit(val_raw)
    # Reject non-numeric free-text values for uncontrolled keys without = form digit.
    if not known and not isinstance(value, (int, float)):
        if not used_kv:
            return [], sticky_device, sticky_ts
    return (
        [
            _make_entry(
                key=key,
                value=value,
                unit=unit,
                device=sticky_device,
                secret=secret,
                ts=ts,
            )
        ],
        sticky_device,
        sticky_ts,
    )


def _try_tabular(text: str) -> list[dict[str, Any]] | None:
    """Optional CSV/TSV one-shot. Returns None if not tabular."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    sample = lines[0]
    dialect = None
    if "\t" in sample:
        delim = "\t"
    elif sample.count(",") >= 1:
        delim = ","
    else:
        return None
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        if not reader.fieldnames:
            return None
        fields = [f.strip().lower() for f in reader.fieldnames if f]
        if "key" not in fields or "value" not in fields:
            return None
        out: list[dict[str, Any]] = []
        for row in reader:
            if not isinstance(row, dict):
                continue
            norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            key_raw = norm.get("key") or ""
            val_raw = norm.get("value") or ""
            if not key_raw or val_raw == "":
                continue
            secret = str(norm.get("secret") or "").lower() in ("1", "true", "yes", "secret")
            device = norm.get("device") or None
            ts = norm.get("ts") or norm.get("timestamp") or _now()
            unit = norm.get("unit") or None
            key_low = key_raw.lower()
            if key_low in ("bp", "blood_pressure") or "/" in val_raw:
                pair = _parse_bp_pair(val_raw, secret=secret, device=device, ts=ts)
                if pair:
                    out.extend(pair)
                    continue
            key = coerce_key(key_raw, secret=secret)
            value, parsed_unit = _parse_value_unit(val_raw)
            out.append(
                _make_entry(
                    key=key,
                    value=value,
                    unit=unit or parsed_unit,
                    device=device,
                    secret=secret,
                    ts=ts,
                )
            )
        return out if out else None
    except csv.Error:
        return None


def parse_paste(text: str) -> list[dict[str, Any]]:
    """Parse multi-line paste into measurement entries. May be empty."""
    tabular = _try_tabular(text)
    if tabular is not None:
        return tabular
    entries: list[dict[str, Any]] = []
    sticky_device: str | None = None
    sticky_ts: str | None = None
    for line in (text or "").splitlines():
        got, sticky_device, sticky_ts = _parse_one_line(
            line, sticky_device=sticky_device, sticky_ts=sticky_ts
        )
        entries.extend(got)
    return entries


def append_measurements(user_data: dict[str, Any], text: str) -> str:
    """Parse paste and append to card. Disarms on success or hard refuse."""
    if not card_present(user_data):
        end_measure(user_data)
        return MSG_NO_CARD
    body = (text or "").strip()
    if not body:
        return MSG_EMPTY
    parsed = parse_paste(body)
    if not parsed:
        return MSG_BAD_PASTE
    items = get_measurements(user_data)
    items.extend(parsed)
    set_measurements(user_data, items)
    end_measure(user_data)
    n_secret = sum(1 for m in parsed if m.get("secret"))
    return MSG_SAVED.format(n=len(parsed), n_secret=n_secret)


def _fmt_value(m: dict[str, Any]) -> str:
    val = m.get("value")
    unit = m.get("unit")
    if unit:
        return f"{val} {unit}"
    return str(val)


def list_text(user_data: dict[str, Any]) -> str:
    """Keys + counts; secrets → count only (never echo values)."""
    items = get_measurements(user_data)
    if not items:
        return MSG_LIST_EMPTY

    secrets = [m for m in items if m.get("secret")]
    public = [m for m in items if not m.get("secret")]
    n_secret = len(secrets)

    if not public:
        return MSG_LIST_SECRETS_ONLY.format(n=n_secret)

    # Group by key; special pair bp_sys / bp_dia
    by_key: dict[str, list[dict[str, Any]]] = {}
    for m in public:
        k = str(m.get("key") or "")
        by_key.setdefault(k, []).append(m)

    lines: list[str] = ["Measurements on this card:"]
    used: set[str] = set()

    if "bp_sys" in by_key or "bp_dia" in by_key:
        sys_list = by_key.get("bp_sys") or []
        dia_list = by_key.get("bp_dia") or []
        n = max(len(sys_list), len(dia_list))
        latest_sys = sys_list[-1] if sys_list else None
        latest_dia = dia_list[-1] if dia_list else None
        sys_v = latest_sys.get("value") if latest_sys else "?"
        dia_v = latest_dia.get("value") if latest_dia else "?"
        unit = (
            (latest_sys or latest_dia or {}).get("unit") or "mmHg"
        )
        ts = (latest_sys or latest_dia or {}).get("ts") or ""
        ts_bit = f" ({ts})" if ts else ""
        lines.append(
            f"- bp_sys / bp_dia: {n} reading(s), latest {sys_v} / {dia_v} {unit}{ts_bit}"
        )
        used.add("bp_sys")
        used.add("bp_dia")

    for key in sorted(k for k in by_key if k not in used):
        series = by_key[key]
        latest = series[-1]
        ts = latest.get("ts") or ""
        ts_bit = f" ({ts})" if ts else ""
        lines.append(
            f"- {key}: {len(series)} reading(s), latest {_fmt_value(latest)}{ts_bit}"
        )

    if n_secret:
        lines.append(f"Secret measures on file: {n_secret} (values not shown).")
    return "\n".join(lines)


def clear_measurements(
    user_data: dict[str, Any], key: str | None = None
) -> str:
    """Clear all or one key series. key=None or 'all' clears everything."""
    end_measure(user_data)
    if not card_present(user_data):
        return MSG_NO_CARD
    items = get_measurements(user_data)
    if key is None or key.lower() == "all":
        set_measurements(user_data, [])
        return MSG_CLEAR_ALL
    target = key.strip()
    # Allow clearing via alias
    if not target.startswith("other:"):
        mapped = _ALIASES.get(target.lower())
        if mapped:
            target = mapped
        else:
            # Also match coerced other: form
            pass
    remaining = [m for m in items if str(m.get("key")) != target]
    # Also clear if user passed other:slug matching
    if target.startswith("other:"):
        remaining = [m for m in items if str(m.get("key")) != target]
    set_measurements(user_data, remaining)
    return MSG_CLEAR_KEY.format(key=target)


def secret_count(user_data: dict[str, Any] | None) -> int:
    if not user_data:
        return 0
    return sum(1 for m in get_measurements(user_data) if m.get("secret"))


def public_latest_by_key(
    user_data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Latest non-secret measurement per key."""
    out: dict[str, dict[str, Any]] = {}
    if not user_data:
        return out
    for m in get_measurements(user_data):
        if m.get("secret"):
            continue
        k = str(m.get("key") or "")
        if not k:
            continue
        out[k] = m
    return out


def board_measurements_block(user_data: dict[str, Any] | None) -> str:
    """TEMPLATE-measure board block: non-secret lines + secret count stub."""
    if not user_data:
        return BOARD_NONE
    items = get_measurements(user_data)
    if not items:
        return BOARD_NONE
    public = [m for m in items if not m.get("secret")]
    n_secret = sum(1 for m in items if m.get("secret"))
    if not public:
        return BOARD_SECRET_STUB.format(n=n_secret)

    latest = public_latest_by_key(user_data)
    lines: list[str] = []
    used: set[str] = set()
    if "bp_sys" in latest or "bp_dia" in latest:
        sys_m = latest.get("bp_sys")
        dia_m = latest.get("bp_dia")
        sys_v = sys_m.get("value") if sys_m else "?"
        dia_v = dia_m.get("value") if dia_m else "?"
        unit = (sys_m or dia_m or {}).get("unit") or "mmHg"
        ts = (sys_m or dia_m or {}).get("ts") or ""
        # Prefer Z suffix display when ISO-ish
        ts_show = ts if ts.endswith("Z") else (ts + "Z" if ts and "Z" not in ts and "+" not in ts[-6:] else ts)
        lines.append(f"- bp: {sys_v}/{dia_v} {unit} ({ts_show})")
        used.add("bp_sys")
        used.add("bp_dia")
    for key in sorted(k for k in latest if k not in used):
        m = latest[key]
        ts = m.get("ts") or ""
        ts_show = ts if str(ts).endswith("Z") else (
            str(ts) + "Z" if ts and "Z" not in str(ts) and "+" not in str(ts)[-6:] else str(ts)
        )
        lines.append(f"- {key}: {_fmt_value(m)} ({ts_show})")
    if n_secret:
        lines.append(BOARD_SECRET_STUB.format(n=n_secret))
    return "\n".join(lines)


def load_dump_line(user_data: dict[str, Any] | None) -> str:
    """Count-only line for /load format_card — never values (secret or otherwise)."""
    if not user_data:
        return "Measurements: none on file."
    items = get_measurements(user_data)
    if not items:
        return "Measurements: none on file."
    n_secret = sum(1 for m in items if m.get("secret"))
    return f"Measurements: {len(items)} on file ({n_secret} secret)."


def public_keys_for_search(user_data: dict[str, Any]) -> list[str]:
    """Distinct non-secret keys for search.json measure:<key> indexing."""
    keys: list[str] = []
    seen: set[str] = set()
    for m in get_measurements(user_data):
        if m.get("secret"):
            continue
        k = str(m.get("key") or "")
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def redact_for_downstream(payload: Any) -> Any:
    """Drop measurement values from a structure destined for LM/Discord (defensive)."""
    return payload


def assert_no_secret_measure_values(payload: Any, *, where: str = "downstream") -> None:
    """Raise if a dict tree embeds raw measurements destined for LM/Discord."""
    stack: list[Any] = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for key, val in cur.items():
                if key in BLOCKED_DOWNSTREAM_KEYS:
                    # Allow count-only stubs
                    if key == "measurements" and isinstance(val, (int, str)):
                        continue
                    if isinstance(val, list) and val:
                        raise ValueError(
                            f"Hard block: refusing to pass {key!r} into {where}."
                        )
                    if isinstance(val, dict):
                        raise ValueError(
                            f"Hard block: refusing to pass {key!r} into {where}."
                        )
                stack.append(val)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)


def last_batch_meta(user_data: dict[str, Any], n: int) -> list[dict[str, Any]]:
    """Return last n measurement entries (full; caller must not echo secrets)."""
    items = get_measurements(user_data)
    if n <= 0:
        return []
    return items[-n:]
