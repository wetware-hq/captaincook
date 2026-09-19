# Feature: Mol* structures in `/app` live view

**Status:** Shipped 2026-09-20  
**Depends on:** FEATURE-app.md (live HTML + R2/`extra_files` deploy)

## Goal

Show up to **three** mmCIF structures from the session `last_run` in the Laboratory section of the TTL HTTPS page, using embedded **Mol\*** (molstar) from a pinned jsDelivr build.

## Behaviour

1. `collect_structure_assets(user_data)` reads `load_card(...).last_run.files` with `kind` in `{cif, mmcif, structure_cif}` (existing files only, ≤25 MB, max 3).
2. On deploy, `/app` allocates a slug, uploads each CIF beside the HTML as `{slug}-mol{i}.cif` via `deploy_live_html(..., extra_files=...)`.
3. HTML receives public HTTPS URLs only (`{APP_DEPLOY_BASE_URL}/{slug}-mol{i}.cif`) — never local paths.
4. Laboratory → **Structures** (`#structures`): one figure per viewer; Mol\* init is minimal (no control chrome).
5. If no CIF assets, the page matches prior behaviour (no Mol\* CDN, no Structures nav).

## Constraints

- White / serif / ≤42 rem visual lock unchanged.
- No secrets, biometrics, note bodies, or filesystem paths in HTML.
- CDN pin: `molstar@4.18.0` (`build/viewer/molstar.js` + `molstar.css`).
- Research-use-only tone; CIF also remains available via `/download`.

## Out of scope (v1)

- 3Dmol.js SMILES ligands (optional later).
- Revoking orphan CIF objects on `/app revoke` (HTML revoke only; TTL + regenerate covers rotation).
