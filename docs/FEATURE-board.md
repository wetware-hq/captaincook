# Feature: `/board` — molecular board packet (specialty-agnostic)

**Status:** Locked 2026-09-20 (Minimum Idiot Index · max utility · X signal: MTB/case boards)  
**Owners:** biostrategist · biomodels · biolang (TEMPLATE-board) · bioresearch  
**Ship order:** **1** `/board` → **2** `/variant` → **3** `/trials` (follow-on FEATURES)

## Goal

One clinician-readable Markdown **board packet** assembled from stores we already have — for molecular tumour boards **or any specialty case conference**. Research-use only. No diagnosis, no treatment orders, no auto-enroll.

## Agnostic rule (user lock)

HELP/commands never brand as oncology-only or one bio subfield. KRAS/Switch-II may appear only as fixture examples. Filing tags in `clinic.md` / `lab.ipynb` are optional, not product identity.

## Inputs

- Current `/load` card (if any)  
- Patient biometrics: **on file / incomplete** only (never raw values)  
- `patient_files` count (not bodies)  
- Latest `/evidence` / `/research` briefs on card or patient store  
- Latest lab designs (`ligand:` / `binder:` from `search.json` / `lab.ipynb`)  

If no card and no patient: short refuse + tip to `/load` or `/onboard`.

## Output

One `.md` → Telegram `reply_document` + one-line TLDR caption.

Skeleton (biolang owns final prose):

```markdown
# Board packet

{research-use disclaimer — not a clinical record; not advice}

## Case context
- Card intent / gene / variant (if present)
- Patient biometrics: on file | incomplete | none
- Patient files: N on file

## Evidence
{peer-reviewed bullets + Harvard refs at bottom of this section, or “none yet — run /evidence”}

## Laboratory designs
{ligand/binder summaries + design-ids; research-use in-silico only; or “none yet”}

## Open questions
{from notes count / missing fields — no invented clinical questions}

## Source note
Assembled from session stores only; nothing inferred beyond listed fields.
```

## Commands

| Command | Behavior |
| --- | --- |
| `/board` | Build packet from current card + patient stores |
| `/board clear` | Not required v1 (packet is ephemeral document) |

## Store / privacy

- Packet is a **download artifact** for this chat turn; optional stash on card `last_run`  
- Never echo biometric secrets or note bodies  
- Never Discord-mirror PHI  
- Sorter may file a stub under `clinic.md` `## Meeting minutes` or `## General` only if user later asks — **v1: no auto-file**

## Acceptance

1. With KRAS card + evidence + binder design → packet lists all three without raw biometrics.  
2. Empty stores → honest “none yet” lines, not invented findings.  
3. HELP describes board packet without oncology-only branding.  
4. Voice: clinicians + well-educated patients; full sentences.

## Follow-ons (not this PR)

- `/variant` — gene+mut → plain brief + `/evidence`  
- `/trials` — ClinicalTrials.gov shortlist only  

## Split

- Spec — biostrategist  
- Wire — biomodels  
- TEMPLATE-board / COPY — biolang (`docs/TEMPLATE-board.md`)  
