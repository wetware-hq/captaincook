"""Boltz small-molecule design + ADME client.

Owned by biomodels: submit/poll/download only. Telegram confirm UX and
sequence/variant resolution stay on the strategist side.

Verified against:
  https://api.boltz.bio/docs/guides/small-molecule-design/
  https://api.boltz.bio/docs/guides/costs/
  boltz-api 0.50.0 DesignResource.start / estimate_cost / retrieve / list_results

API floor is 10 molecules. ADME Tier-1 fields arrive on each design result
(no extra ADME job). Do not invent protein sequences.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .config import Settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 10
POLL_TIMEOUT_SEC = 60 * 60
MIN_MOLECULES = 10
MAX_MOLECULES = 100  # hard cap for this bot; API allows up to 1_000_000


@dataclass
class DesignCandidate:
    id: str
    smiles: str
    binding_confidence: float | None = None
    optimization_score: float | None = None
    structure_confidence: float | None = None
    iptm: float | None = None
    ptm: float | None = None
    complex_plddt: float | None = None
    adme_lipophilicity: float | None = None
    adme_permeability: float | None = None
    adme_solubility: str | None = None
    cif_path: Path | None = None


@dataclass
class DesignEstimate:
    estimated_cost_usd: float
    num_molecules: int
    cost_per_unit_usd: float | None
    clamped_from: int | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignResult:
    run_id: str
    status: str
    num_requested: int
    candidates: list[DesignCandidate]
    best_cif_path: Path | None
    estimated_cost_usd: float | None
    summary: str


class SmallMoleculeDesignClient:
    """Thin Boltz small-molecule:design wrapper (start / poll / list / download)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self) -> Any:
        from boltz_api import Boltz

        return Boltz(
            base_url=self.settings.boltz_base_url,
            api_key=self.settings.boltz_api_key,
        )

    @staticmethod
    def clamp_num_molecules(n: int) -> tuple[int, int | None]:
        if n < MIN_MOLECULES:
            return MIN_MOLECULES, n
        if n > MAX_MOLECULES:
            return MAX_MOLECULES, n
        return n, None

    def _target(
        self,
        sequence: str,
        *,
        pocket_residues: dict[str, list[int]] | None = None,
        reference_ligands: list[str] | None = None,
        bonds: list[dict[str, Any]] | None = None,
        constraints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        seq = "".join(sequence.split()).upper()
        if not seq:
            raise ValueError("Target sequence is empty. Resolve UniProt + mutation first.")
        target: dict[str, Any] = {
            "entities": [{"type": "protein", "value": seq, "chain_ids": ["A"]}],
        }
        if pocket_residues:
            target["pocket_residues"] = pocket_residues
        if reference_ligands:
            target["reference_ligands"] = reference_ligands
        if bonds:
            target["bonds"] = bonds
        if constraints:
            target["constraints"] = constraints
        return target

    def estimate_cost(
        self,
        sequence: str,
        num_molecules: int = MIN_MOLECULES,
        *,
        pocket_residues: dict[str, list[int]] | None = None,
        reference_ligands: list[str] | None = None,
        chemical_space: Literal["enamine_real", "none"] = "enamine_real",
        bonds: list[dict[str, Any]] | None = None,
        constraints: list[dict[str, Any]] | None = None,
    ) -> DesignEstimate:
        n, clamped_from = self.clamp_num_molecules(num_molecules)
        client = self._client()
        est = client.small_molecule.design.estimate_cost(
            target=self._target(
                sequence,
                pocket_residues=pocket_residues,
                reference_ligands=reference_ligands,
                bonds=bonds,
                constraints=constraints,
            ),
            num_molecules=n,
            chemical_space=chemical_space,
        )
        total = float(getattr(est, "estimated_cost_usd"))
        breakdown = getattr(est, "breakdown", None)
        per = None
        if breakdown is not None:
            raw_per = getattr(breakdown, "cost_per_unit_usd", None)
            if raw_per is not None:
                per = float(raw_per)
        return DesignEstimate(
            estimated_cost_usd=total,
            num_molecules=n,
            cost_per_unit_usd=per,
            clamped_from=clamped_from,
            raw={"estimated_cost_usd": str(getattr(est, "estimated_cost_usd"))},
        )

    def design(
        self,
        sequence: str,
        num_molecules: int = MIN_MOLECULES,
        *,
        pocket_residues: dict[str, list[int]] | None = None,
        reference_ligands: list[str] | None = None,
        chemical_space: Literal["enamine_real", "none"] = "enamine_real",
        bonds: list[dict[str, Any]] | None = None,
        constraints: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        download_best_cif: bool = True,
        max_wait_sec: int | None = None,
        max_usd: float | None = None,
    ) -> DesignResult:
        """Submit a design run, wait, rank by binding_confidence, optionally download best CIF.

        Caller must already have user confirmation and a real sequence.
        """
        n, _ = self.clamp_num_molecules(num_molecules)
        estimate = self.estimate_cost(
            sequence,
            n,
            pocket_residues=pocket_residues,
            reference_ligands=reference_ligands,
            chemical_space=chemical_space,
            bonds=bonds,
            constraints=constraints,
        )
        if max_usd is not None and estimate.estimated_cost_usd > max_usd:
            raise RuntimeError(
                f"Estimated cost US${estimate.estimated_cost_usd:.4f} exceeds "
                f"max_usd US${max_usd:.4f} for {n} molecules."
            )
        client = self._client()
        kwargs: dict[str, Any] = {
            "target": self._target(
                sequence,
                pocket_residues=pocket_residues,
                reference_ligands=reference_ligands,
                bonds=bonds,
                constraints=constraints,
            ),
            "num_molecules": n,
            "chemical_space": chemical_space,
        }
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key
        run = client.small_molecule.design.start(**kwargs)
        run = self._poll(client, run, max_wait_sec=max_wait_sec)
        status = getattr(run, "status", None)
        if status == "failed":
            err = getattr(run, "error", None)
            raise RuntimeError(_format_error(err))

        raw_results = list(client.small_molecule.design.list_results(run.id))
        candidates = [_to_candidate(r) for r in raw_results]
        candidates.sort(
            key=lambda c: (
                c.binding_confidence is not None,
                c.binding_confidence or 0.0,
            ),
            reverse=True,
        )

        best_cif: Path | None = None
        if download_best_cif and candidates:
            best_cif = self._download_best_cif(client, run.id, candidates[0])
            if best_cif is not None:
                candidates[0].cif_path = best_cif

        summary = _format_summary(run.id, status or "unknown", n, estimate, candidates)
        return DesignResult(
            run_id=str(run.id),
            status=str(status or "unknown"),
            num_requested=n,
            candidates=candidates,
            best_cif_path=best_cif,
            estimated_cost_usd=estimate.estimated_cost_usd,
            summary=summary,
        )

    def _poll(self, client: Any, run: Any, max_wait_sec: int | None = None) -> Any:
        timeout = max_wait_sec if max_wait_sec and max_wait_sec > 0 else POLL_TIMEOUT_SEC
        deadline = time.monotonic() + timeout
        while getattr(run, "status", None) not in ("succeeded", "failed", "stopped"):
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Boltz design timed out after {int(timeout) // 60} minutes "
                    f"(id={getattr(run, 'id', '?')})."
                )
            time.sleep(POLL_INTERVAL_SEC)
            run = client.small_molecule.design.retrieve(run.id)
        return run

    def _download_best_cif(
        self, client: Any, run_id: str, best: DesignCandidate
    ) -> Path | None:
        work = Path(tempfile.mkdtemp(prefix="boltz_des_"))
        try:
            try:
                run_dir = client.experiments.download_results(id=run_id, name=work.name)
                cif = _find_cif(Path(run_dir))
                if cif is not None:
                    dest = Path(
                        tempfile.NamedTemporaryFile(
                            prefix="boltz_des_", suffix=".cif", delete=False
                        ).name
                    )
                    shutil.copy2(cif, dest)
                    return dest
            except Exception as exc:  # noqa: BLE001
                logger.warning("design download_results failed: %s", exc)
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _to_candidate(result: Any) -> DesignCandidate:
    metrics = getattr(result, "metrics", None)
    adme = getattr(result, "adme", None)

    def _f(obj: Any, key: str) -> float | None:
        if obj is None:
            return None
        val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _s(obj: Any, key: str) -> str | None:
        if obj is None:
            return None
        val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        return str(val) if val is not None else None

    return DesignCandidate(
        id=str(getattr(result, "id", "")),
        smiles=str(getattr(result, "smiles", "") or ""),
        binding_confidence=_f(metrics, "binding_confidence"),
        optimization_score=_f(metrics, "optimization_score"),
        structure_confidence=_f(metrics, "structure_confidence"),
        iptm=_f(metrics, "iptm"),
        ptm=_f(metrics, "ptm"),
        complex_plddt=_f(metrics, "complex_plddt"),
        adme_lipophilicity=_f(adme, "lipophilicity"),
        adme_permeability=_f(adme, "permeability"),
        adme_solubility=_s(adme, "solubility"),
    )


def _find_cif(root: Path) -> Path | None:
    if not root.exists():
        return None
    cifs = sorted(root.rglob("*.cif"))
    return cifs[0] if cifs else None


def _format_error(err: Any) -> str:
    if err is None:
        return "Boltz design failed (no error details)."
    if isinstance(err, dict):
        code = err.get("code", "")
        message = err.get("message", str(err))
        return f"Boltz design error{f' [{code}]' if code else ''}: {message}"
    code = getattr(err, "code", None)
    message = getattr(err, "message", None) or str(err)
    if code:
        return f"Boltz design error [{code}]: {message}"
    return f"Boltz design error: {message}"


def _format_summary(
    run_id: str,
    status: str,
    n: int,
    estimate: DesignEstimate,
    candidates: list[DesignCandidate],
) -> str:
    lines = [
        f"Boltz small-molecule design — {status}",
        f"Run: {run_id}",
        f"Molecules: {n}  est. US${estimate.estimated_cost_usd:.4f}",
        "Ranked by binding_confidence (hit discovery). ADME is Tier-1 triage, not a measurement.",
        "Research use only. Not a validated inhibitor.",
    ]
    if estimate.clamped_from is not None:
        lines.append(
            f"Requested {estimate.clamped_from} molecules; API/bot clamp used {n}."
        )
    for i, c in enumerate(candidates[:8], 1):
        bc = f"{c.binding_confidence:.3f}" if c.binding_confidence is not None else "—"
        opt = f"{c.optimization_score:.3f}" if c.optimization_score is not None else "—"
        sol = c.adme_solubility or "—"
        lines.append(f"{i}. bind={bc}  opt={opt}  sol={sol}  {c.smiles}")
    if len(candidates) > 8:
        lines.append(f"… {len(candidates) - 8} more")
    return "\n".join(lines)
