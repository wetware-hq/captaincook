# Feature: Structures in `/app` live view (bio + chem)

**Status:** Shipped 2026-09-20  
**Depends on:** FEATURE-app.md (live HTML + R2/`extra_files` deploy)

## Goal

Laboratory **Structures** panel covering both structure types the bot already produces:

| Kind | Source | Viewer | Cap |
| --- | --- | --- | --- |
| **Biological** | `last_run` mmCIF (`kind=cif`) — fold / Boltz / binder complex | **Mol\*** (RCSB-minimal chrome, white canvas) | 1–2 |
| **Chemical** | `/design ligand` — SDF/MOL artifacts, else top SMILES from `design_csv` | **3Dmol.js** (CDN-pinned, white, no UI chrome) | ≤3 |

## Behaviour

1. `collect_structure_assets` → existing CIF paths (≤25 MB, max 2).
2. `collect_ligand_assets` → SDF/MOL files first; else ranked SMILES from `design_csv`.
3. Deploy uploads CIF (and SDF/MOL) beside HTML as public R2 URLs; SMILES are inlined (small, non-secret).
4. HTML loads pinned CDNs only when the corresponding assets exist.
5. No assets → prior page (no Structures nav, no viewer CDNs).

## Constraints

- White / serif / ≤42 rem; thin border; ~360px (grid cells ~280px).
- No secrets, biometrics, note bodies, or local filesystem paths.
- Pins: `molstar@4.18.0`, `3dmol@2.4.2`.
- Research-use only.

## Out of scope

- Gallery bloat; revoke of orphan R2 objects; diagnosis UI.
