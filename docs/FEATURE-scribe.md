# Feature: `/scribe` — biomedical meeting minutes (unlinked)

**Status:** Locked 2026-09-14 (Minimum Idiot Index)  
**Owners:** biostrategist (spec) · biomodels (wire) · biolang (template + voice)  
**Depends on:** Telegram document send; optional chat-completions endpoint for organisation  
**Out of scope v1:** Link to context card / patient / notes; Discord mirror; RAG; diagnosis; EHR export

## Goal

Take free-text meeting notes (or a transcript paste) and return **one structured Markdown document** of biomedical meeting minutes. Prose: clear, concise, **complete sentences**, readable by **clinicians and well-educated patients**. Research-use / documentation aid only — not a clinical record of truth and not advice.

## Card linkage (user lock)

**Unlinked for now.** `/scribe` does **not** read or write the context card, biometric secrets, or `patient_files`. No `/load` required.

## Minimum Idiot Index

| Choice | Lock |
| --- | --- |
| Input | `/scribe` arms “next message is source text”, **or** `/scribe <text>` if under Telegram length limits. Prefer next-message for long pastes. |
| Cap | Source text ≤ **12_000** chars (refuse oversize with clear hint). |
| Engine | One OpenAI-compatible chat Completions URL via env (`SCRIBE_LLM_URL` + `SCRIBE_LLM_KEY` optional + `SCRIBE_LLM_MODEL`). If unset/down → fail-closed refuse (biolang). No second model. |
| Prompt | Fixed system prompt (biolang): organise only; do not invent attendees, decisions, or data absent from the source; flag uncertainty; complete sentences; dual clinician/patient clarity. |
| Output | One `.md` → `reply_document`; caption = one-line TLDR + research-use notice. |
| Privacy | Do not attach card secrets/files. Do not log full source at INFO. |
| Discord | Off. |

## Fixed Markdown skeleton (biolang may polish titles)

```markdown
# Meeting minutes

{one-paragraph research-use / not-a-legal-record disclaimer}

## Summary
…

## Decisions
- …

## Action items
- {who / what / when if present in source; else omit who}

## Discussion
…

## Open questions
- …

## Source note
Organised from user-supplied text; items not stated in the source were not added.
```

Omit empty sections rather than writing “None.” if the source has no material — except always keep **Summary** and **Source note**.

## Commands

| Command | Behavior |
| --- | --- |
| `/scribe` | Arm next plain message as source. |
| `/scribe <text>` | Organise immediately when short enough. |
| `/cancel` | Clear armed scribe state. |

## Acceptance

1. Unlinked: works with no card loaded.  
2. Paste messy notes → structured `.md` with complete sentences; no invented decisions.  
3. Missing LLM config → refuse, no fake minutes.  
4. Card patient/notes unchanged after `/scribe`.  
5. Voice: clinician + well-educated patient readable (biolang sign-off).

## Split

- Spec — **biostrategist**  
- Handler + LLM client + send document — **biomodels**  
- System prompt, section titles, caption, refuse — **biolang** (`TEMPLATE-scribe.md` / `COPY-scribe.md`)
