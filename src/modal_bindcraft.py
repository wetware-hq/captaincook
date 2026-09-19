"""Modal compute client for BindCraft (/design binder).

Modal is GPU compute only. Never send clinic.md, biometrics, Telegram tokens,
patient_files, or notes. Payload is limited to target sequence/CIF + optional
hotspot + N.

Fail-closed: missing tokens, missing MODAL_BINDCRAFT_APP, undeployed app,
timeouts, or errors → raise; callers refuse with COPY (no invented binders).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Distinct from BINDCRAFT_HOME refuse — app/weights not on Modal yet.
MSG_MODAL_APP_NOT_DEPLOYED = (
    "This request cannot proceed. Modal credentials are present, but the "
    "BindCraft Modal app is not deployed yet (set MODAL_BINDCRAFT_APP and "
    "deploy modal_app/bindcraft_app.py with GPU image + weights volume). "
    "No binder design was started. Ligand design via /design ligand remains "
    "available if Boltz is configured."
)

MSG_MODAL_JOB_FAILED = (
    "This request cannot proceed. The Modal BindCraft job failed or timed out. "
    "No binder design was started. Ligand design via /design ligand remains "
    "available if Boltz is configured."
)

# Keys that must never appear in a Modal payload (PHI / secrets / patient store).
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "clinic",
        "clinic_md",
        "biometrics",
        "patient_files",
        "patient_id",
        "telegram_bot_token",
        "telegram_token",
        "note",
        "note_body",
        "notes",
        "age_years",
        "sex",
        "weight_kg",
        "height_cm",
        "bmi",
        "scribe",
        "inbox",
        "secrets",
        "biohub_api_token",
        "boltz_api_key",
    }
)


@dataclass(frozen=True)
class ModalBinderResult:
    """Real Modal job output — never fabricate designs when empty/failed."""

    designs: list[dict[str, Any]]
    run_id: str | None = None
    artifact_paths: list[str] = field(default_factory=list)
    fasta_bytes: bytes | None = None
    cif_bytes_list: list[bytes] = field(default_factory=list)


def modal_tokens_present(
    token_id: str | None = None,
    token_secret: str | None = None,
) -> bool:
    tid = (token_id if token_id is not None else os.getenv("MODAL_TOKEN_ID", "")).strip()
    tsec = (
        token_secret
        if token_secret is not None
        else os.getenv("MODAL_TOKEN_SECRET", "")
    ).strip()
    return bool(tid and tsec)


def modal_app_configured(app_name: str | None = None) -> bool:
    name = (
        app_name
        if app_name is not None
        else os.getenv("MODAL_BINDCRAFT_APP", "")
    ).strip()
    return bool(name)


def build_modal_payload(
    *,
    target_sequence: str | None = None,
    cif_path: Path | str | None = None,
    cif_bytes: bytes | None = None,
    hotspot: list[str] | None = None,
    n_designs: int = 5,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a PHI-free Modal job payload.

    Only target seq/CIF + optional hotspot + N. Raises if forbidden keys sneak in.
    """
    payload: dict[str, Any] = {
        "n_designs": int(n_designs),
    }
    if target_sequence is not None:
        seq = "".join(str(target_sequence).split()).upper()
        if seq:
            payload["target_sequence"] = seq
    if cif_bytes is not None:
        payload["cif_bytes"] = cif_bytes
    elif cif_path is not None:
        path = Path(cif_path)
        if path.is_file():
            payload["cif_bytes"] = path.read_bytes()
            payload["cif_name"] = path.name
    if hotspot:
        # Pass through as supplied — never invent residues.
        payload["hotspot"] = [str(h) for h in hotspot]

    if extra:
        for k, v in extra.items():
            if k.lower() in _FORBIDDEN_PAYLOAD_KEYS or k in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"Forbidden key in Modal payload: {k}")
            if k in payload:
                continue
            payload[k] = v

    _assert_no_phi(payload)
    return payload


def _assert_no_phi(payload: dict[str, Any]) -> None:
    for k in payload:
        lk = str(k).lower()
        if lk in _FORBIDDEN_PAYLOAD_KEYS or str(k) in _FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError(f"Forbidden key in Modal payload: {k}")


