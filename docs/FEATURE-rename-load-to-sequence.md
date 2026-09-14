# Feature: command name for context card

**Status:** Locked 2026-09-14 · **REVERTED** — `/load` is primary again  
**Owners:** biostrategist · biomodels · biolang

## Current lock (user: REVERT back to /load)

| Command | Role |
| --- | --- |
| `/load <nl>` `/load` `/load clear` | **Primary** — NL → context card (unchanged behaviour) |
| `/sequence` | **Withdrawn** — one-line stub only if BotFather still lists it (“use `/load`”), then same path or refuse |

HELP, README, COPY, FEATURE cross-refs: **`/load` only** as the user-facing name.

## History

Briefly renamed to `/sequence` (2026-09-14); user reverted same day. Do not keep dual first-class commands.

## Acceptance

1. HELP lists `/load`, not `/sequence` as primary.  
2. `/load find me an inhibitor for KRAS G12C GDP` builds the card.  
3. `/sequence` if present only redirects to `/load`.  
4. Fingerprint / sorter / lit consumers unchanged.
