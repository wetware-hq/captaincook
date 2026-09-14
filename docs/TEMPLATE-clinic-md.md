# Per-patient `clinic.md` skeleton (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — complete sentences; clinician + well-educated patient  
**Daemon:** sole writer (full R/W). Handlers emit events only.  
**Hard rules:** no raw biometrics; no sequences/scores in Biosecurity; no preprint briefs here (`/research` → lab.ipynb); DOI-idempotent Evidence upserts; never strip bottom Harvard `## References`; no invented claims on merge; no preprint↔peer-reviewed tone swap

## Empty file (create once per patient)

```markdown
# Clinic file

Patient record for research-use documentation only. This file is not a legal medical record and is not clinical advice.

Demographics: not on file.

## Notes

## Evidence

## Meeting minutes

## Biosecurity

## General

## Oncology

## Haematology

## Cardiology

## Infectious disease

## Imaging

## Pharmacy
```

Omit empty specialty sections on create if you prefer a thinner file — **required** headers that must exist when first written: title block, Demographics line, `## Notes`, `## Evidence`, `## Meeting minutes`, `## Biosecurity`. Other specialty headers may be created on first append.

## Demographics stub (`/onboard`)

Never write age, sex, weight, height, or BMI.

| State | Line (exactly) |
| --- | --- |
| Incomplete / none | `Demographics: not on file.` |
| Complete | `Demographics: on file.` |

Replace the single Demographics line in place; do not append duplicates.

## `## Notes` (`/note`)

Append under `## Notes` (or a specialty header only if the event carries a closed-list specialty tag).

v1 prefer **count-safe** entries — no full body dump if card policy is count-only:

```markdown
- {ISO8601}: note on file (id `{note_id}`). Body retained in session patient files; not repeated here.
```

If a later lock allows short excerpts, cap at 40 characters + ellipsis; never paste biometric values.

## `## Evidence` (`/evidence`)

Upsert by **DOI** (idempotent). Each evidence unit is one sub-block:

```markdown
### {Author et al., Year} — {short title}

{Findings bullets already rendered — claim→cite; no title restatement.}

#### References

{Harvard lines with https://doi.org/… — bottom of this unit; never strip}
```

Rules:

1. If DOI already present → replace that unit; do not duplicate.  
2. Keep Findings claim→cite alignment with References.  
3. Do not move this content into specialty headers in v1 — Evidence stays under `## Evidence`.  
4. Source line from the brief may be kept once under the unit: `Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded.`

## `## Meeting minutes` (linked `/scribe` only)

Unlinked `/scribe` → user **inbox**, not this file.

When linked, append:

```markdown
### Minutes — {ISO8601}

{rendered minutes body from TEMPLATE-scribe.md — Summary through Source note}
```

Do not invent decisions when merging; if reconciling duplicates, keep the fuller source-faithful version.

## `## Biosecurity` (REVIEW/BLOCK refuses)

```markdown
- {ISO8601}: pre-compute screen returned {REVIEW|BLOCK}. No sequence or score is recorded. Compute was not started.
```

Never paste DNA/RNA/AA strings, commec internals, or refuse-stack traces.

## Specialty headers (`## Oncology`, …)

Closed list only (config): General · Oncology · Haematology · Cardiology · Infectious disease · Imaging · Pharmacy.

Append event prose under the tagged specialty when the fixed map or an explicit tag says so. Full sentences. No free-string header invention.

## Daemon rewrite limits (voice)

Allowed: create, append, dedupe by DOI/event id, retitle specialty within the closed list, merge duplicate Evidence units, compress wording without adding clinical claims.

Forbidden: upgrading preprint language into peer-reviewed tone (or the reverse); inventing attendees/decisions/doses; echoing secrets; stripping Harvard bottoms; re-querying Europe PMC to “refresh” text.
