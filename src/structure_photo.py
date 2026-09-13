"""Headless mmCIF → PNG for inline Telegram attaches on `/esm` / `/boltz` (and optional design best-CIF).

No separate `/photo` command. Research-use imagery only. Seed-owned slice:
PyMOL primary, Mol* fallback. Does NOT implement RDKit design grids
(see result_photo / biomodels).

Host deps (see docs/RENDER-seed.md):
  - Preferred: `sudo apt-get install -y python3-pymol pymol`
  - Headless invoke: `pymol -cq script.pml` (or `python3 -m pymol -cq`)
  - Optional Mol* CLI: not packaged by default; see _render_molstar.

Biomodels call site:
  from src.structure_photo import render_cif_to_png
  png = render_cif_to_png(cif_path, engine=None)  # auto: pymol then molstar
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal, Optional

Engine = Literal["pymol", "molstar"]

# Default PNG size (Telegram-friendly).
_DEFAULT_W = 1024
_DEFAULT_H = 768

# Water / solvent residue names to exclude from ligand sticks.
_WATER_RESN = "HOH+WAT+SOL+DOD+TIP+TIP3+TIP4+SPC"


def _crop_white_margins(png_path: Path, *, pad_frac: float = 0.08, threshold: int = 250) -> None:
    """Trim near-white margins and re-center subject by content mass on the canvas.

    Uses the bounding box to size the subject, then places it so the centroid of
    non-white pixels sits at the canvas center (avoids diagonal helices looking
    top-left heavy when only the bbox is centered).
    """
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Pillow required to center PNG margins. "
            "apt install python3-pil or pip install Pillow"
        ) from exc

    im = Image.open(png_path).convert("RGB")
    canvas_w, canvas_h = im.size
    r, g, b = im.split()
    mask = ImageChops.lighter(
        ImageChops.lighter(
            r.point(lambda x: 255 if x < threshold else 0),
            g.point(lambda x: 255 if x < threshold else 0),
        ),
        b.point(lambda x: 255 if x < threshold else 0),
    )
    bbox = mask.getbbox()
    if not bbox:
        return
    cropped = im.crop(bbox)
    cw, ch = cropped.size
    margin = max(8, int(min(canvas_w, canvas_h) * pad_frac))
    max_w = max(1, canvas_w - 2 * margin)
    max_h = max(1, canvas_h - 2 * margin)
    scale = min(max_w / cw, max_h / ch)
    if abs(scale - 1.0) > 0.001:
        new_size = (max(1, int(cw * scale)), max(1, int(ch * scale)))
        cropped = cropped.resize(new_size, Image.Resampling.LANCZOS)
        cw, ch = cropped.size
        mask_c = mask.crop(bbox).resize(new_size, Image.Resampling.NEAREST)
    else:
        mask_c = mask.crop(bbox)

    # Centroid of non-white pixels in the scaled crop
    arr = list(mask_c.getdata())
    w = cw
    xs = []
    ys = []
    for i, v in enumerate(arr):
        if v:
            xs.append(i % w)
            ys.append(i // w)
    if not xs:
        cx, cy = cw / 2.0, ch / 2.0
    else:
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

    # Place so content centroid lands on canvas center; clamp to keep subject on-canvas
    x = int(round(canvas_w / 2.0 - cx))
    y = int(round(canvas_h / 2.0 - cy))
    x = max(0, min(x, canvas_w - cw))
    y = max(0, min(y, canvas_h - ch))

    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    canvas.paste(cropped, (x, y))
    canvas.save(png_path, "PNG")


def _resolve_pymol_bin() -> list[str]:
    """Return argv prefix to run headless PyMOL.

    Debian's /usr/bin/pymol wrapper calls whatever `python3` is on PATH.
    The bot venv shadows that and cannot import apt `python3-pymol`, so
    prefer a system interpreter that can `import pymol`.
    """
    for py in ("/usr/bin/python3", "/usr/bin/python3.13", "/usr/bin/python3.12", "/usr/bin/python3.11"):
        if Path(py).is_file():
            try:
                subprocess.run(
                    [py, "-c", "import pymol"],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                return [py, "-m", "pymol"]
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
    for candidate in ("pymol",):
        path = shutil.which(candidate)
        if path:
            return [path]
    return [sys.executable if Path(sys.executable).name.startswith("python") else "python3", "-m", "pymol"]


def _pml_script(cif_path: Path, out_path: Path, width: int, height: int) -> str:
    """Reproducible PyMOL recipe: cartoon polymer + sticks for organic ligands."""
    cif = str(cif_path.resolve()).replace("\\", "/")
    out = str(out_path.resolve()).replace("\\", "/")
    return f"""# structure_photo seed recipe — research-use only
