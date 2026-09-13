"""Boltz hosted API client wrappers.

Verified against:
  https://api.boltz.bio/docs/guides/predictions/
  https://api.boltz.bio/docs/guides/authentication/
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 60 * 30  # 30 minutes


@dataclass
class BoltzResult:
    summary: str
    cif_path: Path | None = None


class BoltzClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self) -> Any:
        from boltz_api import Boltz

        return Boltz(
            base_url=self.settings.boltz_base_url,
            api_key=self.settings.boltz_api_key,
        )

    def predict_structure(
        self, sequence: str, ligand_smiles: str | None = None
    ) -> BoltzResult:
        """Submit structure (+ optional ligand binding), poll, download best CIF."""
        entities: list[dict[str, Any]] = [
            {"type": "protein", "value": sequence, "chain_ids": ["A"]},
        ]
        prediction_input: dict[str, Any] = {
            "entities": entities,
            "num_samples": 1,
        }
        if ligand_smiles:
            entities.append(
                {
                    "type": "ligand_smiles",
                    "value": ligand_smiles,
                    "chain_ids": ["B"],
                }
            )
            prediction_input["binding"] = {
                "type": "ligand_protein_binding",
                "binder_chain_id": "B",
            }

        client = self._client()
        prediction = client.predictions.structure_and_binding.start(
            model=self.settings.boltz_model,
            input=prediction_input,
        )
        prediction = self._poll(client, prediction)

        if getattr(prediction, "status", None) == "failed":
            err = getattr(prediction, "error", None)
            raise RuntimeError(_format_boltz_error(err))

        output = getattr(prediction, "output", None)
        if output is None:
            raise RuntimeError("Boltz prediction succeeded but returned no output.")

        metrics_lines = _format_metrics(output)
        cif_path = self._download_best_cif(client, prediction, output)

        mode = "structure + binding" if ligand_smiles else "structure only"
        summary = (
            f"Boltz ({self.settings.boltz_model}) — {mode}\n"
            f"Length: {len(sequence)} aa\n"
            + "\n".join(metrics_lines)
        )
        return BoltzResult(summary=summary, cif_path=cif_path)

    def _poll(self, client: Any, prediction: Any) -> Any:
        deadline = time.monotonic() + POLL_TIMEOUT_SEC
        while getattr(prediction, "status", None) not in ("succeeded", "failed"):
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Boltz prediction timed out after {POLL_TIMEOUT_SEC // 60} minutes "
                    f"(id={getattr(prediction, 'id', '?')})."
                )
            time.sleep(POLL_INTERVAL_SEC)
            prediction = client.predictions.structure_and_binding.retrieve(prediction.id)
        return prediction

    def _download_best_cif(
        self, client: Any, prediction: Any, output: Any
    ) -> Path | None:
        """Prefer experiments.download_results; fall back to structure URL."""
        work = Path(tempfile.mkdtemp(prefix="boltz_run_"))
        try:
            try:
                run_dir = client.experiments.download_results(
                    id=prediction.id, name=work.name
                )
                run_path = Path(run_dir)
                cif = _find_cif(run_path)
                if cif is not None:
                    dest = Path(
                        tempfile.NamedTemporaryFile(
                            prefix="boltz_", suffix=".cif", delete=False
                        ).name
                    )
                    shutil.copy2(cif, dest)
                    return dest
            except Exception as dl_exc:  # noqa: BLE001
                logger.warning("download_results failed, trying structure URL: %s", dl_exc)

            url = _best_structure_url(output)
            if not url:
                return None
            dest = Path(
                tempfile.NamedTemporaryFile(
                    prefix="boltz_", suffix=".cif", delete=False
                ).name
            )
            with httpx.Client(timeout=120.0) as http:
                resp = http.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            return dest
        finally:
            shutil.rmtree(work, ignore_errors=True)


    def estimate_design_cost(
        self,
        sequence: str,
        num_molecules: int = 10,
        *,
        pocket_residues: dict[str, list[int]] | None = None,
        reference_ligands: list[str] | None = None,
        chemical_space: str = "enamine_real",
        bonds: list[dict[str, Any]] | None = None,
        constraints: list[dict[str, Any]] | None = None,
    ):
        """Live estimate-cost for small-molecule:design. API floor is 10 molecules."""
        from .small_molecule_design import SmallMoleculeDesignClient

        return SmallMoleculeDesignClient(self.settings).estimate_cost(
            sequence,
            num_molecules,
            pocket_residues=pocket_residues,
            reference_ligands=reference_ligands,
            chemical_space=chemical_space,  # type: ignore[arg-type]
            bonds=bonds,
            constraints=constraints,
        )

    def design_small_molecules(
        self,
        sequence: str,
        num_molecules: int = 10,
        *,
        pocket_residues: dict[str, list[int]] | None = None,
        reference_ligands: list[str] | None = None,
        chemical_space: str = "enamine_real",
        bonds: list[dict[str, Any]] | None = None,
        constraints: list[dict[str, Any]] | None = None,
        covalent: bool | None = None,
        max_wait_sec: int | None = None,
        max_usd: float | None = None,
        idempotency_key: str | None = None,
    ):
        """Start / poll / rank small-molecule design. Telegram UX calls this.

        num_molecules below 10 is clamped to 10 (API minimum). covalent=True
        without bonds raises; pass explicit bonds for G12C-style warheads.
        """
        from .small_molecule_design import SmallMoleculeDesignClient

        if covalent and not bonds:
            raise RuntimeError(
                "covalent=True needs an explicit bonds payload. "
                "Do not invent a warhead attachment."
            )
        return SmallMoleculeDesignClient(self.settings).design(
            sequence,
            num_molecules,
            pocket_residues=pocket_residues,
            reference_ligands=reference_ligands,
            chemical_space=chemical_space,  # type: ignore[arg-type]
            bonds=bonds,
            constraints=constraints,
            idempotency_key=idempotency_key,
            max_wait_sec=max_wait_sec,
            max_usd=max_usd,
        )


def _find_cif(root: Path) -> Path | None:
    if not root.exists():
        return None
    cifs = sorted(root.rglob("*.cif"))
    if not cifs:
        return None
    # Prefer sample_0 / predicted_structure style names.
    for preferred in ("sample_0.cif", "sample_0_predicted_structure.cif"):
        for c in cifs:
            if c.name == preferred:
                return c
    return cifs[0]


def _best_structure_url(output: Any) -> str | None:
    best = getattr(output, "best_sample", None)
    if best is not None:
        structure = getattr(best, "structure", None)
        url = getattr(structure, "url", None) if structure is not None else None
        if url:
            return str(url)
        if isinstance(best, dict):
            st = best.get("structure") or {}
            if isinstance(st, dict) and st.get("url"):
                return str(st["url"])

    samples = getattr(output, "all_sample_results", None) or []
    if isinstance(samples, list) and samples:
        first = samples[0]
        structure = getattr(first, "structure", None)
        url = getattr(structure, "url", None) if structure is not None else None
        if url:
            return str(url)
        if isinstance(first, dict):
            st = first.get("structure") or {}
            if isinstance(st, dict) and st.get("url"):
                return str(st["url"])
    return None


def _format_metrics(output: Any) -> list[str]:
    lines: list[str] = []
    best = getattr(output, "best_sample", None)
    metrics = None
    if best is not None:
        metrics = getattr(best, "metrics", None)
        if metrics is None and isinstance(best, dict):
            metrics = best.get("metrics")

    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    for key, label in (
        ("structure_confidence", "structure_confidence"),
        ("ptm", "pTM"),
        ("iptm", "ipTM"),
        ("complex_plddt", "complex_plddt"),
    ):
        val = _get(metrics, key)
        if val is not None:
            try:
                lines.append(f"{label}: {float(val):.3f}")
            except (TypeError, ValueError):
                lines.append(f"{label}: {val}")

    binding = getattr(output, "binding_metrics", None)
    if binding is None and isinstance(output, dict):
        binding = output.get("binding_metrics")
    if binding is not None:
        for key, label in (
            ("binding_confidence", "binding_confidence"),
            ("optimization_score", "optimization_score"),
        ):
            val = _get(binding, key)
            if val is not None:
                try:
                    lines.append(f"{label}: {float(val):.3f}")
                except (TypeError, ValueError):
                    lines.append(f"{label}: {val}")

    if not lines:
        lines.append("Prediction succeeded (see attached CIF).")
    return lines


def _format_boltz_error(err: Any) -> str:
    if err is None:
        return "Boltz prediction failed (no error details)."
    if isinstance(err, dict):
        code = err.get("code", "")
        message = err.get("message", str(err))
        return f"Boltz API error{f' [{code}]' if code else ''}: {message}"
    code = getattr(err, "code", None)
    message = getattr(err, "message", None) or str(err)
    if code:
        return f"Boltz API error [{code}]: {message}"
    return f"Boltz API error: {message}"
