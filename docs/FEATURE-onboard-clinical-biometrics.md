# Feature: `/onboard` — clinical biometrics on the context card (secrets)

**Status:** Locked 2026-09-14 (Minimum Idiot Index)  
**Owners:** biostrategist (spec) · biomodels (wire) · biolang (question + refuse copy)  
**Depends on:** `/load` context card session store  
**Out of scope v1:** EHR import; FHIR; diagnosis; dosing; drug–drug checks; Discord/WhatsApp mirror of secrets; LLM interview; free-text medical history dump

## Goal

`/onboard` initialises a fixed **patient biometrics** block on the current context card, marked **secrets**, and fills it by asking **one short question at a time** in Telegram chat. Values never appear in public card dumps, `/view` fingerprints, Discord webhooks, research Markdown, or error text.

Research-use only. Not clinical care. No diagnosis or treatment claims.

## Minimum Idiot Index decisions (locked)

| Choice | Lock |
| --- | --- |
| Field set | Fixed four fields only (below). No open-ended “tell me your history.” |
| Flow | One question → one reply → next. No multi-field forms in v1. |
| Storage | `context.user_data["context_card"]["patient"]` (or sibling key) with `secret: true`. If no card, create a minimal card shell for patient only. |
| Display | `/load` (show card) lists **Patient: on file** or **Patient: incomplete** — never echo raw values. |
| Fingerprint / `/view` | **Exclude** all `patient` fields from card fingerprint. |
| Bioscreen | Not applied to biometrics (not a sequence). |
| Discord | Never mirror patient secrets. |
| Clear | `/onboard clear` drops patient secrets only; `/load clear` drops card **and** patient. |

## Secret fields (v1)

| Key | Ask (biolang may polish) | Valid |
| --- | --- | --- |
| `age_years` | “What is the patient’s age in whole years?” | integer 0–120 |
| `sex` | “Patient sex for research coding: `F`, `M`, or `X`?” | `F` \| `M` \| `X` |
| `weight_kg` | “Weight in kilograms?” | float 1–400 |
| `height_cm` | “Height in centimetres?” | float 30–250 |

Derived (optional, computed, not asked): `bmi` = weight_kg / (height_m²), stored only if both present; still secret.

Missing any of the four → `patient.complete = false`. All four valid → `patient.complete = true`.

## Commands

| Command | Behavior |
| --- | --- |
| `/onboard` | Init empty patient secret block if absent; start or resume Q&A at first missing field. |
| `/onboard status` | “Complete” / “Incomplete (missing: …)” — **no raw values**. |
| `/onboard clear` | Delete patient secrets; end onboard conversation state. |
| (plain reply while onboard active) | Parse as answer to current question; on invalid, re-ask once with short hint. |

Cancel: `/cancel` ends onboard Q&A without clearing already-saved secrets (same spirit as design cancel).

## Conversation state

```
user_data["onboard"] = {
  active: bool,
  next_field: "age_years" | "sex" | "weight_kg" | "height_cm" | null,
}
user_data["context_card"]["patient"] = {
  secret: true,
  complete: bool,
  age_years: int | null,
  sex: "F"|"M"|"X"| null,
  weight_kg: float | null,
  height_cm: float | null,
  bmi: float | null,
  updated_at: iso8601,
}
```

## Safety / privacy

1. Never log raw patient values at INFO; DEBUG only if already gated off production.  
2. Never include patient block in `/download` artifacts or research `.md`.  
3. Help text: research-use; not for clinical decisions; user is responsible for lawful handling of personal data.  
4. Refuse requests to “diagnose from biometrics” — short refuse (biolang).

## Acceptance

1. `/onboard` → four questions in order → `status` reports Complete without printing numbers.  
2. `/load` shows Patient: on file, not the values.  
3. G12C `/view` fingerprint unchanged when only patient secrets change.  
4. `/onboard clear` removes secrets; incomplete mid-flow can resume.  
5. Invalid age `999` re-asks; does not store.

## Split

- Spec — **biostrategist**  
- Handler + card fields + fingerprint exclude — **biomodels**  
- Question / status / refuse strings — **biolang** (`docs/COPY-onboard.md`)
