# Feature: Interpretable result unit (image + clinical NL)

**Status:** Locked 2026-09-12 (single-message amendment)  
**Owners:** biostrategist (copy/structure) · biomodels (Telegram packaging)  
**Builds on:** 3C `interpret.py`, inline PNGs, `/load` `last_run`

## Goal

For **each** successful fold/design call, deliver **one consolidated result unit** that a physician and a patient can read smoothly together — not a scattered text bubble, then image, then metrics.

## Problem today

Order is: separate 3C `reply_text` → `reply_photo` (generic caption) → CIF/table. Easy to miss the link between “what the picture shows” and “what it means.”

## Locked UX (proposed MVP)

### Primary message (one Telegram photo)
`reply_photo` with:
- **Image:** protein PNG or design ligand grid (unchanged renderers)
- **Caption:** the 3C clinical paragraph (≤1024 chars), ending with a one-line research-use caveat  

No separate interpretation `reply_text` before the image.

### Secondary message (optional, specialists)
Compact metrics / ranked table / CIF as today, prefixed e.g. `Details (scores & files):` so patients can skip; physicians can dig in.

### Card
`last_run.interpretation` still stores the same paragraph used as caption.

## Dual audience (3C + “for both”)

Rewrite templates so each paragraph does three beats in one block:

1. **What this is** — “computer model of …” (patient-safe)  
2. **What the picture shows** — structure shape / ranked molecules (ties caption to image)  
3. **What it does *not* mean** — not a diagnosis, not an approved drug, not lab-proven  

Tone: clinically understandable, no fear language, no treatment advice.

## Example captions

**Fold:**  
> This image is a computer-predicted 3D shape of the protein (about {n} amino acids; model confidence ~{x}). It helps researchers see folds and possible pockets. It is not an experimental structure and does not diagnose disease or guide treatment on its own. Research-use only.

**Design:**  
> This grid shows {n} computer-suggested small molecules for the loaded target, best first (left→right, top→bottom). The top idea has an in-silico binder score ~{bind}. These are starting points for research discussion—not validated medicines and not a prescription. Research-use only.

## Implementation

| Change | Owner |
| --- | --- |
| `interpret.py` — dual-audience captions that reference “this image/grid” | biostrategist (draft) + biomodels |
| `photo.py` / bot — pass interpretation as `caption=` on `reply_photo`; remove preceding blurb `reply_text` | biomodels |
| Keep secondary metrics/CIF after the photo unit | biomodels |
| Persist caption text on `last_run` | already planned |

## Acceptance

1. One successful `/boltz` → **one** photo whose caption is the clinical NL (no prior blurb message).  
2. `/confirm` design → grid photo with clinical caption; ranked scores in a following “Details” message.  
3. Caption mentions what the image shows + research caveat.  
4. `/load` card still shows stored interpretation.  
5. Telegram caption ≤ 1024 characters.

## Non-goals

- Text burned into the design grid PNG (stays no-text molecules)  
- Separate patient vs physician messages in v1 (one dual-audience caption)  
- Clinical decision support or care pathways

## Amendment (user 2026-09-12) — single Telegram message

Call outputs are **one** Telegram message: `reply_photo` + clinical caption only.

- No separate blurb before the photo
- No secondary Details message for scores/CIF
- Optional short scores inside the caption if total ≤1024 chars
- Do not send mmCIF in the same turn by default (would force a second message)
- `last_run.interpretation` still stores the caption text

