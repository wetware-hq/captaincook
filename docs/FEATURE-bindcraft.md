# Feature: `/design` modes — ligand (Boltz) · binder (BindCraft)

**Status:** Locked 2026-09-19 · consolidated under `/design` (user: ligand / binder)  
**Owners:** biostrategist · biomodels · bioresearch · biolang (`docs/COPY-design.md`)  
**Supersedes:** standalone `/bind` as the user-facing command (withdrawn)

## Goal

One `/design` surface, **two explicit modes** — never auto-guess from the card.

| Mode | Engine | Product |
| --- | --- | --- |
| **`ligand`** | Boltz small-molecule design | today’s `/design` → `/confirm` path |
| **`binder`** | BindCraft | protein binder design |

## Commands

| Command | Behavior |
| --- | --- |
| `/design` | Prompt for mode: **ligand** or **binder** (biolang COPY). |
| `/design ligand` `[n]` | Boltz path (existing confirm/cost; API floor 10). |
| `/design binder` `[n]` | BindCraft path: need structure; hotspot optional; N default **5**, cap **20**; confirm gate. |
| `/confirm` / `/cancel` | Shared pending-job slot — one spend job at a time. |
| `/bind` | One-line stub: use `/design binder` (if registered). |

## Binder locks (unchanged)

- Hotspot **optional**; never invent; confirm states target-wide if absent.  
- Filters: **BindCraft defaults only** (no Boltz-2 re-score in v1).  
- Fail-closed if `BINDCRAFT_HOME` / AF2 weights missing.  
- Research-use captions; not validated binders.  
- Bioscreen/validate designed AA before return.

## Store

- Both land in **`lab.ipynb`**.  
- `search.json` namespaces: **`ligand:`** / **`binder:`** (plus design-id).  
- Not `clinic.md`. Discord out.

## Ligand path

Unchanged Boltz behaviour; HELP/README say `/design ligand` as the explicit small-molecule entry (bare `/design` only asks mode).

## Acceptance

1. `/design` with no mode → mode prompt, no GPU.  
2. `/design ligand` → existing Boltz confirm flow.  
3. `/design binder` → BindCraft confirm; fail-closed without weights.  
4. No silent mode swap from card intent.  
5. COPY-design strings match (biolang locked).

## Split

- Spec — biostrategist  
- Wire dual-mode `/design` — biomodels (when GPU ready for binder)  
- Voice — biolang (`COPY-design.md`)  
- Pipeline — bioresearch  
