# `/design` dual-mode copy (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md  
**Modes (explicit only — never auto-guess):**

| Mode | Engine | Namespace |
| --- | --- | --- |
| `ligand` | Boltz small-molecule (today’s path) | `ligand:` |
| `binder` | BindCraft protein binder | `binder:` |

## HELP lines

```
/design ligand [n] — Queue Boltz small-molecule design (confirm required).
/design binder [n] — Queue BindCraft protein-binder design (confirm required).
/design — Ask which mode: ligand or binder.
```

Bare `/design` without a mode:

```
Please choose a design mode: /design ligand or /design binder. Ligand uses Boltz for small molecules. Binder uses BindCraft for protein binders.
```

## Confirm cards

### Ligand (Boltz)

```
Pending ligand design (Boltz). Molecules: {n}. Estimated cost: about US${cost}. Research use only — in-silico candidates, not validated inhibitors. Reply /confirm to spend or /cancel to stop.
```

### Binder (BindCraft) — with hotspot (user-supplied)

```
Pending binder design (BindCraft). Designs: {n}. Hotspot residues will be used as supplied on the card. This job can take tens of minutes to a few hours. Research use only — in-silico protein binders, not validated therapeutics. Reply /confirm to spend or /cancel to stop.
```

### Binder — KRAS Switch-II fixture map

```
Pending binder design (BindCraft). Designs: {n}. Hotspot residues 60–76 come from the curated KRAS Switch-II fixture map (not free-text invention). This job can take tens of minutes to a few hours. Research use only — in-silico protein binders, not validated therapeutics. Reply /confirm to spend or /cancel to stop.
```

### Binder — no hotspot (target-wide)

```
Pending binder design (BindCraft). Designs: {n}. No hotspot was supplied; the run is target-wide. Hotspots are not invented. This job can take tens of minutes to a few hours. Research use only — in-silico protein binders, not validated therapeutics. Reply /confirm to spend or /cancel to stop.
```

## Fail-closed

**BindCraft / AF2 missing:**

```
This request cannot proceed. BindCraft is not configured on this host (BINDCRAFT_HOME), so no binder design was started. Ligand design via /design ligand remains available if Boltz is configured.
```

**Modal BindCraft job failed / timed out** (`kind=failed` — distinct from missing BINDCRAFT_HOME):

```
This request cannot proceed. The Modal BindCraft job failed or timed out (weights/runner error, no filter-passing designs, or GPU timeout). No binder design was started. Ligand design via /design ligand remains available if Boltz is configured.
```

**Modal app not deployed** (creds present, app missing):

```
This request cannot proceed. Modal credentials are present, but the BindCraft Modal app is not deployed yet (set MODAL_BINDCRAFT_APP and deploy modal_app/bindcraft_app.py with GPU image + weights volume). No binder design was started. Ligand design via /design ligand remains available if Boltz is configured.
```

**No card / no structure (binder):**

```
This request cannot proceed. Binder design needs a context card with a target structure. Please /load a target and obtain a structure (for example /esm or /boltz), then use /design binder.
```

**Ambiguous / missing mode:** use the bare `/design` prompt above.

## Result captions (3C shape — research-use close)

**Ligand:** keep existing Boltz ligand-grid caption contract (in-silico only; no drug claims).


**Binder image colour:** target polymer keeps the default cartoon colour; binder chain is coloured distinctly (orange) so the design is visually separable from the target.
**Binder — N=1 (`reply_photo` single cartoon):**

```
This image shows the loaded target with one ranked in-silico protein binder from BindCraft. Scores and poses are computational estimates only. Research use only; not a validated binder or therapeutic.
```

**Binder — N>1 (`reply_photo` ranked grid, ligand-style):**

```
This image is a grid of ranked in-silico protein binders from BindCraft on the loaded target. Each cell is a computational complex view. Scores and poses are estimates only. Research use only; not validated binders or therapeutics.
```

**Binder — text-only fallback (no PNG yet):**

```
BindCraft returned ranked in-silico protein binder designs for the loaded target. Structure files are available via /download. Scores are computational estimates only. Research use only; not a validated binder or therapeutic.
```

Do not say “this image shows…” unless a photo is actually attached.


## Hotspot HELP tip

```
On KRAS, naming Switch-II (or Switch 2 / SII) fills hotspot residues from the curated fixture map (residues 60–76). Other pocket names do not set a hotspot by themselves; supply residue numbers on the card if you want a hotspot, otherwise the run is target-wide.
```

## Do not say

- That binder and ligand are the same pipeline  
- “Best binder” / wet-lab hit-rate guarantees  
- Invented hotspot residues  
- Discord mirror of designs
