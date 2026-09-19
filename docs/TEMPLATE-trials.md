# `/trials` Markdown template (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — specialty-agnostic; clinicians + well-educated patients  
**Hard rules:** research shortlist only; human review required; cook does **not** enroll; never “you are eligible” / enroll / contact-sponsor language; no raw biometrics; no invented trials; Harvard not required (use CT.gov links)

## Document template

```markdown
# Trials shortlist

This document lists public studies from ClinicalTrials.gov that may relate to the query or card context below. It is for research use only. A human must review every study. This bot does not determine eligibility, does not enroll anyone, and does not contact sponsors.

**Query / context:** {query_or_card_summary}

## Studies

{studies_block}

## Source note

Retrieved from ClinicalTrials.gov API v2 at search time. Counts are capped (≤10). Status and eligibility text can change on the registry — always open the study link before acting.
```

### `{studies_block}` — one unit per study (≤10)

```markdown
### {n}. {official_title}

- **NCT:** {nct_id}
- **Status:** {overall_status}
- **Phase:** {phase_or_not_applicable}
- **Why it matched:** {one or two full sentences on gene/variant/condition themes from the query or card — no eligibility verdict}
- **Eligibility themes:** {short bullets of inclusion/exclusion themes present in the registry text — frame as themes only, never “you qualify”}
- **Registry:** https://clinicaltrials.gov/study/{nct_id}
```

### Zero hits

```markdown
## Studies

No public ClinicalTrials.gov studies matched this query at the time of search. No studies are listed, and none are invented.
```

## Caption

**With hits:**

```
Trials shortlist: {n} public ClinicalTrials.gov study(ies). Research use only; human review required; this bot does not enroll.
```

**Zero:**

```
Trials shortlist: no matching public studies found. Research use only; this bot does not enroll.
```

## HELP one-liner

```
/trials [condition or gene variant] — Shortlist public ClinicalTrials.gov studies for the card or query. Eligibility themes only. Research use only; human review required; this bot does not enroll.
```

## Refuse / help

**Missing context:**

```
Please name a condition, gene, or variant, or /load a card first. Example: /trials KRAS G12C
```

**Fail-closed (API down / timeout):**

```
This request cannot proceed. The clinical trials registry did not respond safely, so no shortlist was written. Please try again shortly.
```

## Banned phrases

- you are eligible / you qualify / enroll now / we will enroll  
- recommended trial for this patient  
- Discord or PHI mirroring notes
