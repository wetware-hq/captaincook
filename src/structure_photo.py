"""Headless mmCIF → PNG for inline Telegram attaches on `/esm` / `/boltz` (and optional design best-CIF).

No separate `/photo` command. Research-use imagery only. Seed-owned slice:
PyMOL primary, Mol* fallback. Does NOT implement RDKit design grids
(see result_photo / biomodels).

Host deps (see docs/RENDER-seed.md):
  - Preferred: `sudo apt-get install -y python3-pymol pymol`
  - Headless invoke: `pymol -cq script.pml` (or `python3 -m pymol -cq`)
  - Optional Mol* CLI: not packaged by default; see _render_molstar.
  - Last-resort: smoothed Cα tube via Bio.PDB/biotite + matplotlib (always available in bot venv; caption must note simplified).

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
from dataclasses import dataclass
from typing import Literal, Optional

Engine = Literal["pymol", "molstar", "backbone_ca"]


@dataclass(frozen=True)
class StructureRender:
    """PNG path plus which renderer produced it (for honest captions)."""

    path: Path
    engine: Engine
    simplified: bool  # True when only a Cα tube/trace was drawn

    def __str__(self) -> str:  # pragma: no cover
        return str(self.path)

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
    try:
        flat = mask_c.get_flattened_data()  # Pillow >=10.1
        arr = list(flat)
    except AttributeError:
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




def _pml_script_binder_complex(
    cif_path: Path,
    out_path: Path,
    width: int,
    height: int,
    *,
    binder_chain: str = "B",
) -> str:
    """PyMOL recipe for target+binder complexes.

    Target (all polymer not binder_chain) keeps PyMOL default cartoon colour.
    Binder chain is coloured distinctly (tv_orange) so the designed binder reads
    clearly against the target. Research-use only.
    """
    cif = str(cif_path.resolve()).replace("\\", "/")
    out = str(out_path.resolve()).replace("\\", "/")
    bc = "".join(ch for ch in binder_chain if ch.isalnum()) or "B"
    return f"""# binder complex — target default colour, binder differentiated
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
# Target: leave PyMOL default cartoon colour on non-binder chains
# Binder: distinct accent so it is visually separable from the target
color tv_orange, chain {bc} and polymer and struct
orient struct
origin struct
center struct
zoom struct, buffer=8, complete=1
ray {width},{height}
png {out}, dpi=150
quit
"""


def _render_pymol_binder_complex(
    cif_path: Path,
    out_path: Path,
    *,
    width: int = _DEFAULT_W,
    height: int = _DEFAULT_H,
    binder_chain: str = "B",
) -> Path:
    """Render a target+binder complex with differentiated binder colour."""
    cif_path = Path(cif_path).resolve()
    out_path = Path(out_path).resolve()
    if not cif_path.is_file():
        raise FileNotFoundError(f"mmCIF not found: {cif_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pymol_cmd = _resolve_pymol_bin()
    if pymol_cmd[0].endswith("python") or Path(pymol_cmd[0]).name.startswith("python"):
        try:
            subprocess.run(
                [pymol_cmd[0], "-c", "import pymol"],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pymol_cmd = ["python3", "-m", "pymol"]

    with tempfile.TemporaryDirectory(prefix="binder_complex_photo_") as tmp:
        pml_path = Path(tmp) / "render.pml"
        pml_path.write_text(
            _pml_script_binder_complex(
                cif_path, out_path, width, height, binder_chain=binder_chain
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
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
                f"PyMOL binder-complex render failed (rc={proc.returncode}). "
                f"Detail:\n{detail}"
            )
    try:
        _crop_white_margins(out_path)
    except Exception as crop_exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("PNG margin crop skipped: %s", crop_exc)
    return out_path


def render_binder_complex(
    cif_path: str | Path,
    out_path: str | Path | None = None,
    *,
    binder_chain: str = "B",
) -> StructureRender:
    """Render a binder complex CIF with target default colour + binder accent.

    Prefers PyMOL binder recipe; falls back to ordinary render_structure (no
    colour split) if that fails — never invents coordinates.
    """
    cif_path = Path(cif_path)
    if out_path is None:
        out_path = cif_path.with_suffix(".png")
    else:
        out_path = Path(out_path)
    try:
        path = _render_pymol_binder_complex(
            cif_path, out_path, binder_chain=binder_chain
        )
        return StructureRender(path, "pymol", False)
    except Exception:
        # Fall back to standard stack (may lose colour split)
        return render_structure(cif_path, out_path=out_path)


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



def _ca_coords_and_sse(cif_path: Path) -> tuple["object", "object"]:
    """Return (N,3) Cα coords and per-Cα SSE labels ('a'/'b'/'c'/None).

    Prefers biotite (SSE annotation from N/CA/C). Falls back to Bio.PDB Cα
    only with coil labels. Never invents coordinates.
    """
    import numpy as np

    try:
        import biotite.structure as struc
        import biotite.structure.io.pdbx as pdbx

        try:
            ff = pdbx.CIFFile.read(str(cif_path))
        except Exception:
            ff = pdbx.PDBxFile.read(str(cif_path))
        arr = pdbx.get_structure(ff, model=1)
        ca_mask = arr.atom_name == "CA"
        if int(ca_mask.sum()) < 3:
            raise RuntimeError("fewer than 3 Cα")
        coords = np.asarray(arr.coord[ca_mask], dtype=float)
        try:
            sse_all = struc.annotate_sse(arr)
            # annotate_sse returns one label per residue; align to CA atoms
            if len(sse_all) == arr.array_length():
                sse = [str(x) for x in sse_all[ca_mask]]
            elif len(sse_all) == int(ca_mask.sum()):
                sse = [str(x) for x in sse_all]
            else:
                # residue-level: map via residue starts
                ca_atoms = arr[ca_mask]
                sse = ["c"] * len(coords)
                # best-effort: annotate on full array length mismatch → coil
                if hasattr(ca_atoms, "res_id"):
                    pass
                sse = [str(x) if str(x) in ("a", "b", "c") else "c" for x in sse]
        except Exception:
            sse = ["c"] * len(coords)
        sse = [s if s in ("a", "b", "c") else "c" for s in sse]
        return coords, sse
    except Exception:
        from Bio.PDB import MMCIFParser

        parser = MMCIFParser(QUIET=True)
        structure = parser.get_structure("struct", str(cif_path))
        coords_list: list[list[float]] = []
        for atom in structure.get_atoms():
            if atom.get_id() == "CA":
                coords_list.append(list(atom.get_coord()))
        if len(coords_list) < 3:
            raise RuntimeError(
                f"Backbone PNG fallback found fewer than 3 Cα atoms in {cif_path}"
            )
        coords = np.asarray(coords_list, dtype=float)
        sse = ["c"] * len(coords)
        return coords, sse


def _smooth_polyline(xy: "object", *, n_dense: int | None = None) -> "object":
    """Cubic spline through 2D points; returns denser polyline (no new endpoints invented beyond fit)."""
    import numpy as np

    xy = np.asarray(xy, dtype=float)
    n = len(xy)
    if n < 4:
        return xy
    try:
        from scipy.interpolate import splprep, splev
    except ImportError:
        # Catmull-Rom-ish local smoothing without scipy
        out = [xy[0]]
        for i in range(n - 1):
            p0 = xy[max(i - 1, 0)]
            p1 = xy[i]
            p2 = xy[i + 1]
            p3 = xy[min(i + 2, n - 1)]
            for t in (0.25, 0.5, 0.75):
                t2, t3 = t * t, t * t * t
                pt = 0.5 * (
                    (2 * p1)
                    + (-p0 + p2) * t
                    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
                )
                out.append(pt)
            out.append(p2)
        return np.asarray(out, dtype=float)

    # chord-length parameterization; stronger s removes CA zigzag while
    # staying a fit to the real projected coordinates (no invented atoms).
    k = 3
    s = float(n) * 4.0
    tck, _u = splprep([xy[:, 0], xy[:, 1]], s=s, k=k)
    if n_dense is None:
        n_dense = max(n * 12, 400)
    u_fine = np.linspace(0.0, 1.0, n_dense)
    x_f, y_f = splev(u_fine, tck)
    return np.column_stack([x_f, y_f])


def _render_backbone(
    cif_path: Path,
    out_path: Path,
    *,
    width: int = _DEFAULT_W,
    height: int = _DEFAULT_H,
) -> Path:
    """Last-resort smoothed Cα tube PNG via Bio.PDB/biotite + matplotlib.

    Uses real Cα coordinates only (optional SSE from biotite for tube width).
    Not a ray-traced cartoon — callers must note simplification in the caption.
    """
    cif_path = Path(cif_path).resolve()
    out_path = Path(out_path).resolve()
    if not cif_path.is_file():
        raise FileNotFoundError(f"mmCIF not found: {cif_path}")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Backbone PNG fallback needs matplotlib and numpy "
            f"in the bot environment. Detail: {exc}"
        ) from exc

    arr, sse = _ca_coords_and_sse(cif_path)
    arr = np.asarray(arr, dtype=float)
    if len(arr) < 3:
        raise RuntimeError(
            f"Backbone PNG fallback found fewer than 3 Cα atoms in {cif_path}"
        )

    # PCA → 2D (stable view); keep 3rd PC as depth for shading
    centered = arr - arr.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    xy3 = centered @ vt[:3].T
    xy = xy3[:, :2]
    depth = xy3[:, 2]
    depth_n = (depth - depth.min()) / max(float(np.ptp(depth)), 1e-6)

    # Dense smooth tube through Cα projection (still derived from real coords)
    dense = _smooth_polyline(xy)
    # Interpolate SSE / depth onto dense polyline by nearest original index
    n = len(xy)
    # Map dense points to nearest CA index along arc length of original
    # Approximate: proportional index
    dense_idx = np.linspace(0, n - 1, len(dense))
    sse_w = {"a": 9.0, "b": 7.0, "c": 3.8}  # helix / sheet / coil
    widths_ca = np.array([sse_w.get(s, 3.2) for s in sse], dtype=float)
    depths_ca = depth_n
    widths = np.interp(dense_idx, np.arange(n), widths_ca)
    depths_d = np.interp(dense_idx, np.arange(n), depths_ca)

    dpi = 100
    fig_w, fig_h = width / dpi, height / dpi
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    pts = dense.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    # Colour by chain progress; darken distant (high depth) segments
    t = np.linspace(0.0, 1.0, len(segs))
    cmap = plt.cm.viridis
    colors = cmap(t)
    # depth shading: multiply RGB by (0.55 + 0.45*(1-depth))
    shade = 0.55 + 0.45 * (1.0 - 0.5 * (depths_d[:-1] + depths_d[1:]))
    colors = colors.copy()
    colors[:, :3] *= shade[:, None]
    lw = 0.5 * (widths[:-1] + widths[1:])
    lc = LineCollection(segs, colors=colors, linewidths=lw, capstyle="round", joinstyle="round")
    ax.add_collection(lc)

    # Soft under-glow tube for ribbon feel
    lc2 = LineCollection(
        segs,
        colors=[(0.75, 0.85, 0.95, 0.25)] * len(segs),
        linewidths=lw * 1.8,
        capstyle="round",
        joinstyle="round",
        zorder=0,
    )
    ax.add_collection(lc2)

    ax.scatter(xy[0, 0], xy[0, 1], s=42, c="#2ca02c", zorder=3, edgecolors="white", linewidths=0.6)
    ax.scatter(xy[-1, 0], xy[-1, 1], s=42, c="#d62728", zorder=3, edgecolors="white", linewidths=0.6)
    ax.axis("off")
    pad = 0.08 * max(float(np.ptp(xy[:, 0])), float(np.ptp(xy[:, 1])), 1.0)
    ax.set_xlim(xy[:, 0].min() - pad, xy[:, 0].max() + pad)
    ax.set_ylim(xy[:, 1].min() - pad, xy[:, 1].max() + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.autoscale_view()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor="white", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    if not out_path.is_file() or out_path.stat().st_size < 64:
        raise RuntimeError(f"Backbone PNG fallback wrote an empty file: {out_path}")
    try:
        _crop_white_margins(out_path)
    except Exception as crop_exc:  # noqa: BLE001
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


def render_structure(
    cif_path: str | Path,
    engine: Engine | None = None,
    out_path: str | Path | None = None,
) -> StructureRender:
    """Render an mmCIF structure to a PNG and report which engine drew it.

    Auto order: PyMOL → Mol* → smoothed Cα tube (simplified=True).
    """
    cif_path = Path(cif_path)
    if out_path is None:
        out_path = cif_path.with_suffix(".png")
    else:
        out_path = Path(out_path)

    if engine is not None and engine not in ("pymol", "molstar", "backbone_ca"):
        raise ValueError(
            f"engine must be 'pymol', 'molstar', 'backbone_ca', or None; got {engine!r}"
        )

    if engine == "pymol":
        return StructureRender(_render_pymol(cif_path, out_path), "pymol", False)
    if engine == "molstar":
        return StructureRender(_render_molstar(cif_path, out_path), "molstar", False)
    if engine == "backbone_ca":
        return StructureRender(_render_backbone(cif_path, out_path), "backbone_ca", True)

    pymol_err: Optional[Exception] = None
    mol_err: Optional[Exception] = None
    try:
        return StructureRender(_render_pymol(cif_path, out_path), "pymol", False)
    except Exception as exc:  # noqa: BLE001 — intentional fallback gate
        pymol_err = exc
    try:
        return StructureRender(_render_molstar(cif_path, out_path), "molstar", False)
    except Exception as exc:  # noqa: BLE001
        mol_err = exc
    try:
        return StructureRender(_render_backbone(cif_path, out_path), "backbone_ca", True)
    except Exception as bb_err:
        raise RuntimeError(
            f"Protein PNG render failed. PyMOL: {pymol_err}; "
            f"Mol* fallback: {mol_err}; Backbone fallback: {bb_err}"
        ) from bb_err


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
        ``"pymol"`` | ``"molstar"`` | ``"backbone_ca"`` | ``None``
        (auto: try PyMOL, then Mol*, then smoothed Cα tube).
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
        All engines failed (or forced engine failed).
    ValueError
        Unknown engine string.

    Notes
    -----
    Prefer :func:`render_structure` when the caller needs to know whether the
    PNG is a simplified Cα tube (so captions stay honest).
    """
    return render_structure(cif_path, engine=engine, out_path=out_path).path


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.structure_photo",
        description="Render mmCIF → PNG (PyMOL → Mol* → Cα tube). Research-use only.",
    )
    parser.add_argument("cif", type=Path, help="Input mmCIF path")
    parser.add_argument("-o", "--out", type=Path, default=None, help="Output PNG path")
    parser.add_argument(
        "--engine",
        choices=("pymol", "molstar", "backbone_ca"),
        default=None,
        help="Force renderer (default: auto pymol→molstar→backbone_ca)",
    )
    args = parser.parse_args(argv)
    path = render_cif_to_png(args.cif, engine=args.engine, out_path=args.out)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
