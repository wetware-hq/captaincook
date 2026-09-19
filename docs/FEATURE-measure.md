# Feature: `/measure` — paste-friendly patient observations on the card

**Status:** Locked 2026-09-20 (Minimum Idiot Index)  
**Owners:** biostrategist · biomodels · biolang · bioresearch · bioplatform (no Discord)  
**Depends on:** context card; onboard-style secret handling; `search.json`

## Goal

Generic, secure, **copy/paste** entry for hospital-hardware or personal biometric-style observations onto the **current card**, searchable in-session for non-secret keys. Research-use only. No diagnosis.

## Card shape (extend, don’t fork)

```
card.measurements[] = {
  ts: iso8601,
  key: str,           # controlled list or other:* 
  value: str|number,
  unit: str|null,
  device: str|null,
  secret: bool,
  source: "paste"|"hardware"|…
}
```

## Controlled keys (v1)

`hr`, `bp_sys`, `bp_dia`, `weight_kg`, `height_cm`, `temp_c`, `spo2`, `glucose_mmol`  
Escape: `other:<slug>` or free key **only** with `secret` flag (or force into `other:`).

## Paste formats (all accepted)

```
HR 72 bpm
BP 120/80 mmHg
weight_kg=81.2 secret
device: ward_monitor_3
2026-09-20T08:00 glucose_mmol=5.4
```

TSV/CSV one-shot (optional header). `secret` / `secret=true` marks vaulted fields.

## Commands

| Command | Behavior |
| --- | --- |
| `/measure` | Arm next message as paste |
| `/measure <lines>` | Parse immediately if short |
| `/measure list` | Keys + counts; secrets → “N secret measures on file” only |
| `/measure clear [key\|all]` | Drop matching / all measures |

## Security

- **Secret** measures: never in `/load`, `/board`, captions, HELP dumps, Discord, `/variant`/`/evidence`/`/trials`, or any LM prompt — only counts.  
- **Non-secret:** index `search.json` as `measure:<key>`; `/board` may show tidy key–value lines.  
- Discord: never mirror measure packets.

## Board

`/board` / `/board update` include a **Measurements** section: non-secret lines + secret count stub.

## Acceptance

1. Paste HR/BP/`weight_kg=… secret` → list redacts secret value.  
2. `/board` shows non-secret HR; secret count only.  
3. Unknown free key without secret → refuse or coerce to `other:` (biomodels pick one; document). **Picked: coerce to `other:<slug>`.**
**Wire decision (biomodels, 2026-09-20):** unknown free key without `secret` → **coerce to `other:<slug>`** (not hard refuse). Free keys with `secret` are kept as the slug. Documented in `src/measure.py` module docstring.
  
4. Clear key removes only that series.

## Split

- Spec — biostrategist  
- Parser + card array + search index — biomodels  
- TEMPLATE-measure + board section — biolang  
- Discord stay dark — bioplatform  
