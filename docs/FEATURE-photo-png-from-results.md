# Feature: auto-image on existing slash results (no `/photo`)

**Status:** Locked 2026-09-12 (user clarification)  
**Supersedes:** separate `/photo` command (removed)

## Goal

> **User lock 2026-09-12:** `/design`→`/confirm` attaches **ligands-only** (RDKit grid). No protein/complex PNG on design. `/esm`/`/boltz` still attach protein PNGs.


Every successful slash-command result that returns protein and/or chemical output **includes a PNG in the same Telegram response**. No separate `/photo` command.

## Mapping

| Command | Result artifacts | Image(s) attached |
| --- | --- | --- |
| `/esm <seq>` | summary + CIF | Protein PNG (PyMOL primary / Mol* fallback) |
| `/boltz <seq>` | summary + CIF | Protein PNG |
| `/boltz <seq> <smiles>` | summary + CIF | Protein–ligand PNG (cartoon + ligand sticks) |
| `/design` → `/confirm` | ranked SMILES (+ CIF optional) | **RDKit 2D ligand grid only** (no protein/complex PNG for now) |

## Non-goals

- `/photo`, `/photo protein`, `/photo design` — **do not add**
- Interactive Mol* in chat
- Blocking the text/CIF reply if render fails — send text+CIF anyway; note “image render failed” once

## Ownership

| Slice | Owner |
| --- | --- |
| `render_cif_to_png(cif, engine=...)` PyMOL/Mol* | **seed** |
| `render_design_png(candidates, meta)` RDKit grid | **biomodels** |
| Wire images into `/esm`, `/boltz`, `/confirm`; HELP/README; no `/photo` handler | **biomodels** |
| Spec | **biostrategist** |

## Acceptance

1. `/boltz` success → photo + CIF (or clear render-fail note).  
2. `/esm` success → photo + CIF.  
3. `/confirm` design success → design-grid photo (+ CIF if available).  
4. No `/photo` in HELP or command list.  
5. Research-use caption on every image.

## Deps

- seed: PyMOL / Mol*  
- biomodels: pin `rdkit`, `Pillow` for design grid  

## Design grid view (locked plan 2026-09-12)

Plain white grid for `/design` → `/confirm` ligand PNG:

| Rule | Detail |
| --- | --- |
| Background | Plain white |
| Text on image | **None** — no legends, ranks, scores, headers, disclaimers in pixels |
| Sort | Descending by objective score: `binding_confidence` primary, then `optimization_score` |
| Layout | English reading order: left→right, top→bottom (best = top-left) |
| Scores | **Hidden** — used only to order molecules |
| Telegram caption / text reply | May still list scores; image stays molecules-only |

Implementation: `result_photo.render_design_png` — drop Pillow header + RDKit legends; sort before draw; `legends=None` / empty. Invalid SMILES skipped (do not leave blank cells with text).
