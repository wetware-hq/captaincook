# Feature: 3C result interpretation (fold + design)

**Status:** Locked 2026-09-12 (live on poller)  
**Owners:** biostrategist (tone/templates) · biomodels (wire order + card storage)  
**Applies to:** `/esm`, `/boltz`, `/design`→`/confirm` success paths

## Goal

Every successful folding or design run yields **one paragraph** of natural-language interpretation that is:

1. **Concise** — ~2–4 sentences, one Telegram message  
2. **Clear** — plain language, no jargon wall  
3. **Clinically understandable** — what the numbers/structure mean for a research/clinical reader, without diagnosing or claiming a drug  

**Placement:** this paragraph is sent **before** the embedded image for that run.  
**Persistence:** stored on the current `/load` context card (if any) as the latest run interpretation.

## Non-goals

- LLM calls in v1 (deterministic templates from metrics)  
- Multi-paragraph essays or bullet dumps in the interpretation slot  
- Clinical advice, dosing, treatment recommendations, or “this is a drug” claims  
- Replacing the ranked metrics table / CIF — those still follow (or accompany) after the image as today

## Reply order (locked)

For each successful run:

1. **3C interpretation paragraph** (`reply_text`)  
2. **Image** (`reply_photo`) — protein PNG and/or design ligand grid  
3. Existing extras — summary table / CIF document / disclaimer as already implemented  

If image render fails: still send the 3C paragraph, then text+CIF, then one-line image-fail note.

## Card storage

Extend `ContextCard` / `user_data["context_card"]`:

```
last_run:
  kind: esm_fold | boltz_structure | boltz_binding | small_molecule_design
  at: iso8601
  interpretation: str          # the 3C paragraph
  metrics: dict                # compact scores used to build it
  run_id: str | null
```

- Written only when a context card exists (from `/load`); if no card, still show the paragraph in chat, skip persist  
- `/load` (show card) includes `last_run.interpretation` when present  
- New `/load <nl>` replaces the card and clears prior `last_run` unless we merge — **v1: new load clears last_run**

## 3C voice rules

- Second person or neutral (“This model…”) — not “you have cancer”  
- Always frame as **in silico / research model output**  
- Never say “approved”, “safe”, “will work in patients”, “diagnosed”  
- Prefer: confidence, relative ranking, caveats (“not experimentally validated”)  
- One short closing caveat clause inside the same paragraph  

## Template inputs → paragraph (v1 deterministic)

### Fold (`/esm`, `/boltz` structure-only)
Inputs: length aa; structure_confidence / pLDDT / pTM if present.  
Example pattern:  
> “This predicted structure covers {n} amino acids with overall model confidence around {x}. The fold is a computational estimate useful for exploring shape and pockets, not a substitute for an experimental structure. Treat it as research-only guidance for the next design or binding step.”

### Binding (`/boltz` + ligand)
Inputs: binding_confidence, optimization_score, structure_confidence.  
Example:  
> “The predicted complex scores about {bind} for binder likelihood and {opt} for relative affinity ranking, with structure confidence near {sc}. Higher binder likelihood suggests a plausible in-silico pose for this ligand, but it is not proof of activity in cells or patients. Use this only to prioritize ideas for lab follow-up.”

### Design (`/confirm`)
Inputs: n, top binding_confidence, top optimization_score, ADME flag on #1, run cost/time optional.  
Example:  
> “We generated {n} candidate molecules; the top-ranked hit shows binder likelihood ~{bind} and relative score ~{opt} ({adme_note}). Molecules are ordered best-to-worst in the image (left-to-right, top-to-bottom). These are computer-proposed starting points only—not validated inhibitors or clinical candidates.”

## Implementation

| File | Change |
| --- | --- |
| `src/interpret.py` *(new)* | `interpret_fold(...)`, `interpret_binding(...)`, `interpret_design(...)` → `str` |
| `src/context_card.py` | `last_run` field; `attach_last_run(card, ...)`; `format_card` shows it |
| `src/bot.py` / `photo.py` | Before every `reply_photo`, `reply_text(interpretation)`; then persist to card |
| `docs/FEATURE-3c-result-interpretation.md` | this spec |

## Acceptance

1. `/boltz <seq>` success → 3C paragraph message, then PNG, then CIF.  
2. `/design`→`/confirm` → 3C paragraph, then ligand grid PNG.  
3. With a prior `/load` card, `/load` (no args) shows the stored `last_run.interpretation`.  
4. Paragraph has no bullet list; single block; includes research caveat.  
5. No overclaim words (approved/safe/cure/diagnosis).

## Split

- **biostrategist:** templates + acceptance language  
- **biomodels:** interpret.py wiring, reply order, card persist, poller  
