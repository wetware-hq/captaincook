# Feature: `/evidence <question>` — peer-reviewed Europe PMC brief + citations

**Status:** Locked 2026-09-14 (Minimum Idiot Index)  
**Owners:** biostrategist (spec) · biomodels (wire) · bioresearch (query sanity) · biolang (template/copy)  
**Depends on:** Europe PMC HTTP client patterns from `/research`; Telegram `reply_document`  
**Out of scope v1:** OpenEvidence; X scrape; RAG; patient secrets / `patient_files` in prompts; Discord mirror (unless later amend)

## Goal

Answer a clinical/research question with a short Markdown brief grounded in **peer-reviewed** Europe PMC hits, with a **Harvard citation list** (required). No GPU. Fail-closed if Europe PMC is down.

## Split from `/research` (user lock)

| Command | Corpus | Citations |
| --- | --- | --- |
| `/research <topic>` | **Unchanged** — preprint OK (bioRxiv/medRxiv `SRC:PPR` filter as today) | Harvard list ≤5 |
| `/evidence <question>` | **Peer-reviewed filter only** — exclude preprints | Harvard list ≤5 (**required**) |

Do not merge the two handlers into one ambiguous filter flag in user-facing copy — two commands, two contracts.

## Minimum Idiot Index

| Choice | Lock |
| --- | --- |
| Client | Europe PMC REST only (reuse transport; separate query builder) |
| Peer-review filter | `(question) AND SRC:MED NOT SRC:PPR` (MEDLINE/PubMed path; no preprint source). Drop hits that still look like `source=PPR` if any slip through. |
| Cap | Top **5** after recency sort (year/first pub date desc; relevance tie-break) |
| Citations | **Harvard style**, always at the **bottom** of the output (after Findings). `## References` when ≥1 hit. Zero hits → honest empty findings, **no fake cites**. |
| Evidence tier line | One line in the brief: “Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded.” |
| Output | One `.md` → Telegram document; caption = 1-line TLDR + research-use notice |
| Privacy | Never send biometric secrets or `patient_files` into the query or the brief |
| Bioscreen | Off (not a sequence) |
| OpenEvidence / X | Out |

## Command

```
/evidence <natural language clinical or scientific question>
```

- Missing text → usage help.  
- Length cap (~300–500 chars) → refuse overlong.  
- Lit down / bad JSON → fail-closed refuse (biolang); no invented papers.

## Implementation sketch

```
src/evidence_client.py   # search_peer_reviewed(question) -> list[Record]
src/evidence_md.py       # render brief + Harvard refs (biolang template)
# /research keeps research_client.QUERY_FILTER = SRC:PPR bioRxiv/medRxiv
```

Reuse `Record` / Harvard formatting helpers where possible; **do not** change `/research` default filter.

## Markdown shape (biolang owns final prose)

Order is fixed: **Findings first, Harvard references last** (bottom of the document / message payload).

```markdown
# Evidence brief: {question}

{research-use disclaimer}
Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded.

## Findings
- Claim in full sentences (Author et al., Year).
…

## References
Author, A.A., Year. Title. Journal. https://doi.org/…
```

- In-text cites in Findings use Harvard `(Author et al., Year)`.
- Full Harvard reference list is **only** at the bottom under `## References`.
- Every in-text cite must appear in that bottom list. No footnote mid-body reference dump.


## Citations / DOIs (locked 2026-09-14)

- Harvard reference list at the **bottom** of the Markdown.
- Every Reference line **must include a DOI** as `https://doi.org/{doi}` when Europe PMC provides one.
- Prefer selecting the top ≤5 hits that **have DOIs**; do not invent DOIs.
- If fewer than one DOI-bearing hit remains → honest empty references (no fake cites).

## Acceptance

1. `/evidence KRAS G12C inhibitors in NSCLC` → `.md` with ≤5 **non-preprint** hits; Harvard `## References` at the **bottom** of the file.  
2. Same topic via `/research` may still return bioRxiv/medRxiv (unchanged).  
3. Zero peer-reviewed hits → honest empty; no fabricated references.  
4. No patient secrets/files in query or document.  
5. Europe PMC failure → refuse, no partial fake brief.

## Split

- Spec — **biostrategist**  
- Client + `/evidence` handler — **biomodels**  
- Template / caption / refuse — **biolang** (`TEMPLATE-evidence.md` / `COPY-evidence.md`)  
- Filter sanity — **bioresearch**
