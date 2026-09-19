# Feature: unstructured inputs into `/measure` (staged)

**Status:** Locked 2026-09-20 — **greenlight v1.1 only**  
**Owners:** biostrategist · biomodels · biolang · bioresearch · bioplatform  
**Depends on:** FEATURE-measure.md (v1 line-shaped live)

## Stages

| Stage | Scope | Status |
| --- | --- | --- |
| **v1** | Line-shaped paste only | **Live** (`74a273f`) |
| **v1.1** | Soft structure: regex gazetteer, no LLM | **Ship next** |
| **v1.2** | Opt-in LLM `/measure free` extract | **Dropped from critical path** |
| **v1.3** | `category:` + append-only + time-series projections | Hold |


## Helper-first UX (locked 2026-09-20 — user)

**Prefer helper replies over NLP.** Structure comes from the user; the bot coaches.

| Case | Behavior |
| --- | --- |
| Bad / messy / pure prose paste | Short **helper** (not silent coerce): say it couldn’t be read as measurements; show 3 examples + `secret` tip + `/cancel`; **re-arm** paste |
| Near-miss synonym line (“HR was 72”) | Optional cheap **v1.1 gazetteer** only — no LLM |
| Zero parses | Helper + re-arm; never invent rows |
| v1.2 LLM `/measure free` | **Dropped from critical path** — do not ship |

HELP and refuse copy (biolang) own the helper examples.

## v1.1 (locked)

- Gazetteer synonyms → controlled keys: e.g. “HR was 72”, “BP 120 over 80”, “wt 81.2 kg”, unit synonyms  
- Split on `;` / newlines / commas  
- Zero parses → refuse (fail-closed); unknown → `other:<slug>`  
- Idempotent hash `(ts,key,value,device)` skip double-paste  
- Still **no** free-paragraph NLP; prefer helper coach over aggressive gazetteer  
- HELP examples for synonym lines (biolang)

## v1.2 (hold)

- Only if line parse yields 0 **and** user used `/measure free`  
- Bounded extract → proposed rows → **`/confirm` required** before write  
- Default `secret` on weight/identifiers  
- Never auto-write; never feed extract into `/variant`/`/evidence`/`/trials`; never Discord

## v1.3 (hold)

- `category:vitals|labs|device|other`  
- Append-only log; board/list = last-N / last-per-key  
- `search.json` `measure:<category>:<key>`

## Out of scope

Silent EHR ingest; diagnosis from vitals; free-paragraph auto-commit.

## Acceptance (v1.1)

1. “HR was 72” / “BP 120 over 80” → `hr` / `bp_sys`+`bp_dia`  
2. Pure prose paragraph → refuse  
3. Double-paste same hash → no duplicate row  

## Split

- Spec — biostrategist  
- Gazetteer + hash — biomodels  
- HELP examples — biolang  
