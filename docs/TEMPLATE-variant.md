# `/variant` Markdown template (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — specialty-agnostic; papers-first; clinicians + well-educated patients  
**Hard rules:** not a diagnosis; not a dose; no FM/ClinVar scores in v1; Harvard refs at bottom; no invented papers

## Document template

```markdown
# Variant brief: {gene} {change}

This brief summarises peer-reviewed literature for the gene and variant named above. It is for research use only. It is not a diagnosis, not a prognosis, and not treatment or dosing advice.

## What this variant is

{one or two full sentences naming the gene, the change, and the molecular class if stated in sources — no clinical assertion}

## What the papers report

{3–5 claim→cite bullets from /evidence hits; (Author et al., Year)}

## What the papers do not prove

{1–3 full sentences on limits: study design, population, actionability gaps — never invent absence of evidence as proof of safety or harm}

## References

{Harvard lines with https://doi.org/… ; ≤5; bottom only}
```

### Zero hits

```markdown
# Variant brief: {gene} {change}

This brief is for research use only. It is not a diagnosis or treatment advice.

## Findings

No peer-reviewed Europe PMC / MEDLINE articles matched this gene and variant at the time of search. No findings are listed, and no references are invented.

## References

None.
```

## Caption

```
Variant brief for {gene} {change}: peer-reviewed literature only. Research use only; not a diagnosis.
```

## Refuse / help

**Missing gene/change:**

```
Please name a gene and a variant. Example: /variant KRAS G12C
```

**Fail-closed:**

```
This request cannot proceed. The literature service did not respond safely, so no variant brief was written. Please try again shortly.
```

## Later (not v1): optional score subsection

Only after the papers sections, if a future FEATURE enables it:

```markdown
## Computational estimate (optional)

{Method name and version} reports an estimate of {quantity}. This is a computational estimate only. It is not a diagnosis and does not replace the papers above. See {cite}.
```

Never open the document with a score.
