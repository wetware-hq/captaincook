# Feature: `/variant` — gene + change → plain-language evidence brief

**Status:** Locked 2026-09-20 (Minimum Idiot Index)  
**Owners:** biostrategist · biomodels · biolang · bioresearch  
**Ship order:** after `/board` (live) · before `/trials`

## Goal

Natural-language (or structured) **gene + variant** in → one specialty-agnostic Markdown brief grounded in **`/evidence`** (Europe PMC MEDLINE, Harvard cites at bottom). Research-use only. **Not a diagnosis. Not a dose.**

## v1 lock (user + room)

| Choice | Lock |
| --- | --- |
| Core | Thin wrapper on `/evidence` — papers-first narrative |
| Scoring / genomic FMs | **Out of v1.** AlphaMissense-class / ESM variant / ClinVar-style scores may land later as an **optional subsection** after the papers, labelled “computational estimate only; not a diagnosis,” with method cite. Never the lead sentence; never Discord. |
| Agnostic | Any specialty / bio subfield; KRAS G12C = smoke fixture only |
| Privacy | No raw biometrics; no Discord PHI |

## Command

```
/variant <gene> <change>
/variant <nl mentioning gene and change>
```

- Prefer card gene/variant if bare `/variant` and card has them.  
- Missing gene/change → usage help.  
- Lit down → fail-closed refuse.

## Output

One `.md` document (or photo-caption-style text if short) + Harvard **References** at bottom. Sections: what the variant is; what peer-reviewed papers report; what they do **not** prove; research-use disclaimer.

## Acceptance

1. `/variant KRAS G12C` → MEDLINE brief + DOIs; no diagnosis claim.  
2. No score block in v1.  
3. HELP specialty-agnostic.  
4. Empty hits → honest empty, no invented papers.

## Follow-on (separate FEATURE)

Optional FM/ClinVar estimate subsection behind papers.

## Split

- Spec — biostrategist  
- Wire (reuse evidence_client) — biomodels  
- TEMPLATE/COPY — biolang (`docs/TEMPLATE-variant.md`)  
