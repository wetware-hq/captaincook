# `/onboard` copy (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — Proper English; never echo raw biometrics  
**Wire from:** `src/onboard.py`  
**Hard rules:** research-use only; no diagnosis/dosing; values never in status, `/load`, captions, Discord, research `.md`, or errors

## Questions (one at a time)

| Field | String |
| --- | --- |
| `age_years` | What is the patient’s age in whole years? |
| `sex` | Patient sex for research coding: F, M, or X? |
| `weight_kg` | What is the patient’s weight in kilograms? |
| `height_cm` | What is the patient’s height in centimetres? |

## Invalid hints (re-ask)

| Field | String |
| --- | --- |
| `age_years` | Please reply with a whole number from 0 to 120. |
| `sex` | Please reply with F, M, or X. |
| `weight_kg` | Please reply with a number of kilograms from 1 to 400. |
| `height_cm` | Please reply with a number of centimetres from 30 to 250. |

## Status / card (no raw values)

| Case | String |
| --- | --- |
| Empty | Patient biometrics are incomplete (missing: age_years, sex, weight_kg, height_cm). Values are not shown. |
| Partial | Patient biometrics are incomplete (missing: {fields}). Values are not shown. |
| Complete | Patient biometrics are complete. |
| Complete + secrets note | Patient biometrics are complete. Values are stored as secrets and are not shown. |
| `/load` not on file | Patient: not on file. |
| `/load` incomplete | Patient: incomplete. |
| `/load` on file | Patient: on file. |

## Clear / cancel

| Case | String |
| --- | --- |
| Cleared (`/onboard clear`) | Patient biometric secrets have been cleared. |
| Cleared (`/load clear`) | The context card and any patient biometrics have been cleared. |
| Cancel Q&A | Onboarding questions have stopped. Saved biometrics, if any, remain as secrets until cleared. |

## Refuse (diagnose / dose from biometrics)

```
This request cannot be fulfilled. Biometrics collected here are for research context only. This bot does not diagnose, dose, or give clinical advice from age, sex, weight, height, or BMI.
```

## Intro (optional first `/onboard`)

```
Research-use biometrics only. Four short questions follow. Values stay secret on this chat’s context card and are never shown in /load, /view, Discord, or research briefs. Not for clinical decisions.
```
