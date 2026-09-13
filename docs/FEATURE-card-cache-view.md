# Feature: card memory + `/view`

**Status:** Locked 2026-09-13  
**Owners:** biostrategist (spec) · biomodels (wire)  
**Depends on:** `/load` context card, `last_run` (caption + files + durable PNG if stashed)

## Goal

If a **new** `/load` card matches a **previously completed** card (same formal specifications), tell the user and offer `/view` to return that earlier result (clinical blurb + image) without re-running GPU jobs.

## Match key (canonical)

Hash these fields only (ignore `raw_text`, `created_at`, `last_run`, `missing_fields` order):

```
intent
gene
variant
sequence          # resolved AA string
sequence_source
smiles            # ligand if any
state
covalent
n_designs
chemical_space
```

Normalise: uppercase gene/variant; sequence uppercase no whitespace; `covalent` tri-state as true/false/null; default n_designs compared after clamp.

Two cards **match** iff the SHA-256 of the canonical JSON is equal.

## Cache store (per Telegram user / chat)

```
user_data["card_cache"][fingerprint] = {
  card: <ContextCard dict without last_run or with snapshot>,
  last_run: { kind, at, interpretation, metrics, run_id, files, result_png? },
  fingerprint: str,
}
```

- Write/update cache **when a run succeeds** and a card is loaded (same moment as `attach_last_run`).
- Prefer also stashing the **result PNG** path in `last_run` (or `result_png`) so `/view` can `reply_photo` without re-render. If PNG missing, re-render from CIF when possible; for design grid, re-render from candidates.csv / stored candidate list if present.
- Cap cache size (e.g. 20 fingerprints); LRU eviction. TTL align with session stash (~24h).

## `/load` behaviour

1. Parse new card as today.  
2. Compute fingerprint.  
3. If fingerprint ∈ cache **and** `last_run` has a usable result:  
   - Save the new card as current (as today).  
   - Reply with the card **plus** a clear offer, e.g.  
     “This request matches a completed card from {when}. Send /view to see that earlier result (image and description), or continue with /esm, /boltz, or /design to run again.”  
4. If no match: current behaviour only.

Do **not** auto-show the old result; require `/view`.

## `/view`

| Case | Response |
| --- | --- |
| Current card fingerprint hits cache with result | One message: `reply_photo(caption=stored interpretation)` — same single-message shape as a live run |
| No card | “No context card is loaded…” |
| Card but no cached result | “No stored result for this card yet. Please run a job first.” |
| Cached files missing on disk | Explain and offer to re-run |

`/view` does **not** spend GPU when the PNG (or rebuildable artifacts) exist.

## Acceptance

1. `/load` KRAS G12C… → run `/design`→`/confirm` → later `/load` same intent → offer `/view`.  
2. `/view` returns one photo+caption matching the prior clinical blurb.  
3. Different variant (G12D) does **not** match.  
4. Live run outputs remain single-message; `/download` unchanged.

## Split

- `context_card.fingerprint(card)` + cache helpers — either agent  
- `cmd_view`, `/load` match branch, stash PNG on success — **biomodels**  
- Spec — **biostrategist**

## Amendment (user)

`/view` returns old results as a **consolidated message (blurb + image) as usual** — one `reply_photo` with clinical caption. Same packaging as a live call output. No separate Details message.

## Amendment — session-only storage (user)

Cache **only within the same Telegram chat session**.

Minimum design:
- `context.user_data["card_cache"]` only (per-chat by PTB)
- Reuse `session_<chat_id>/` files for PNG/CIF; do not add a separate cache database
- Small LRU (≤5). No cross-restart persistence for `/view`
- Poller restart clears in-memory cache (expected)

