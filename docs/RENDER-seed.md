# Protein structure PNG rendering (seed)

Research-use imagery only. Implements `src.structure_photo.render_cif_to_png` for inline PNGs on `/esm` and `/boltz` (and optional design best-CIF). No separate `/photo` command.

## Host install

Preferred (Debian/Ubuntu — system Python can `import pymol`):

```bash
sudo apt-get install -y python3-pymol pymol python3-pil
```

Verify:

```bash
pymol -cq -d "print('ok')"
# or
python3 -m pymol -cq -d "print('ok')"
```

The bot venv does **not** need `pymol` on pip. `structure_photo` invokes headless PyMOL via **subprocess + `.pml` script** (`pymol -cq` / `python3 -m pymol -cq`), so isolation from `.venv` is fine.

Conda only if apt is unavailable:

```bash
conda install -c conda-forge pymol-open-source
```

## Mol* fallback

There is **no standard apt Mol* headless image CLI**. If PyMOL fails (or `--engine molstar`), `structure_photo` looks for `molstar` / `molstar-cli` / `npx --no-install molstar` on PATH. If none exist, it raises a clear error after that single fallback attempt.

## Recipe (PyMOL)

1. `load` mmCIF; `remove` solvent residues  
2. cartoon polymer + sticks for organic/hetatm  
3. white bg → `orient` / `origin` / `center` / `zoom` (buffer) → `ray` → `png`  
4. Pillow post-pass: trim near-white margins and re-center on the canvas (`python3-pil`)

## API for biomodels

```python
from src.structure_photo import render_cif_to_png

png_path = render_cif_to_png(cif_path)                    # auto engine
png_path = render_cif_to_png(cif_path, engine="pymol")    # force
png_path = render_cif_to_png(cif_path, engine="molstar", out_path="/tmp/x.png")
```

CLI:

```bash
cd /workspace/telegram-biomodel-bot
python -m src.structure_photo /path/to/model.cif -o out.png --engine pymol
```

## Smoke outputs

PNGs land under `boltz-experiments/photo-smoke/` during seed smoke tests.
