"""BindCraft protein-binder design — fail-closed until weights or Modal app ready.

Never invents binders. Prefer Modal GPU when MODAL_TOKEN_ID/SECRET are set;
otherwise local BINDCRAFT_HOME. Callers refuse with COPY-design strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import modal_bindcraft as modal_bc


@dataclass(frozen=True)
class BinderDesignResult:
    """Result shape for BindCraft / Modal runners."""

    designs: list[dict[str, Any]]
    run_id: str | None = None
    artifact_paths: list[str] = field(default_factory=list)
    source: str = "local"  # "local" | "modal"


def bindcraft_home_ok(home: str | None) -> bool:
    """True only when BINDCRAFT_HOME is a non-empty existing directory."""
    if not home or not str(home).strip():
        return False
    return Path(str(home).strip()).is_dir()


def weights_present(home: str | None) -> bool:
    """Heuristic: AF2 / BindCraft weight dirs under home. Never downloads."""
    if not bindcraft_home_ok(home):
        return False
    root = Path(str(home).strip())
    # Common BindCraft / AF2 layout markers — any one is enough to attempt a run.
    markers = (
        root / "params",
        root / "alphafold_params",
        root / "AF2_params",
        root / "bindcraft" / "params",
        root / "weights",
    )
    return any(m.exists() for m in markers)


def modal_creds_ok(token_id: str | None, token_secret: str | None) -> bool:
    """True when both Modal token id and secret are non-empty (compute-only; no PHI).

    Uses only the passed values (typically from Settings). Does not read os.environ —
    the bot loads MODAL_* via config.load_settings / dotenv.
    """
    return bool((token_id or "").strip() and (token_secret or "").strip())


def binder_compute_ready(
    home: str | None,
    *,
    modal_token_id: str | None = None,
    modal_token_secret: str | None = None,
) -> bool:
    """True if local BINDCRAFT_HOME exists OR Modal credentials are set.

    Modal is GPU compute only — never a patient-store. Callers still must not
    invent binders; the runner remains fail-closed until the Modal app/weights
    are deployed (or local weights exist).
    """
    return bindcraft_home_ok(home) or modal_creds_ok(modal_token_id, modal_token_secret)


def run_binder_design(
    *,
    structure_path: Path | str | None = None,
    n_designs: int = 5,
    hotspot: list[str] | None = None,
    home: str | None = None,
    timeout_sec: int = 3600,
    target_sequence: str | None = None,
    modal_token_id: str | None = None,
    modal_token_secret: str | None = None,
    modal_bindcraft_app: str | None = None,
    prefer_modal: bool = True,
) -> BinderDesignResult:
    """Run BindCraft via Modal (preferred when tokens set) or local home.

    Stub/fail-closed if Modal app undeployed and local weights missing —
    never fake binders.
    """
    use_modal = prefer_modal and modal_creds_ok(modal_token_id, modal_token_secret)
    if use_modal:
        result = modal_bc.run_bindcraft_modal(
            target_sequence=target_sequence,
            cif_path=structure_path,
            hotspot=hotspot,
            n_designs=n_designs,
            token_id=modal_token_id,
            token_secret=modal_token_secret,
            app_name=modal_bindcraft_app,
            timeout_sec=timeout_sec,
        )
        return BinderDesignResult(
            designs=list(result.designs),
            run_id=result.run_id,
            artifact_paths=list(result.artifact_paths),
            source="modal",
        )

    if not bindcraft_home_ok(home):
        raise RuntimeError(
            "BindCraft is not configured on this host (BINDCRAFT_HOME)."
        )
    if not weights_present(home):
        raise RuntimeError(
            "BindCraft weights are not present under BINDCRAFT_HOME. "
            "No binder design was started."
        )
    raise NotImplementedError(
        "BindCraft runner is not wired on this build. No binder design was started."
    )
