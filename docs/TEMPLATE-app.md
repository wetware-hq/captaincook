# `/app` copy (locked) — case-conference packet + live view

**Owner:** biolang  
**Cadence:** docs/VOICE.md + TEMPLATE-board.md (same sections/redaction)  
**Rename:** `/app` primary; `/board` and `/board update` / `/app update` = strict aliases (one release)

## HELP one-liners

```
/app — Assemble a Markdown case-conference packet from the current card and patient stores. Optional short-lived web view when configured. Research use only; not a clinical record.
/app update — Same as /app (fresh snapshot; not an incremental merge).
/board — Alias of /app for one release.
/board update — Alias of /app for one release.
```

## Markdown packet

Reuse **TEMPLATE-board.md** body verbatim (title may say `# Case conference packet` or keep `# Board packet` during the alias window — prefer):

```markdown
# Case conference packet
```

All section rules, Measurements redaction, Evidence Harvard, Laboratory designs, Open questions, and Source note are unchanged from TEMPLATE-board.

## Caption (Telegram)

**MD only:**

```
Case conference packet for this session. Research use only; not a clinical record.
```

**MD + live view link:**

```
Case conference packet for this session. Research use only; not a clinical record. Open live view (short-lived): {url}
```

Never put secret values or raw biometrics in the caption or URL.

## Live view page chrome (copy)

Top banner (serif, plain):

```
Research use only. This page is a short-lived case-conference view. It is not a clinical record, not a diagnosis, and not treatment advice. Secret measurements and biometric values are omitted.
```

Footer:

```
Generated from the Telegram session stores. This shared link expires (default 7 days; maximum 30). Do not forward if the page could identify a patient. Not a medical record.
```

Chart figure captions (under each Vega-Lite chart):

```
Figure. {key} over time (non-secret session measurements only).
```

## Fail-closed (live view)

```
The Markdown packet is ready. A live web view could not be created because hosting is not configured or the deploy failed. Secret values were not uploaded. You can still use the document above.
```

## Refuse (no card / no patient)

Same as TEMPLATE-board refuse (load or onboard first) — substitute “case conference packet” for “board packet” if desired:

```
This request cannot proceed. There is no context card and no patient on file to assemble a case conference packet. Please /load a case or /onboard a patient first.
```




## Style guide (live view + packet chrome)

- **Scan first, prose second.** Prefer charts, tables, and anchors so a colleague can grok the case in one scroll.  
- When words are required: **complete short sentences**, clear and concise — never fragments like “API error” or “BP ok.”  
- Section titles only; no paragraph intros. If a section needs a sentence, **one max**.  
- Evidence / Laboratory: **≤3 claim→cite bullets** + Harvard list at the section bottom — not the full brief dump.  
- Empty: `None yet.`  
- Telegram caption: one or two sentences + link + expiry; the page carries the detail.

## Dual-audience merge (clinic.md + lab.ipynb)

One page, two headings — not two apps:

```markdown
## Clinical
{evidence peer-reviewed; meeting minutes; notes stubs/counts — from clinic.md / board projection}

## Laboratory
{preprint research; ligand/binder design summaries + image refs — from lab.ipynb; CIF/FASTA via download only}
```

Top anchor nav (minimal): `Clinical` · `Laboratory` · `Measurements`.

**Tone fence:** peer-reviewed evidence stays under Clinical; preprint `/research` stays under Laboratory — never upgrade preprint language into peer-reviewed voice.

Empty sections: honest “None yet.”

## Lifetime / sharing (amended)

- Default live-view lifetime: **7 days** (colleague share for discussion). Hard max **30 days**.  
- Regenerating `/app` refreshes or rotates the link; `/app revoke` ends sharing early.  
- Caption may include the expiry day. Optional access code in the caption later — never in the URL path.

**Caption with link:**

```
Case conference packet for this session. Research use only; not a clinical record. Open live view (shared link, expires {date}): {url}
```

**Revoke confirm:**

```
The live view link has been revoked. The Markdown packet in this chat is unchanged. Secret values were never in the page.
```

**Expired / revoked open:**

```
This live view has expired or was revoked. Ask the operator to run /app again for a fresh short-lived link. Research use only; not a clinical record.
```

## Banned

- “Dashboard”, diagnosis, or dosing language  
- Secret measure values in HTML, JSON embeds, query strings, or Discord  
- Claiming the live view is permanent or clinical-grade EHR
