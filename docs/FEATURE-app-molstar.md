# Feature: Mol* structure in `/app` live view

**Status:** Shipped 2026-09-20  
**Depends on:** FEATURE-app.md (live HTML + R2/`extra_files` deploy)

## Goal

RCSB-style **structure-first** panel: one primary mmCIF from session `last_run` in Laboratory, using embedded **Mol\*** (pinned jsDelivr). Cap **2** CIFs. No second viewer framework.

## Behaviour

1. `collect_structure_assets(user_data)` takes `last_run.files` with `kind` in `{cif, mmcif}` (existing, ≤25 MB, max 2; primary = first cif).
2. On deploy, `/app` uploads `{slug}-mol{i}.cif` via `extra_files` and passes public HTTPS URLs into HTML.
3. Laboratory → **Structures** (`#structures`): minimal Mol\* chrome (no controls/sequence/log/left panel), white canvas, ~360px, thin border.
4. No CIF → unchanged page (no Mol\* CDN, no Structures nav).

## Constraints

- White / serif / ≤42 rem; no dark theme.
- No secrets, biometrics, note bodies, or local paths in HTML.
- CDN: `molstar@4.18.0` (`build/viewer/molstar.js` + `molstar.css`).
- Research-use only; CIF still via `/download`.

## Out of scope (v1)

- 3Dmol.js / SMILES ligands.
- Gallery of many widgets; revoke of orphan CIF objects.
