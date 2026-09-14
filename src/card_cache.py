"""Fingerprint + per-chat result cache for /view.

Match key locked in docs/FEATURE-card-cache-view.md.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context_card import ContextCard

CARD_CACHE_KEY = "card_cache"
CACHE_MAX = 5
TTL_SEC = 24 * 60 * 60


def fingerprint(card: ContextCard) -> str:
    """SHA-256 of the canonical formal fields.

    raw_text / last_run are ignored. Patient biometric secrets and patient_files
    live on the card dict, not the dataclass, and are therefore excluded from
    this fingerprint.
    """
    gene = (card.gene or "").strip().upper().replace("-", "") or None
    variant = (card.variant or "").strip().upper().replace("-", "") or None
    if variant in ("", "NONE"):
        variant = None
    seq = "".join((card.sequence or "").split()).upper() or None
    smiles = (card.smiles or "").strip() or None
    state = (card.state or "").strip().upper() or None
    payload = {
        "chemical_space": card.chemical_space,
        "covalent": card.covalent,
        "gene": gene,
        "intent": card.intent,
        "n_designs": int(card.n_designs),
        "sequence": seq,
        "smiles": smiles,
        "state": state,
        "variant": variant,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def prune_cache(user_data: dict[str, Any]) -> None:
    cache = user_data.get(CARD_CACHE_KEY) or {}
    if not cache:
        return
    now = time.time()
    kept: dict[str, Any] = {}
    for fp, entry in cache.items():
        if not isinstance(entry, dict):
            continue
        ts = float(entry.get("cached_ts") or 0)
        if ts and now - ts > TTL_SEC:
            continue
        kept[fp] = entry
    user_data[CARD_CACHE_KEY] = kept


def remember_result(user_data: dict[str, Any], card: ContextCard) -> None:
    """Write/update cache when a run succeeds on a loaded card."""
    if not card.last_run or not card.last_run.get("interpretation"):
        return
    prune_cache(user_data)
    cache: dict[str, Any] = user_data.setdefault(CARD_CACHE_KEY, {})
    fp = fingerprint(card)
    last = card.last_run or {}
    cache[fp] = {
        "interpretation": last.get("interpretation"),
        "result_png": last.get("result_png"),
        "files": list(last.get("files") or []),
        "cached_ts": time.time(),
        "at": last.get("at")
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if len(cache) > CACHE_MAX:
        oldest = sorted(cache.items(), key=lambda kv: float(kv[1].get("cached_ts") or 0))
        for old_fp, _ in oldest[: len(cache) - CACHE_MAX]:
            cache.pop(old_fp, None)


def lookup_result(user_data: dict[str, Any], card: ContextCard) -> dict[str, Any] | None:
    """Return a cache entry if this card matches a completed run."""
    prune_cache(user_data)
    cache = user_data.get(CARD_CACHE_KEY) or {}
    entry = cache.get(fingerprint(card))
    if not isinstance(entry, dict):
        return None
    interpretation = entry.get("interpretation") or (entry.get("last_run") or {}).get(
        "interpretation"
    )
    if not interpretation:
        return None
    return entry


def clear_cache(user_data: dict[str, Any]) -> None:
    user_data.pop(CARD_CACHE_KEY, None)


def result_png_path(entry: dict[str, Any] | None) -> Path | None:
    if not entry:
        return None
    last = entry.get("last_run") if "last_run" in entry else entry
    raw = entry.get("result_png") or (last or {}).get("result_png")
    if raw and Path(str(raw)).exists():
        return Path(str(raw))
    for rec in (entry.get("files") or (last or {}).get("files") or []):
        if not isinstance(rec, dict):
            continue
        if rec.get("kind") in ("result_png", "png_archive"):
            path = Path(str(rec.get("path") or ""))
            if path.exists():
                return path
    return None


def file_of_kind(entry: dict[str, Any] | None, kind: str) -> Path | None:
    if not entry:
        return None
    last = entry.get("last_run") if isinstance(entry.get("last_run"), dict) else {}
    for rec in (entry.get("files") or last.get("files") or []):
        if not isinstance(rec, dict):
            continue
        if rec.get("kind") == kind:
            path = Path(str(rec.get("path") or ""))
            if path.exists():
                return path
    return None


if __name__ == "__main__":
    a = ContextCard(intent="small_molecule_design", gene="kras", variant="G12C", sequence="MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRTGEGFLCVFAINNTKSFEDIHHYREQIKRVKDSEDVPMVLVGNKCDLPSRTVDTKQAQDLARSYGIPFIETSAKTRQGVDDAFYTLVREIRKHKEK", n_designs=10, chemical_space="enamine_real", state="GDP", covalent=False)
    b = ContextCard(intent="small_molecule_design", gene="KRAS", variant="g12c", sequence=a.sequence.lower(), n_designs=10, chemical_space="enamine_real", state="gdp", covalent=False, raw_text="ignored")
    c = ContextCard(intent="small_molecule_design", gene="KRAS", variant="G12D", sequence=a.sequence, n_designs=10, chemical_space="enamine_real", state="GDP", covalent=False)
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint(c)
    print("card_cache self-check passed")
