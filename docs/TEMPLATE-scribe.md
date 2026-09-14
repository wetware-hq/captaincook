# `/scribe` Markdown template (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — complete sentences; clinician + well-educated patient  
**Unlinked:** never read or write context card, biometric secrets, or patient files

## Document template

```markdown
# Meeting minutes

This document organises user-supplied meeting text for research and documentation use only. It is not a legal medical record and is not clinical advice.

## Summary

{summary_paragraph}

## Decisions

{decisions_block}

## Action items

{actions_block}

## Discussion

{discussion_block}

## Open questions

{questions_block}

## Source note

Organised from user-supplied text; items not stated in the source were not added.
```

### Section rules

1. **Always** keep Summary and Source note.  
2. Omit Decisions, Action items, Discussion, or Open questions entirely when the source has no material for that section — do not write “None.”  
3. Full sentences only. No invented attendees, decisions, dates, doses, or results.  
4. If the source is unclear, say so once in Summary or Open questions.  
5. Action items: `{who} — {what} — {when}` only when those parts appear in the source; otherwise `{what}` alone.

## System prompt (fixed)

```
You organise biomedical meeting notes into Markdown. Use only information present in the source text. Do not invent attendees, decisions, action items, clinical conclusions, or data. Write clear, complete sentences that a clinician and a well-educated patient can both understand. Prefer concise paragraphs and short bullets. Follow the user’s section skeleton exactly. Research-use / documentation aid only — not clinical advice and not a legal medical record. If something is uncertain or missing, state that plainly.
```

## Captions

**Success:** `Meeting minutes organised from your text. Research use only; not a clinical record.`

## Refuse / help

**Arm:** `Send the meeting notes or transcript in your next message. /scribe does not use the context card, biometric secrets, or patient files.`

**Cancel:** `Scribe cancelled. No minutes were written.`

**Missing / empty source:** `Please provide meeting notes or a transcript. Example: /scribe then paste the text, or /scribe followed by a short note.`

**Too long:** `This text is too long for one pass. Please shorten it to 12000 characters or fewer and try again.`

**LLM unset / down (fail-closed):** `This request cannot proceed. The scribe service is not configured or did not respond safely, so no minutes were written. Please try again shortly or contact the operator.`