reinitialize
load {cif}, struct
remove resn {_WATER_RESN}
hide everything, struct
show cartoon, polymer and struct
show sticks, (organic or hetatm) and struct
set cartoon_fancy_helices, 1
set stick_radius, 0.18
set ray_opaque_background, 1
set orthoscopic, on
bg_color white
orient struct
origin struct
center struct
zoom struct, buffer=8, complete=1
ray {width},{height}
png {out}, dpi=150
quit
"""


def _render_pymol(
    cif_path: Path,
    out_path: Path,
    *,
    width: int = _DEFAULT_W,
    height: int = _DEFAULT_H,
) -> Path:
    """Render via subprocess + .pml (avoids fragile import pymol inside bot venv)."""
    cif_path = Path(cif_path).resolve()
    out_path = Path(out_path).resolve()
    if not cif_path.is_file():
        raise FileNotFoundError(f"mmCIF not found: {cif_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pymol_cmd = _resolve_pymol_bin()
    # Prefer system python3 -m pymol when bot venv python lacks pymol
    if pymol_cmd[0].endswith("python") or Path(pymol_cmd[0]).name.startswith("python"):
        # If venv python cannot import pymol, fall back to system python3
        try:
            subprocess.run(
                [pymol_cmd[0], "-c", "import pymol"],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pymol_cmd = ["python3", "-m", "pymol"]

    with tempfile.TemporaryDirectory(prefix="structure_photo_") as tmp:
        pml_path = Path(tmp) / "render.pml"
        pml_path.write_text(_pml_script(cif_path, out_path, width, height), encoding="utf-8")
        env = os.environ.copy()
        # Headless / offscreen friendly
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env.setdefault("PYMOL_PATH", env.get("PYMOL_PATH", ""))
        cmd = [*pymol_cmd, "-cq", str(pml_path)]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        if proc.returncode != 0 or not out_path.is_file() or out_path.stat().st_size < 64:
            detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
            raise RuntimeError(
                f"PyMOL render failed (rc={proc.returncode}, cmd={' '.join(cmd)}). "
                f"Install: apt install python3-pymol pymol. Detail:\n{detail}"
            )
    # Center subject by trimming asymmetric white margins
    try:
        _crop_white_margins(out_path)
    except Exception as crop_exc:  # noqa: BLE001 — non-fatal; keep uncropped PNG
        import logging
        logging.getLogger(__name__).warning("PNG margin crop skipped: %s", crop_exc)
    return out_path


def _find_molstar_cli() -> Optional[list[str]]:
    """Locate a headless Mol* image exporter if the host has one."""
    for name in ("molstar-cli", "molstar", "mol*"):
        path = shutil.which(name)
        if path:
            return [path]
    # npx local / global packages sometimes used experimentally
    npx = shutil.which("npx")
    if npx:
        # Probe without network if possible — only accept if already installed
        for pkg in ("molstar",):
            # Check global npm bin
            try:
                r = subprocess.run(
                    [npx, "--no-install", pkg, "--help"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r.returncode == 0:
                    return [npx, "--no-install", pkg]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
    return None


def _render_molstar(cif_path: Path, out_path: Path) -> Path:
    """Attempt headless Mol* PNG export.

    Mol* is primarily a browser viewer; there is no standard Debian/apt CLI for
    offline image export. If no CLI is found, raise a clear error so callers
    can surface a Telegram-friendly message after the single fallback attempt.
    """
    cif_path = Path(cif_path).resolve()
    out_path = Path(out_path).resolve()
    if not cif_path.is_file():
        raise FileNotFoundError(f"mmCIF not found: {cif_path}")

    cli = _find_molstar_cli()
    if cli is None:
        raise RuntimeError(
            "Mol* headless CLI not available on this host. "
            "Install PyMOL instead (`apt install python3-pymol pymol`) or provide a "
            "Mol* image-export binary on PATH (molstar / molstar-cli). "
            "No standard apt package exists for Mol* offline PNG export."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Best-effort generic invocation; real CLIs vary — document failures clearly.
    attempts = [
        [*cli, "image", "--input", str(cif_path), "--output", str(out_path)],
        [*cli, "export", str(cif_path), str(out_path)],
        [*cli, str(cif_path), "-o", str(out_path)],
    ]
    errors: list[str] = []
    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 64:
                return out_path
            errors.append(f"{' '.join(cmd)} → rc={proc.returncode} {(proc.stderr or '')[:400]}")
        except Exception as exc:  # noqa: BLE001 — collect for clear multi-attempt error
            errors.append(f"{' '.join(cmd)} → {exc}")
    raise RuntimeError(
        "Mol* fallback failed after CLI attempts:\n" + "\n".join(errors)
    )


def render_cif_to_png(
    cif_path: str | Path,
    engine: Engine | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Render an mmCIF structure to a PNG.

    Parameters
    ----------
    cif_path:
        Path to mmCIF (e.g. Boltz predicted.cif).
    engine:
        ``\"pymol\"`` | ``\"molstar\"`` | ``None`` (auto: try PyMOL, then one Mol* attempt).
    out_path:
        Destination PNG. Default: same stem as CIF with ``.png`` beside the CIF.

    Returns
    -------
    Path
        Absolute path to the written PNG.

    Raises
    ------
    FileNotFoundError
        CIF missing.
    RuntimeError
        Both engines failed (or forced engine failed).
    ValueError
        Unknown engine string.
    """
    cif_path = Path(cif_path)
    if out_path is None:
        out_path = cif_path.with_suffix(".png")
    else:
        out_path = Path(out_path)

    if engine is not None and engine not in ("pymol", "molstar"):
        raise ValueError(f"engine must be 'pymol', 'molstar', or None; got {engine!r}")

    if engine == "pymol":
        return _render_pymol(cif_path, out_path)
    if engine == "molstar":
        return _render_molstar(cif_path, out_path)

    # Auto: PyMOL primary, one Mol* fallback
    pymol_err: Optional[Exception] = None
    try:
        return _render_pymol(cif_path, out_path)
    except Exception as exc:  # noqa: BLE001 — intentional single-fallback gate
        pymol_err = exc
    try:
        return _render_molstar(cif_path, out_path)
    except Exception as mol_err:
        raise RuntimeError(
            f"Protein PNG render failed. PyMOL: {pymol_err}; Mol* fallback: {mol_err}"
        ) from mol_err


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.structure_photo",
        description="Render mmCIF → PNG (PyMOL primary, Mol* fallback). Research-use only.",
    )
    parser.add_argument("cif", type=Path, help="Input mmCIF path")
    parser.add_argument("-o", "--out", type=Path, default=None, help="Output PNG path")
    parser.add_argument(
        "--engine",
        choices=("pymol", "molstar"),
        default=None,
        help="Force renderer (default: auto pymol→molstar)",
    )
    args = parser.parse_args(argv)
    path = render_cif_to_png(args.cif, engine=args.engine, out_path=args.out)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
