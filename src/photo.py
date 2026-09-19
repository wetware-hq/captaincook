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

# Appended to 3C caption when only the smoothed Cα tube was available (not PyMOL/Mol*).
SIMPLIFIED_CA_CAPTION_NOTE = (
    "Image is a simplified Cα backbone trace (not a cartoon render). "
    "/download CIF is the source of truth for binder design."
)

# Minimum PNG size we will hand to Telegram (avoids empty / corrupt media).
_MIN_PNG_BYTES = 64


def render_structure_png(
    cif_path: str | Path,
    *,
    engine: str | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Wrap seed ``render_cif_to_png``. Raises on import or render failure."""
    return render_structure_result(cif_path, engine=engine, out_path=out_path).path


def render_structure_result(
    cif_path: str | Path,
    *,
    engine: str | None = None,
    out_path: str | Path | None = None,
):
    """Wrap seed ``render_structure`` (path + engine + simplified flag)."""
    from src.structure_photo import render_structure

    kwargs: dict[str, Any] = {}
    if engine is not None:
        kwargs["engine"] = engine
    if out_path is not None:
        kwargs["out_path"] = out_path
    return render_structure(cif_path, **kwargs)


def _caption_with_render_note(caption: str, *, simplified: bool) -> str:
    """Keep 3C caption honest when PNG is only a Cα tube."""
    base = (caption or "").strip()
    if not simplified:
        return base
    note = SIMPLIFIED_CA_CAPTION_NOTE
    if note.lower() in base.lower():
        return base
    if not base:
        return note
    combo = f"{base}\n\n{note}"
    if len(combo) <= 1024:
        return combo
    # Prefer keeping the honesty note; trim the clinical blurb first.
    budget = 1024 - len(note) - 2
    if budget < 32:
        return note[:1024]
    return base[: budget - 1].rstrip() + "…\n\n" + note


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


def _usable_png(path: Path | None) -> Path | None:
    """Return path only if it is a non-empty PNG file; else None."""
    if path is None:
        return None
    try:
        p = Path(path)
    except TypeError:
        return None
    if not p.is_file():
        return None
    try:
        if p.stat().st_size < _MIN_PNG_BYTES:
            return None
    except OSError:
        return None
    return p


async def send_structure_photo(
    message: Message,
    cif_path: Path,
    *,
    caption: str,
    engine: str | None = None,
    keep_path: Path | None = None,
) -> bool:
    """Render CIF → PNG and ``reply_photo``. Returns True on success.

    Never calls ``reply_photo`` with a missing/empty image — returns False so
    the caller can send clear text instead. If keep_path is set, copy the PNG
    there before the temp file is removed.
    """
    png: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix="struct_photo_", suffix=".png", dir="/tmp")
        import os

        os.close(fd)
        png = Path(tmp_name)
        result = render_structure_result(cif_path, engine=engine, out_path=png)
        png = result.path
        usable = _usable_png(png)
        if usable is None:
            logger.warning("structure PNG missing or empty after render: %s", png)
            return False
        png = usable
        if keep_path is not None:
            keep_path = Path(keep_path)
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, keep_path)
        with png.open("rb") as fh:
            data = fh.read()
        if not data or len(data) < _MIN_PNG_BYTES:
            logger.warning("structure PNG bytes empty; refusing reply_photo")
            return False
        final_caption = _caption_with_render_note(caption, simplified=result.simplified)
        logger.info(
            "structure PNG engine=%s simplified=%s bytes=%d",
            result.engine,
            result.simplified,
            len(data),
        )
        await message.reply_photo(photo=data, caption=final_caption[:1024])
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
    """Render RDKit design grid and ``reply_photo``. Returns True on success.

    Never calls ``reply_photo`` with a missing/empty image.
    """
    png: Path | None = None
    try:
        png = render_design_png(_candidates_as_dicts(candidates), meta)
        usable = _usable_png(png)
        if usable is None:
            logger.warning("design PNG missing or empty after render: %s", png)
            return False
        png = usable
        if keep_path is not None:
            keep_path = Path(keep_path)
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, keep_path)
        with png.open("rb") as fh:
            data = fh.read()
        if not data or len(data) < _MIN_PNG_BYTES:
            logger.warning("design PNG bytes empty; refusing reply_photo")
            return False
        await message.reply_photo(photo=data, caption=(caption or "")[:1024])
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


# --- BindCraft binder complex PNG (N=1 single / N>1 ligand-style grid) ---

_BINDER_CELL = (360, 270)
_BINDER_COLS = 3
_BINDER_BG = (255, 255, 255)


def list_binder_cifs(artifact_paths: Sequence[str | Path] | None) -> list[Path]:
    """Ranked binder complex CIFs from artifact paths (existing files only). Never invent."""
    out: list[Path] = []
    for raw in artifact_paths or []:
        try:
            p = Path(raw)
        except TypeError:
            continue
        if p.is_file() and p.suffix.lower() in {".cif", ".mmcif"}:
            out.append(p.resolve())
    return out


def _resize_cell(im: "Image.Image", size: tuple[int, int] = _BINDER_CELL) -> "Image.Image":
    from PIL import Image as PILImage

    im = im.convert("RGB")
    # Letterbox onto white cell so aspect is preserved.
    im.thumbnail(size, PILImage.Resampling.LANCZOS)
    canvas = PILImage.new("RGB", size, _BINDER_BG)
    x = (size[0] - im.size[0]) // 2
    y = (size[1] - im.size[1]) // 2
    canvas.paste(im, (x, y))
    return canvas


def render_binder_png(
    cif_paths: Sequence[str | Path],
    *,
    out_path: str | Path | None = None,
    engine: str | None = None,
) -> tuple[Path, int]:
    """Render binder complex CIF(s) → PNG.

    N=1: single target+binder cartoon via structure_photo (pymol stack).
    N>1: ranked white grid of complex views (ligand-style; no text in pixels).

    Returns (png_path, n_cells_drawn). Raises if nothing usable is drawn.
    Never invents coordinates or binders.
    """
    from PIL import Image as PILImage

    paths = [Path(p) for p in cif_paths if p is not None and Path(p).is_file()]
    if not paths:
        raise ValueError("no binder CIF files to render")

    if out_path is None:
        fd, name = tempfile.mkstemp(prefix="binder_photo_", suffix=".png", dir="/tmp")
        import os

        os.close(fd)
        out = Path(name)
    else:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

    def _render_one(cif: Path, dest: Path):
        """Binder complex: target default colour, binder chain accent."""
        if engine in (None, "pymol"):
            from src.structure_photo import render_binder_complex

            return render_binder_complex(cif, out_path=dest)
        return render_structure_result(cif, engine=engine, out_path=dest)

    if len(paths) == 1:
        result = _render_one(paths[0], out)
        usable = _usable_png(result.path)
        if usable is None:
            raise RuntimeError("binder single-CIF render produced empty PNG")
        if usable.resolve() != out.resolve():
            shutil.copy2(usable, out)
        return out.resolve(), 1

    # Grid: render each complex, then composite (English reading order = artifact order).
    cell_images: list[Any] = []
    with tempfile.TemporaryDirectory(prefix="binder_grid_") as tmp:
        for i, cif in enumerate(paths):
            cell_path = Path(tmp) / f"cell_{i}.png"
            try:
                result = _render_one(cif, cell_path)
                usable = _usable_png(result.path)
                if usable is None:
                    logger.warning("binder grid cell %s empty; skipping", cif.name)
                    continue
                cell_images.append(_resize_cell(PILImage.open(usable)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("binder grid cell %s failed: %s", cif.name, exc)
                continue

        if not cell_images:
            raise RuntimeError("all binder CIF grid cells failed to render")

        if len(cell_images) == 1:
            cell_images[0].save(out, format="PNG")
            return out.resolve(), 1

        ncols = min(_BINDER_COLS, len(cell_images))
        nrows = (len(cell_images) + ncols - 1) // ncols
        cw, ch = _BINDER_CELL
        canvas = PILImage.new("RGB", (ncols * cw, nrows * ch), _BINDER_BG)
        for idx, cell in enumerate(cell_images):
            r, c = divmod(idx, ncols)
            canvas.paste(cell, (c * cw, r * ch))
        canvas.save(out, format="PNG")
        return out.resolve(), len(cell_images)


async def send_binder_photo(
    message: Message,
    cif_paths: Sequence[str | Path],
    *,
    caption_n1: str,
    caption_grid: str,
    keep_path: Path | None = None,
    engine: str | None = None,
) -> str | None:
    """Render binder complex(es) and ``reply_photo``.

    Returns the caption actually attached on success, or None on failure.
    Caption is chosen from cells drawn (1 → n1, else grid) — never "this image…"
    without a photo.
    """
    png: Path | None = None
    try:
        png, n_drawn = render_binder_png(cif_paths, engine=engine)
        usable = _usable_png(png)
        if usable is None:
            logger.warning("binder PNG missing or empty after render: %s", png)
            return None
        png = usable
        if keep_path is not None:
            keep_path = Path(keep_path)
            keep_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, keep_path)
        with png.open("rb") as fh:
            data = fh.read()
        if not data or len(data) < _MIN_PNG_BYTES:
            logger.warning("binder PNG bytes empty; refusing reply_photo")
            return None
        caption = (caption_n1 if n_drawn == 1 else caption_grid) or ""
        logger.info("binder PNG n_cells=%d bytes=%d", n_drawn, len(data))
        await message.reply_photo(photo=data, caption=caption[:1024])
        return caption
    except Exception as exc:  # noqa: BLE001
        logger.warning("binder PNG render failed: %s", exc)
        return None
    finally:
        if png is not None:
            try:
                png.unlink(missing_ok=True)
            except OSError:
                pass
