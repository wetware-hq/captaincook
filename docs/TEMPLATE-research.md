# `/research` Markdown template (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — Proper English, full sentences, clinician + engineer readable  
**Wire from:** `src/research_*.py` (biomodels)  
**Hard rules:** no fabricated papers; max five references; no X invent; no score dumps

## Document template

Fill `{…}` only from Europe PMC records or fixed strings below. Do not invent authors, years, titles, or DOIs.

```markdown
# Research brief: {topic}

This brief summarises up to five recent bioRxiv or medRxiv preprints retrieved for the topic above. It is for research use only and is not clinical advice.

## Findings

{findings_block}

## Social signal

Social (X) signal was not available in this version.

## References

{references_block}
```

### `{findings_block}`

**When ≥1 hit:** 3–5 bullets. Each bullet is one or two full sentences: **result claim → cite**, not a title restatement.

**Banned openers (do not generate):**
- `This preprint is about {title}`
- `{Title} (Author et al., Year).` as the whole bullet
- Leading abstract junk: strip a leading `summary`, `abstract`, or `in this work, we` if present; start on the first substantive clause

**Prefer:** one concrete finding from title+abstract (mechanism, mutant, assay, or outcome), then `(Author et al., Year)`. Stay research-use; do not upgrade preprint claims to clinical fact.

Example shape (structure only):

```markdown
- Dual inhibition of GTP-bound and GDP-bound KRAS G12C is reported to suppress PI3Kα signalling with strong tumour inhibition in the cited models (Parker et al., 2026).
- Related preprints emphasise mutant-state selectivity; cross-study potency is not directly comparable without shared assays (Lee et al., 2025).
```

**When 0 hits:**

```markdown
No recent bioRxiv or medRxiv preprints matched this topic in Europe PMC at the time of search. No findings are listed, and no references are invented.
```

Leave `## References` with a single line:

```markdown
None.
```

### `{references_block}` (Harvard)

One reference per line, numbered optional; prefer unnumbered list matching VOICE restraint. Format:

```
{Family}, {Initials}., {Year}. {Title}. {Server}. {DOI_or_URL}
```

Rules:

1. Authors: `Family, A.A., Family, B.B.` — use `et al.` after three authors.  
2. Year: four-digit from first online / publication date; if missing, omit year and keep title + DOI.  
3. Title: sentence case as returned; no invented subtitle.  
4. Server: `bioRxiv` or `medRxiv` (or the Europe PMC preprint source label).  
5. Prefer `https://doi.org/{doi}`; if no DOI, use the Europe PMC full-text or abstract URL once.  
6. Cap at **five**. Sort to match findings order (recency already applied upstream).

Example shape:

```
Smith, J.A., Lee, K., 2024. A covalent inhibitor series for KRAS G12C. bioRxiv. https://doi.org/10.1101/2024.01.01.123456
```

## Telegram caption (not inside the `.md`)

One line TLDR + research-use notice. ≤1024 characters.

**With hits:**

```
Research brief for “{topic}”: {n} recent preprint(s). Research use only; not clinical advice.
```

**Zero hits:**

```
Research brief for “{topic}”: no matching preprints found. Research use only; not clinical advice.
```

## Refuse / help strings (chat text, not the document)

### Missing topic

```
Please provide a research topic. Example: /research KRAS G12C covalent inhibitors
```

### Topic too long

```
This topic is too long for a single search. Please shorten it to a few clear phrases and try again.
```

### Lit API down / timeout / unparseable (fail-closed)

```
This request cannot proceed. The literature service did not respond safely, so no research brief was written. Please try again shortly.
```

## Do not say

- “Highest signal on X” when X is deferred.  
- Fragments: “API error”, “0 results”, “PMC fail”.  
- Stack traces, raw JSON, or internal query URLs in the user caption.
