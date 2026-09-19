# `/measure` copy + board section (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md — research-use; never diagnose from vitals  
**Hard rules:** secret values never echoed; Discord/LM/`/variant`/`/evidence`/`/trials` never see secrets; controlled keys preferred

## Controlled keys (HELP list)

## Curated abbreviations (HELP — ~10 lines)

| Enter | Means | Stored as |
| --- | --- | --- |
| `HR` / `PR` | heart rate | `hr` (bpm) |
| `BP` | blood pressure | `bp_sys` / `bp_dia` (mmHg) |
| `RR` | respiratory rate | `rr` (/min) — if enabled on wire |
| `SpO2` / `O2sat` | oxygen saturation | `spo2` (%) |
| `T` / `Temp` | temperature | `temp_c` (°C; °F converted) |
| `Wt` / `Weight` | weight | `weight_kg` |
| `Ht` / `Height` | height | `height_cm` |
| `Glu` / `BG` / `BGL` | glucose | `glucose_mmol` (mg/dL converted when unit given) |

`BMI` is derived from weight and height when both exist — do not paste BMI as a primary key. Other labs (`Cr`, `eGFR`, `Na`, `K`, `HbA1c`, `Hb`) use `other:<slug>` or mark `secret`. Unknown lines get a helper reply with these examples.

### Key ids

`hr`, `bp_sys`, `bp_dia`, `weight_kg`, `height_cm`, `temp_c`, `spo2`, `glucose_mmol`  
Escape: `other:<slug>`. Free keys require `secret` (or are coerced to `other:` — wire documents which).

## HELP one-liner

```
/measure — Paste patient observations onto the current card (HR, BP, weight_kg=…, optional secret). /measure list shows keys; secret values are never shown. Research use only; not a diagnosis.
```

## Commands (HELP)

```
/measure — Arm the next message as a measurement paste.
/measure <lines> — Parse a short paste immediately.
/measure list — List keys and counts. Secret measures appear only as a count.
/measure clear [key|all] — Clear one key series or all measurements on this card.
```

## Arm

```
Send your measurements in the next message. Examples:
HR 72 bpm
BP 120/80 mmHg
weight_kg=81.2 secret
device: ward_monitor_3

Use controlled keys when you can. Mark sensitive values with secret. Research use only; this bot does not diagnose from measurements.
```

## Saved

```
Saved {n} measurement(s) on this card ({n_secret} secret). Secret values are not shown.
```

## List

**Non-secret lines (example shape):**

```
Measurements on this card:
- hr: 3 reading(s), latest 72 bpm (2026-09-20T08:00)
- bp_sys / bp_dia: 2 reading(s), latest 120 / 80 mmHg
Secret measures on file: 1 (values not shown).
```

**Secrets only / none non-secret:**

```
No non-secret measurements on this card. Secret measures on file: {n} (values not shown).
```

**Empty:**

```
No measurements on this card.
```

## Clear

```
Cleared measurements for key `{key}` on this card.
```

```
Cleared all measurements on this card.
```

## Refuse / help

**No card:**

```
This request cannot proceed. There is no context card. Please /load a case first, then use /measure.
```

**Bad paste / unknown free key (if refuse policy):**

```
This paste could not be parsed. Use lines such as HR 72 bpm, BP 120/80 mmHg, or weight_kg=81.2 secret. Prefer controlled keys (hr, bp_sys, bp_dia, weight_kg, height_cm, temp_c, spo2, glucose_mmol).
```

**Fail / empty after arm:**

```
No measurements were saved. Please send at least one valid line, or /cancel to stop.
```

## `/board` — Measurements section

Insert after Case context (or before Evidence):

```markdown
## Measurements

{measurements_block}
```

### `{measurements_block}`

**With non-secret readings:**

```markdown
- hr: 72 bpm (2026-09-20T08:00Z)
- bp: 120/80 mmHg (2026-09-20T08:00Z)
Secret measures on file: {n} (values not shown).
```

**No non-secret, some secret:**

```markdown
Secret measures on file: {n} (values not shown).
```

**None:**

```markdown
None yet. Paste observations with /measure.
```

Never print secret field values in the board packet.


## v1.1 — soft structure (regex gazetteer)

Accepted synonym / messy one-liner examples (still line-shaped; not free paragraphs):

```
HR was 72
heart rate 72 bpm
BP 120 over 80
blood pressure 120/80
wt 81.2 kg
weight 81.2
temp 37.1 C
SpO2 98%
glucose 5.4 mmol
```

Multi-value on one paste (split on newlines, `;`, or commas):

```
HR 72; BP 120/80; SpO2 98%
```

Idempotent: pasting the same `(ts,key,value,device)` twice does not duplicate.

Pure prose → helper-first coach (see above), then re-arm.

HELP add-on:

```
Messy one-liners are OK when they clearly name a vital (e.g. HR was 72, BP 120 over 80). Free paragraphs are not parsed.
```


## Helper-first (amended)

Structure comes from the user. On a bad or empty paste, **coach and re-arm** — do not NLP a paragraph into vitals.

```
I could not read that as measurements. Please send one fact per line, for example:
HR 72 bpm
BP 120/80 mmHg
weight_kg=81.2 secret

Near-miss wording such as “HR was 72” or “BP 120 over 80” is OK. Free paragraphs are not. Send /cancel to stop.
```

After a partial parse (some lines OK, some not):

```
Saved {n} measurement(s). I could not read {n_bad} line(s). Please resend those as one fact per line (see /help). Secret values are never shown.
```

## Banned

- Diagnosing or dosing from HR/BP/glucose  
- Echoing `secret` values in list, board, captions, or Discord  
- Putting measures into `/variant`, `/evidence`, `/trials`, or LM prompts