def sync_binder_artifacts(
    *,
    dest_dir: Path,
    result: ModalBinderResult,
) -> list[str]:
    """Write binder FASTA/CIF artifacts under dest_dir. Returns absolute paths."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    run_id = result.run_id or uuid.uuid4().hex[:12]
    if result.fasta_bytes:
        p = dest_dir / f"binder_{run_id}.fasta"
        p.write_bytes(result.fasta_bytes)
        written.append(str(p.resolve()))
    for i, blob in enumerate(result.cif_bytes_list or []):
        p = dest_dir / f"binder_{run_id}_{i}.cif"
        p.write_bytes(blob)
        written.append(str(p.resolve()))
    for ap in result.artifact_paths or []:
        src = Path(ap)
        if src.is_file():
            target = dest_dir / src.name
            if src.resolve() != target.resolve():
                target.write_bytes(src.read_bytes())
            written.append(str(target.resolve()))
    return written


class ModalBindCraftError(RuntimeError):
    """Fail-closed Modal binder error (app missing, job failed, etc.)."""

    def __init__(self, message: str, *, kind: str = "failed") -> None:
        super().__init__(message)
        self.kind = kind  # "not_deployed" | "no_tokens" | "failed"


def run_bindcraft_modal(
    *,
    target_sequence: str | None = None,
    cif_path: Path | str | None = None,
    hotspot: list[str] | None = None,
    n_designs: int = 5,
    token_id: str | None = None,
    token_secret: str | None = None,
    app_name: str | None = None,
    timeout_sec: int = 10800,
) -> ModalBinderResult:
    """Invoke Modal BindCraft job. Fail-closed — never invents binders.

    Until the Modal app + GPU image + weights volume exist, raises
    ModalBindCraftError(kind='not_deployed').
    """
    tid = (token_id if token_id is not None else os.getenv("MODAL_TOKEN_ID", "")).strip()
    tsec = (
        token_secret
        if token_secret is not None
        else os.getenv("MODAL_TOKEN_SECRET", "")
    ).strip()
    app = (
        app_name if app_name is not None else os.getenv("MODAL_BINDCRAFT_APP", "")
    ).strip()

    if not (tid and tsec):
        raise ModalBindCraftError(
            "Modal tokens are not configured (MODAL_TOKEN_ID / MODAL_TOKEN_SECRET).",
            kind="no_tokens",
        )
    if not app:
        raise ModalBindCraftError(MSG_MODAL_APP_NOT_DEPLOYED, kind="not_deployed")

    payload = build_modal_payload(
        target_sequence=target_sequence,
        cif_path=cif_path,
        hotspot=hotspot,
        n_designs=n_designs,
    )

    # Ensure Modal SDK sees credentials without logging them.
    os.environ.setdefault("MODAL_TOKEN_ID", tid)
    os.environ.setdefault("MODAL_TOKEN_SECRET", tsec)

    try:
        import modal  # type: ignore
    except ImportError as exc:
        raise ModalBindCraftError(
            MSG_MODAL_APP_NOT_DEPLOYED
            + " (modal package not installed on poller host).",
            kind="not_deployed",
        ) from exc

    try:
        # Look up remote function; if app isn't deployed this fails closed.
        fn = modal.Function.from_name(app, "run_bindcraft")
        call = fn.spawn(payload) if hasattr(fn, "spawn") else None
        if call is not None and hasattr(call, "get"):
            raw = call.get(timeout=timeout_sec)
        else:
            # Synchronous remote call
            raw = fn.remote(payload)
    except ModalBindCraftError:
        raise
    except Exception as exc:  # noqa: BLE001
        # Undeployed app, auth failure, timeout, etc. — never invent binders.
        msg = str(exc).lower()
        if any(
            s in msg
            for s in (
                "not found",
                "lookup failed",
                "does not exist",
                "no such app",
                "unknown app",
                "function not found",
            )
        ):
            raise ModalBindCraftError(MSG_MODAL_APP_NOT_DEPLOYED, kind="not_deployed") from exc
        logger.warning("modal bindcraft job failed: %s", type(exc).__name__)
        raise ModalBindCraftError(MSG_MODAL_JOB_FAILED, kind="failed") from exc

    return _parse_modal_result(raw)


def _parse_modal_result(raw: Any) -> ModalBinderResult:
    if raw is None:
        raise ModalBindCraftError(MSG_MODAL_JOB_FAILED, kind="failed")
    if isinstance(raw, ModalBinderResult):
        if not raw.designs:
            raise ModalBindCraftError(MSG_MODAL_JOB_FAILED, kind="failed")
        return raw
    if not isinstance(raw, dict):
        raise ModalBindCraftError(MSG_MODAL_JOB_FAILED, kind="failed")
    designs = raw.get("designs") or []
    if not isinstance(designs, list) or not designs:
        raise ModalBindCraftError(MSG_MODAL_JOB_FAILED, kind="failed")
    fasta = raw.get("fasta_bytes")
    if isinstance(fasta, str):
        fasta = fasta.encode("utf-8")
    cifs = raw.get("cif_bytes_list") or []
    cif_list: list[bytes] = []
    for c in cifs:
        if isinstance(c, str):
            cif_list.append(c.encode("utf-8"))
        elif isinstance(c, (bytes, bytearray)):
            cif_list.append(bytes(c))
    return ModalBinderResult(
        designs=list(designs),
        run_id=raw.get("run_id"),
        artifact_paths=list(raw.get("artifact_paths") or []),
        fasta_bytes=fasta if isinstance(fasta, (bytes, bytearray)) else None,
        cif_bytes_list=cif_list,
    )
