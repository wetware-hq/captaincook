# `/annotate parts` copy (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — specialty-agnostic; research-use; **not a diagnosis**  
**Hard rules:** Bakta (+ Pyrodigal) → GenBank/GFF; PromoterAtlas or curated parts for promoter/RBS/terminator; `commec` first on DNA/RNA; never invent features; never echo sequence body; Discord dark; Chromosomal stays CNV-only

## HELP one-liner

```
/annotate parts — Annotate genetic parts on the card sequence (Bakta → GenBank/GFF; promoter/RBS/terminator via curated match). DNA/RNA only after biosecurity. Chat shows length, hash, and feature counts — not the sequence. Open /app Laboratory Parts for SEQ|TABLE. Research use only; not a diagnosis.
```

**Sibling guardrail (keep on `/annotate` HELP):** CNV/SV intervals (ClassifyCNV) + biosecurity only — not genetic-parts.

## Arm

```
/annotate parts uses the DNA or RNA sequence on the current card (or accept a FASTA upload next). Amino-acid sequences cannot invent parts. Research use only; this is not a diagnosis. Send /cancel to stop.
```

## Success caption

```
Parts annotation complete: {n} feature(s). Sequence on card only (length {L}, hash {h}). Research annotation — not a diagnosis. Open /app for Laboratory Parts (SEQ|TABLE).
```

## Markdown brief (Telegram)

```markdown
# Parts annotation

This brief summarises genetic-part features called on the sequence you supplied. It is for research use only. It is not a diagnosis, not a prognosis, and not treatment advice. The sequence body is not repeated here.

## Biosecurity screen

{PASS|REVIEW|BLOCK stamp — one sentence; if BLOCK, no features section}

## Summary

- Length: {L} · Hash: {h}
- Feature counts: {type → count bullets, ≤6 types}

## Features

{≤3 bullets overall, or top features by type:}
- {type}: {name/product} ({start}–{end}, {strand})

## Method

Bakta (+ Pyrodigal) GenBank/GFF; regulatory labels via PromoterAtlas or curated part match when present.
```

## Refuse / fail-closed

**No card:**

```
This request cannot proceed. There is no context card. Please /load a case first, then use /annotate parts.
```

**No DNA/RNA sequence:**

```
This request cannot proceed. Parts annotation needs a DNA or RNA sequence on the card (paste, FASTA upload, or prior sequence intake). Amino-acid sequences are not reverse-translated into parts.
```

**AA invent refuse:**

```
This request cannot proceed. Genetic-parts annotation does not invent features from an amino-acid sequence. Load or upload DNA or RNA instead.
```

**commec BLOCK (screened concern):**

```
This request cannot proceed. The pre-compute biosecurity screen blocked this sequence, so parts annotation was not started.
```

**commec missing (`COMMEC_BIN`) — use REFUSE-bioscreen “not configured”:**

```
This request cannot proceed. The biosecurity screen is not configured on this host (COMMEC_BIN), so annotation was not started.
```

**Bakta missing (`BAKTA_HOME` / not on PATH) — keep MSG_BAKTA_MISSING:**

```
This request cannot proceed. The Bakta annotation service is not available on this host (set BAKTA_HOME / install bakta + database). No parts were written.
```

**Tool down (binary present; runtime failure — not missing):**

```
This request cannot proceed. The parts annotation service did not respond safely, so no brief was written. Please try again shortly.
```

**BAM/CRAM (if routed here):**

```
This request cannot proceed. BAM and CRAM uploads are not accepted in this release. Please send FASTA, or use /annotate for VCF/BED intervals.
```

## `/app` Laboratory · Parts

Section under **Laboratory** (not Clinical Chromosomal).

- **SEQ (primary):** horizontal chips / bars by feature type; tap → product/span.  
- **TABLE:** colour-coded rows (type · product · start–end · strand · length); same tap panel.  
- Toggle copy: `SEQ` | `TABLE`.  
- Page chrome: length + hash only for the construct; never full sequence.  
- Tap panel ends with: `Research annotation — not a diagnosis.`

Empty: `None yet.`

Banner if needed:

```
Research use only. Parts annotations are not a diagnosis.
```

## Banned

- Inventing promoter / CDS / terminator from raw DNA without Bakta/curated match  
- Dumping sequence body in Telegram, `/app` HTML, Discord, or LM prompts  
- Merging `commec` stamps into GFF feature types  
- Calling clinical ACMG CNV language on parts features  
- HF nets as the lead annotator in user-facing copy
