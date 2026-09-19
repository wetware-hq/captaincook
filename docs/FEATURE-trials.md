# Feature: `/trials` — public registry shortlist (never enroll)

**Status:** Locked 2026-09-20 (Minimum Idiot Index)  
**Owners:** biostrategist · biomodels · biolang · bioresearch  
**Ship order:** after `/board` + `/variant` (both live)

## Goal

Shortlist **public** clinical studies matching the card’s gene/variant/condition (or NL args). Eligibility **themes** only. Research-use. **Never enroll**, never contact sponsors, never Discord PHI.

## Client (locked)

**One** client: ClinicalTrials.gov API v2 (public). No second registry in v1 (Idiot Index).

## Command

```
/trials
/trials <nl condition or gene variant>
```

- Bare `/trials` uses card gene/variant/condition if present.  
- Missing context → usage help.  
- Cap **N=10** (default 5).  
- API down / timeout → fail-closed refuse.

## Output

One Markdown document → Telegram document (or text if short):

- Study title, NCT id, status, phase (if any)  
- Why it matched (gene/variant/condition themes)  
- Eligibility themes (inclusion/exclusion highlights) — not a determination  
- Link to ClinicalTrials.gov  
- Disclaimer: research shortlist; human review required; cook does not enroll  

## Agnostic + privacy

Specialty/subfield-agnostic. No raw biometrics. No Discord mirror.

## Acceptance

1. `/load` KRAS G12C → `/trials` → ≤N public studies or honest empty.  
2. Never “you are eligible” / enroll language.  
3. API failure → refuse, no invented trials.  
4. HELP lists `/board` `/variant` `/trials`.

## Split

- Spec — biostrategist  
- Wire CT.gov client + handler — biomodels  
- TEMPLATE-trials + README — biolang (`docs/TEMPLATE-trials.md`)  
