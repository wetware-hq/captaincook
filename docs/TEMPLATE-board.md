# `/board` Markdown template (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — specialty- and subfield-agnostic; clinicians + well-educated patients  
**Hard rules:** research-use only; no diagnosis or treatment orders; never raw biometrics or note bodies; no invented evidence or designs; Harvard refs only under Evidence when present

## Document template

```markdown
# Board packet

This packet assembles the current session stores for a case conference or molecular board discussion. It is for research use only. It is not a clinical record, not a diagnosis, and not treatment advice.

## Case context

- Intent: {card_intent_or_none}
- Gene / variant: {gene_variant_or_none}
- Patient biometrics: {on file|incomplete|none}
- Patient files: {n} on file (contents not shown)

## Measurements

{measurements_block}

## Evidence

{evidence_block}

## Laboratory designs

{lab_block}

## Open questions

{open_questions_block}

## Source note

Assembled from session stores only; nothing was inferred beyond the listed fields.
```

### `{evidence_block}`

Prefer peer-reviewed `/evidence` content already on the card or in `clinic.md`. Keep claim→cite bullets and a bottom Harvard `## References` (or `#### References`) inside this section.

If none:

```markdown
None yet. Run /evidence with a clear clinical or scientific question.
```

Do not paste preprint `/research` here as peer-reviewed evidence. If only preprints exist, say:

```markdown
No peer-reviewed evidence brief on file yet. A preprint research brief is available from /research (not a substitute for /evidence).
```

### `{lab_block}`

Summarise `ligand:` and `binder:` designs by design-id (and short research-use line). Never claim wet-lab readiness.

If none:

```markdown
None yet. Run /design ligand or /design binder after /load (and a structure for binders).
```

### `{open_questions_block}`

Only questions implied by **missing** session fields (e.g. incomplete biometrics, zero evidence, zero designs). Full sentences. Never invent clinical dilemmas.

Example when empty stores:

```markdown
- No peer-reviewed evidence brief is on file yet.
- No in-silico ligand or binder designs are on file yet.
```

If everything present:

```markdown
No open session gaps were detected from the stores listed above.
```

## Telegram caption

```
Board packet for this session. Research use only; not a clinical record.
```


## Commands (HELP)

```
/board — Assemble a Markdown board packet from the current card and patient stores. Research use only; not a clinical record.
/board update — Same as /board (fresh snapshot of current stores; not an incremental merge).
```


### Measurements (from `/measure`)

See `TEMPLATE-measure.md`. Non-secret key–value lines + secret count stub only.

## Refuse

```
This request cannot proceed. There is no context card and no patient on file to assemble a board packet. Please /load a case or /onboard a patient first.
```
