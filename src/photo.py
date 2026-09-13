"""Thin helpers for attaching result PNGs to Telegram slash replies.

No /photo command. Research-use imagery only.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from telegram import Message

from .result_photo import render_design_png

logger = logging.getLogger(__name__)

# User-facing one-liner when structure/design PNG render fails (never block text/CIF).
IMAGE_RENDER_FAILED = "The image could not be drawn. The written result is still available."


def render_structure_png(
    cif_path: str | Path,
    *,
    engine: str | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Wrap seed ``render_cif_to_png``. Raises on import or render failure."""
    from src.structure_photo import render_cif_to_png

    kwargs: dict[str, Any] = {}
    if engine is not None:
        kwargs["engine"] = engine
    if out_path is not None:
        kwargs["out_path"] = out_path
    return render_cif_to_png(cif_path, **kwargs)


def _candidates_as_dicts(candidates: Sequence[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in candidates:
        if isinstance(c, Mapping):
            out.append(dict(c))
            continue
        out.append(
            {
                "id": getattr(c, "id", None),
                "smiles": getattr(c, "smiles", None),
                "binding_confidence": getattr(c, "binding_confidence", None),
                "optimization_score": getattr(c, "optimization_score", None),
                "adme_solubility": getattr(c, "adme_solubility", None),
                "structure_confidence": getattr(c, "structure_confidence", None),
            }
        )
    return out


async def send_structure_photo(
    message: Message,
    cif_path: Path,
    *,
    caption: str,
    engine: str | None = None,
    keep_path: Path | None = None,
) -> bool:
    """Render CIF → PNG and ``reply_photo``. Returns True on success.

    If keep_path is set, copy the PNG there before the temp file is removed.
    """
    png: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="struct_photo_", suffix=".png", dir="/tmp")
        import os

        os.close(fd)
        png = Path(tmp_name)
        png = render_structure_png(cif_path, engine=engine, out_path=png)
        if keep_path is not None:
            keep_path = Path(keep_path)
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, keep_path)
        with png.open("rb") as fh:
            await message.reply_photo(photo=fh, caption=(caption or "")[:1024])
        return True
    except Exception as exc:  # noqa: BLE001 — caller sends one caption text
        logger.warning("structure PNG render failed: %s", exc)
        return False
    finally:
        if png is not None:
            try:
                png.unlink(missing_ok=True)
            except OSError:
                pass


async def send_design_photo(
    message: Message,
    candidates: Sequence[Any],
    meta: Mapping[str, Any],
    *,
    caption: str,
    keep_path: Path | None = None,
) -> bool:
    """Render RDKit design grid and ``reply_photo``. Returns True on success."""
    png: Path | None = None
    try:
        png = render_design_png(_candidates_as_dicts(candidates), meta)
        if keep_path is not None:
            keep_path = Path(keep_path)
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, keep_path)
        with png.open("rb") as fh:
            await message.reply_photo(photo=fh, caption=(caption or "")[:1024])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("design PNG render failed: %s", exc)
        return False
    finally:
        if png is not None:
            try:
                png.unlink(missing_ok=True)
            except OSError:
                pass
