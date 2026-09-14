# Feature: `/note` — patient files on the card (separate from biometric secrets)

**Status:** Locked 2026-09-14  
**Owners:** biostrategist (spec) · biomodels (wire) · biolang (copy) · bioplatform (no Discord mirror)  
**Depends on:** `/onboard` patient biometrics present on current card  
**Supersedes for ship:** embedding/RAG drafts — **out of this PR** (document only; do not wire)

## Goal

If the current card has an onboarded **patient** (biometrics block exists), `/note` takes the **next user message** and appends it to a **patient files** store linked to that card. Biometric secrets and note files are **separate concerns**.

## Locked answers (bioresearch)

1. **Yes** — notes live in `context_card.patient_files` (or equivalent), **not** inside the biometric `patient` secret field block from `/onboard`.  
2. **Notes:** Telegram-session-only, linked to the card; **not** secret-flagged like biometrics, but **never** sent to Discord, `/research` Markdown, 3C captions, refuse strings, or **any language-model prompt** in v1. **Biometrics (secrets):** never echoed; **never** enter any LM / embed / research / Discord path.  
3. **Yes** — if no patient on the current card → clear refuse; no-op (biolang string). Do not create a patient via `/note`.

## Minimum Idiot Index

| Concern | Store | Downstream LM |
| --- | --- | --- |
| Biometrics (`/onboard`) | `patient` secrets | **Hard block** — never in prompts, embeds, research, Discord |
| Notes (`/note`) | `patient_files[]` | **Hard block in v1** — store + list/clear only; no embed, no local/hosted LM |

Separate names in all user-facing copy (@biolang): never one blob called “patient data.”

## Commands

| Command | Behavior |
| --- | --- |
| `/note` | If patient exists: arm “next message is a note”; else refuse. |
| *(next plain message while armed)* | Append one file entry `{ id, text, created_at }` (cap **2000** chars); ack without echoing full body (short “Note saved.” / count). |
| `/note list` | Count + timestamps only (or first 40 chars redacted policy — prefer **count only** in v1). |
| `/note clear` | Drop all patient_files; biometrics untouched. |
| `/onboard clear` | Drops biometrics; **also** drop patient_files (same patient gone). |
| `/load clear` | Drops card, biometrics, and files. |

## Data shape

```
context_card:
  patient: { secret: true, age_years, sex, weight_kg, height_cm, bmi, complete, … }
  patient_files: [
    { id: str, text: str, created_at: iso8601 }
  ]
```

Fingerprint / `/view`: exclude `patient` **and** `patient_files`.

## Discord

No mirror of `/note` or file contents (@bioplatform lock stands).

## Acceptance

1. No patient → `/note` refuses.  
2. After `/onboard` complete → `/note` → user message → file count 1; `/load` still shows only Patient: on file (no note body).  
3. Biometrics never appear in any LM-bound string builder (grep/guard in code).  
4. Notes never passed into research/caption/Discord helpers.  
5. `/note clear` removes files only; biometrics remain.

## Split

- Spec — **biostrategist**  
- Wire — **biomodels**  
- Copy — **biolang** (`COPY-note.md`)  
- Discord — **bioplatform** (confirm no hook)
