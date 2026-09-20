# Bioscreen refuse copy (v1)

**Owner:** biolang  
**Applies to:** `PASS` | `REVIEW` | `BLOCK` user replies from `src/bioscreen.py`  
**Cadence:** docs/VOICE.md — Proper English, full sentences, clinical utility first  
**Hard rules:** one short paragraph; research-use only; no stack traces; no score dumps; no taxonomy names, HMM ids, or length thresholds that teach bypass

## Shared shape

Every refuse is the same shape: what happened → what it means → what to do next (if anything).  
`REVIEW` and `BLOCK` differ only in the middle clause. Do not invent DNA from protein in the copy.

## Strings (wire these)

### `BLOCK` — screened concern

```
This request cannot be fulfilled. The sequence did not pass the pre-compute biosecurity screen, and no structure or design job was started. Research use only; this agent does not support misuse.
```


### `BLOCK` — not configured (COMMEC_BIN missing)

```
This request cannot proceed. The biosecurity screen is not configured on this host (COMMEC_BIN), so annotation was not started.
```

Use this **only** for `commec_missing`. Do not reuse the transient tool-down string — missing binary is a host configuration problem, not a retryable screen failure.

### `BLOCK` — tool down / timeout / unknown (fail-closed; not missing binary)

```
This request cannot proceed. The biosecurity screen did not complete safely, so no structure or design job was started. Please try again shortly, or contact the operator if the problem continues.
```

### `REVIEW` — ambiguous / mixed alphabet

```
This request needs a clearer sequence before any compute can run. Please send an unambiguous DNA or RNA string, or a protein sequence on the amino-acid path. No structure or design job was started.
```

### `REVIEW` — short fragment / partial hit / needs human

```
This request cannot proceed without further review. The sequence is incomplete or inconclusive for an automated screen, and no structure or design job was started. Please lengthen or clarify the input, or ask an operator to review it.
```

## Do not say

- Fragments: “Blocked.” “REVIEW.” “commec fail.”  
- Internals: full filesystem paths, exit codes, score tables, regulated-agent names, exact bp cutoffs. (Exception: name `COMMEC_BIN` / `Bakta` only in the not-configured refuses so operators know what to install.)  
- Soft openers that invite argument: “Sorry, but…” / “Looks risky…”

## Acceptance (copy)

1. Each string is one or two full sentences with terminal punctuation.  
2. Physician or engineer can tell: compute did **not** start; research-use limit holds.  
3. A clinician and an engineer read the same words without a second glossary.
