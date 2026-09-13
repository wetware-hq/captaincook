"""RDKit PNG grid for Boltz small-molecule design results.

Plain white, molecules only. Scores sort the grid; they are never drawn.
Research-use imagery only. Owned by biomodels (not seed structure_photo).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image
from rdkit import Chem
from rdkit.Chem import Draw

_MOL_SIZE = (280, 280)
_MOLS_PER_ROW = 5
_BG = (255, 255, 255)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _score_tuple(cand: Any) -> tuple[float, float]:
    """Sort key: binding_confidence desc, then optimization_score desc.

    Missing scores sort last. Never used for drawing.
    """

    def as_float(val: Any) -> float:
        if val is None:
            return float("-inf")
        try:
            return float(val)
        except (TypeError, ValueError):
            return float("-inf")

    return (as_float(_get(cand, "binding_confidence")), as_float(_get(cand, "optimization_score")))


def rank_candidates(candidates: Sequence[Any]) -> list[Any]:
    """English reading order: best first (L→R, T→B once gridded)."""
    return sorted(candidates, key=_score_tuple, reverse=True)


def render_design_png(
    candidates: Sequence[Any],
    meta: Mapping[str, Any] | None = None,  # noqa: ARG001 — kept for caller API
    *,
    out_path: str | Path | None = None,
) -> Path:
    """Render a no-text RDKit grid of design candidates on a white background.

    Candidates are sorted by binding_confidence, then optimization_score
    (both descending). Scores and metadata are not drawn.
    """
    del meta
    ranked = rank_candidates(list(candidates))
    mols: list[Chem.Mol] = []
    for cand in ranked:
        smiles = (_get(cand, "smiles") or "").strip()
        if not smiles:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        mols.append(mol)

    if out_path is None:
        fd, name = tempfile.mkstemp(prefix="boltz_design_", suffix=".png", dir="/tmp")
        import os

        os.close(fd)
        out = Path(name)
    else:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

    if not mols:
        Image.new("RGB", (800, 200), _BG).save(out, format="PNG")
        return out.resolve()

    ncols = min(_MOLS_PER_ROW, len(mols))
    grid_img = Draw.MolsToGridImage(
        mols,
        molsPerRow=ncols,
        subImgSize=_MOL_SIZE,
        legends=None,
        returnPNG=False,
    )
    if not isinstance(grid_img, Image.Image):
        from io import BytesIO

        grid_img = Image.open(BytesIO(grid_img)).convert("RGB")
    else:
        grid_img = grid_img.convert("RGB")

    # Force a clean white canvas in case RDKit leaves off-white.
    canvas = Image.new("RGB", grid_img.size, _BG)
    canvas.paste(grid_img, (0, 0))
    canvas.save(out, format="PNG")
    return out.resolve()


if __name__ == "__main__":
    import json
    import sys

    dummy = Path("/workspace/boltz-smoke/design-dummy-n10.json")
    data = json.loads(dummy.read_text(encoding="utf-8"))
    out = Path("/workspace/telegram-biomodel-bot/docs/photo-design-smoke.png")
    path = render_design_png(
        data["top"],
        {
            "run_id": data.get("run_id"),
            "n": data.get("n_candidates") or len(data["top"]),
            "estimated_cost_usd": data.get("estimated_cost_usd", 0.25),
        },
        out_path=out,
    )
    print(path, path.stat().st_size)
    sys.exit(0)
