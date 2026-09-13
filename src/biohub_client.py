"""Biohub (ESM) hosted API client wrappers.

Verified against:
  https://biohub.ai/learn/getting-started
  https://github.com/Biohub/esm README (ESMFold2 Biohub Platform section)
  https://www.biohub.ai/models/esmfold2
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass
class FoldResult:
    summary: str
    cif_path: Path | None = None
    used_fallback: bool = False


class BiohubClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _fold_client(self) -> Any:
        from esm.sdk.forge import SequenceStructureForgeInferenceClient

        return SequenceStructureForgeInferenceClient(
            model=self.settings.esmfold2_model,
            url=self.settings.biohub_url,
            token=self.settings.biohub_api_token,
        )

    def _esmc_client(self) -> Any:
        from esm.sdk.forge import ESMCForgeInferenceClient

        return ESMCForgeInferenceClient(
            model=self.settings.esmc_model,
            url=self.settings.biohub_url,
            token=self.settings.biohub_api_token,
        )

    def fold(self, sequence: str) -> FoldResult:
        """Run ESMFold2; on failure, fall back to a short ESMC embedding summary."""
        try:
            return self._fold_esmfold2(sequence)
        except Exception as fold_exc:  # noqa: BLE001 — surface API errors cleanly
            logger.warning("ESMFold2 failed, falling back to ESMC: %s", fold_exc)
            try:
                summary = self._esmc_summary(sequence)
                return FoldResult(
                    summary=(
                        f"ESMFold2 failed ({_short_err(fold_exc)}).\n"
                        f"ESMC fallback summary:\n{summary}"
                    ),
                    cif_path=None,
                    used_fallback=True,
                )
            except Exception as emb_exc:  # noqa: BLE001
                raise RuntimeError(
                    f"ESMFold2 error: {_short_err(fold_exc)}; "
                    f"ESMC fallback also failed: {_short_err(emb_exc)}"
                ) from emb_exc

    def _fold_esmfold2(self, sequence: str) -> FoldResult:
        from esm.sdk.api import FoldingConfig
        from esm.utils.structure.input_builder import ProteinInput, StructurePredictionInput

        client = self._fold_client()
        inp = StructurePredictionInput(
            sequences=[ProteinInput(id="A", sequence=sequence)]
        )
        # Fast path defaults suitable for a chat bot (docs use 20/100).
        config = FoldingConfig(num_loops=3, num_sampling_steps=50)
        result = client.fold_all_atom(inp, config=config)
        from esm.sdk.api import ESMProteinError

        if isinstance(result, ESMProteinError):
            raise RuntimeError(
                f"ESMFold2 API error {result.error_code}: {result.error_msg}"
            )
        if isinstance(result, list):
            result = result[0]
            if isinstance(result, ESMProteinError):
                raise RuntimeError(
                    f"ESMFold2 API error {result.error_code}: {result.error_msg}"
                )

        metrics_parts: list[str] = []
        for attr, label in (
            ("plddt", "pLDDT mean"),
            ("ptm", "pTM"),
            ("iptm", "ipTM"),
        ):
            value = getattr(result, attr, None)
            if value is None:
                continue
            try:
                # plddt may be an array; mean() if present.
                if hasattr(value, "mean"):
                    num = float(value.mean())
                else:
                    num = float(value)
                metrics_parts.append(f"{label}: {num:.3f}")
            except (TypeError, ValueError):
                continue

        cif_text = result.complex.to_mmcif()
        tmp = tempfile.NamedTemporaryFile(
            prefix="esmfold2_", suffix=".cif", delete=False
        )
        path = Path(tmp.name)
        tmp.close()
        path.write_text(cif_text, encoding="utf-8")

        summary = (
            f"ESMFold2 ({self.settings.esmfold2_model})\n"
            f"Length: {len(sequence)} aa\n"
            + ("\n".join(metrics_parts) if metrics_parts else "Structure predicted.")
        )
        return FoldResult(summary=summary, cif_path=path, used_fallback=False)

    def _esmc_summary(self, sequence: str) -> str:
        from esm.sdk.api import ESMProtein, LogitsConfig

        client = self._esmc_client()
        protein = ESMProtein(sequence=sequence)
        protein_tensor = client.encode(protein)
        from esm.sdk.api import ESMProteinError

        if isinstance(protein_tensor, ESMProteinError):
            raise RuntimeError(
                f"ESMC encode error {protein_tensor.error_code}: {protein_tensor.error_msg}"
            )

        output = client.logits(
            protein_tensor,
            LogitsConfig(sequence=False, return_embeddings=True),
        )
        emb = getattr(output, "embeddings", None)
        shape = None
        if emb is not None:
            try:
                shape = tuple(emb.shape)
            except Exception:  # noqa: BLE001
                shape = None
        shape_txt = f", embedding shape={shape}" if shape else ""
        return (
            f"ESMC ({self.settings.esmc_model})\n"
            f"Length: {len(sequence)} aa{shape_txt}"
        )


def _short_err(exc: BaseException) -> str:
    msg = str(exc).strip() or type(exc).__name__
    # Avoid dumping huge SDK payloads into Telegram.
    if len(msg) > 400:
        msg = msg[:397] + "..."
    return msg
