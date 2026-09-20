# `/annotate` CNV copy (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — specialty-agnostic; research-use; **not a diagnosis**  
**Hard rules:** helper-first paste; no NLP invent; no AA→DNA invent; ACMG breakdown inspectable; orthogonal to `commec`; never Discord PHI; clinic.md `## Chromosomal` only (not lab.ipynb)

## HELP one-liner

```
/annotate — Paste CNV/SV intervals (BED, VCF-SV, or chr:start-end DEL|DUP) for ACMG/ClinGen-style annotation. Helper coaches bad paste. Research use only; not a diagnosis. Runs after the biosecurity screen when DNA/RNA is involved.
```


## NGS clinic paste (assembly-aware)

Prefer **BED / VCF-SV** from panel, exome, or WGS exporters. Require or prompt for assembly (**GRCh38** default; **GRCh37** accepted).

Arm add-on:

```
Include the genome build when you can (GRCh38 preferred; GRCh37 accepted). Example:
##assembly=GRCh38
chr17:43044295-43125483 DEL
```

Missing assembly helper:

```
Please name the genome build (GRCh38 or GRCh37) on the first line, then your BED or VCF-SV intervals. Chromosomal bars cannot be placed safely without a build.
```

Refuse FASTA pasted as a chromosome path — point users to interval formats, not nucleotide canvases.

## Arm

```
Send chromosomal intervals in the next message, one per line. Examples:
chr17:43044295-43125483 DEL
chr12:25205246-25250929 DUP
Or paste BED / VCF-SV lines.

Amino-acid sequences cannot be annotated as chromosomal CNVs here. Research use only; this is not a diagnosis. Send /cancel to stop.
```

## Saved / success caption

```
Chromosomal annotation complete: {n} interval(s). Research use only; not a diagnosis. Open /app for the Clinical Chromosomal section when a live view is available.
```

## Markdown brief (Telegram)

```markdown
# Chromosomal annotation

This brief summarises copy-number / structural intervals you supplied. It is for research use only. It is not a diagnosis, not a prognosis, and not treatment advice.

## Biosecurity screen

{PASS|REVIEW|BLOCK stamp — one sentence; orthogonal to ACMG; if BLOCK, no ACMG section}

## Findings

{for each interval, ≤3 bullets:}
- Interval: {chr:start-end} {DEL|DUP|…}
- Classification: {class} (ACMG/ClinGen-style criteria below)
- Overlapped genes: {gene list or none yet}

## Criteria breakdown

{inspectable bullets for the score components — plain language, not a black box}

## References

{method / guideline cites, e.g. ClassifyCNV / ACMG-ClinGen 2019 — Harvard or plain links}
```

### Zero / fail-closed

**Pure prose / bad paste (helper-first):**

```
I could not read that as CNV intervals. Please send one interval per line, for example:
chr17:43044295-43125483 DEL
chr12:25205246-25250929 DUP
Or paste BED / VCF-SV. Free paragraphs are not parsed. Send /cancel to stop.
```

**AA-only / no DNA:**

```
This request cannot proceed. Chromosomal annotation needs DNA or RNA intervals, not an amino-acid sequence. Fold or design paths stay on /esm /boltz /design.
```

**commec BLOCK:**

```
This request cannot proceed. The pre-compute biosecurity screen blocked this sequence, so chromosomal annotation was not started.
```

**Tool down:**

```
This request cannot proceed. The CNV annotation service did not respond safely, so no brief was written. Please try again shortly.
```

## clinic.md / `/app` Clinical

Section title: `## Chromosomal`

Scan-first: compact track note + ≤3 bullets + Harvard/method cites. Empty: `None yet.`

Banner if needed:

```
Research use only. Chromosomal annotations are not a diagnosis.
```



## UX inspiration (plasmid viewers → clinical)

Borrow **tap → detail** only. Do **not** ship circular plasmid chrome, enzyme rings, or a nucleotide canvas in Clinical Chromosomal. Linear chromosomal strip + class colours + breakdown panel; gene may deep-link to `/evidence` or `/variant`. SeqViz letter views stay opt-in later.


## SEQ ↔ TABLE toggle (Clinical Chromosomal)

- **SEQ (primary):** horizontal-scrolling strip so text labels stay legible; tap bar → ACMG breakdown.  
- **TABLE:** colour-coded feature rows by ACMG class (vertical scroll); same tap → breakdown.  
- Toggle label copy: `SEQ` | `TABLE`. No pan/zoom genome browser in v1.

## `/app` Clinical strip (interactive — after v1a)

- Colored CNV bars on a chromosomal strip; **tap a bar** opens a breakdown panel (class + criteria bullets + key genes).  
- Filters: chromosome · DEL/DUP. Gene name may deep-link to `/evidence` or `/variant` in Telegram — not auto-run.  
- Default view abstracts away 1-bp / 1-AA resolution; letter-level SeqViz/igv is opt-in later.  
- Panel copy: full short sentences; “Research use only; not a diagnosis.”

## Banned

- “You have cancer” / pathogenic as clinical fact / dosing  
- Merging ACMG class into the bioscreen PASS/BLOCK decision  
- Inventing intervals from prose or reverse-translating protein  
- Discord or LM prompts with raw patient-identifying paste beyond the annotate turn
