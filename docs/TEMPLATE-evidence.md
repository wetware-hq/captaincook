# `/evidence` Markdown template (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md  
**Split:** `/evidence` = peer-reviewed only. `/research` = preprints. Never merge the two voices.

## Document template

```markdown
# Evidence brief: {question}

This brief summarises up to five peer-reviewed articles retrieved for the question above. It is for research use only and is not clinical advice.
Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded.

## Findings

{findings_block}

## References

{references_block}
```

Order is fixed: Findings first; Harvard `## References` **only at the bottom**.

### Findings

Same claim→cite rules as `/research`: no `This article is about {title}`; strip leading `summary`/`abstract`. In-text `(Author et al., Year)`. Every in-text cite must appear in References.

**Zero hits:**

```markdown
No peer-reviewed Europe PMC / MEDLINE articles matched this question at the time of search. No findings are listed, and no references are invented.
```

References line: `None.`

### References (Harvard, bottom only)

```
{Family}, {Initials}., {Year}. {Title}. {Journal}. https://doi.org/{doi}
```

Prefer DOI-bearing hits. Cap ≤5. Do not invent DOIs. Journal name from Europe PMC (not bioRxiv).

## Captions

**Hits:** `Evidence brief for “{question}”: {n} peer-reviewed article(s). Research use only; not clinical advice.`

**Zero:** `Evidence brief for “{question}”: no matching peer-reviewed articles found. Research use only; not clinical advice.`

## Refuse / help

**Missing:** `Please provide a clinical or scientific question. Example: /evidence KRAS G12C inhibitors in NSCLC`

**Too long:** `This question is too long for a single search. Please shorten it to a few clear phrases and try again.`

**Fail-closed:** `This request cannot proceed. The literature service did not respond safely, so no evidence brief was written. Please try again shortly.`

## Privacy

Never include biometric secrets or patient files in the query, brief, or caption.
