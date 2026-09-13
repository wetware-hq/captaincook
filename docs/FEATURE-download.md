# Feature: `/download` — output files from current card

**Status:** Locked 2026-09-12  
**Owners:** biostrategist (spec) · biomodels (bot wire + durable stash)  
**Depends on:** `/load` context card + `last_run`

## Goal

Call outputs stay **one** photo+caption message.  
`/download` sends **output files** (mmCIF, optional design exports) as a **separate** Telegram message, pulled from the **current context card**.

## Behavior

| Command | Result |
| --- | --- |
| `/download` | `reply_document`(s) for files listed on `context_card.last_run.files` |
| No card | “No card loaded. `/load` … then run a job.” |
| Card but no `last_run` / empty files | “No downloadable files yet. Run `/esm`, `/boltz`, or `/design`→`/confirm` first.” |
| Missing path on disk | Skip with one-line note; send what remains |

## Card fields (extend `last_run`)

```
last_run:
  kind: ...
  at: ...
  interpretation: str
  metrics: dict
  run_id: str | null
  files: [
    { path: str, filename: str, kind: cif | design_csv | png_archive | other }
  ]
```

## Stash rules (critical)

Today CIF is often `_safe_unlink`’d after the photo. For `/download`:

1. On success, **copy** artifacts to a durable session dir, e.g.  
   `boltz-experiments/session_<chat_id>/run_<timestamp>/`
2. Record those paths on `last_run.files`
3. **Do not** unlink durable copies until `/load clear`, new `/load`, TTL (~24h), or successful replace by a newer run
4. Temp render PNGs can still be deleted after send; durable stash keeps CIF (+ optional SMILES table `.csv` for design)

## What to include per kind

| Run kind | Files |
| --- | --- |
| `esm_fold` / `boltz_structure` / `boltz_binding` | best `.cif` |
| `small_molecule_design` | best `.cif` if present; `candidates.csv` (smiles + scores) |

## Message shape

Separate from the result photo:

```
Downloads (from current card)
• boltz.cif
• candidates.csv   # design only
```
Then one `reply_document` per file (or a single `.zip` if >2 files — v1.1; v1 = individual docs).

## Acceptance

1. `/load` → `/boltz <seq or bare>` → photo message only → `/download` → CIF document message.  
2. `/load` → `/design`→`/confirm` → photo → `/download` → CIF and/or CSV.  
3. `/download` with no card / no files → clear errors.  
4. Result call path still **no** CIF in the success turn.

## Split

- **biomodels:** durable copy, `last_run.files`, `cmd_download`, HELP, stop unlinking stashed paths  
- **biostrategist:** this spec  
