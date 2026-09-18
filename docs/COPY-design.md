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

### Binder (BindCraft) — with hotspot

```
Pending binder design (BindCraft). Designs: {n}. Hotspot residues will be used as supplied on the card. Research use only — in-silico protein binders, not validated therapeutics. Reply /confirm to spend or /cancel to stop.
```

### Binder — no hotspot (target-wide)

```
Pending binder design (BindCraft). Designs: {n}. No hotspot was supplied; the run is target-wide. Hotspots are not invented. Research use only — in-silico protein binders, not validated therapeutics. Reply /confirm to spend or /cancel to stop.
```

## Fail-closed

**BindCraft / AF2 missing:**

```
This request cannot proceed. BindCraft is not configured on this host (BINDCRAFT_HOME), so no binder design was started. Ligand design via /design ligand remains available if Boltz is configured.
```

**No card / no structure (binder):**

```
This request cannot proceed. Binder design needs a context card with a target structure. Please /load a target and obtain a structure (for example /esm or /boltz), then use /design binder.
```

**Ambiguous / missing mode:** use the bare `/design` prompt above.

## Result captions (3C shape — research-use close)

**Ligand:** keep existing Boltz ligand-grid caption contract (in-silico only; no drug claims).

**Binder:**

```
This image shows ranked in-silico protein binder designs from BindCraft for the loaded target. Scores and poses are computational estimates only. Research use only; not a validated binder or therapeutic.
```

## Do not say

- That binder and ligand are the same pipeline  
- “Best binder” / wet-lab hit-rate guarantees  
- Invented hotspot residues  
- Discord mirror of designs
