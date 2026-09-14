# Feature: fail-closed `commec` pre-GPU biosecurity gate

**Status:** Locked 2026-09-13 · amended same day (thin `--skip-tx` pack; taxonomy BLOCK deferred)  
**Owners:** biostrategist (spec) · biomodels (wire) · biosecurity (threat model) · bioresearch (tool shortlist)  
**Depends on:** slash handlers for `/esm` `/boltz` `/design` `/confirm`; `/load` sequence resolution  
**Out of scope v1:** SeqScreen-Nano clinic streaming (#3); AA function/SoC production BLOCK (#1 — stub only)

## Goal

Before any GPU or paid API call, classify the request sequence with a cook-shaped decision: **`PASS` | `REVIEW` | `BLOCK`**.  
Engineering bar is **Minimum Idiot Index**: one obvious alphabet path, one fail-closed default, no silent translation, no invented DNA from protein.

## Alphabet preference (user lock)

Attempt a screen on **every** sequence-bearing request when possible, in this priority:

1. **DNA** (A/C/G/T + unambiguous IUPAC DNA) → run IBBIS `commec`  
2. **RNA** (A/C/G/U + unambiguous IUPAC RNA) → run `commec` (RNA mode / transcribed policy as tool supports)  
3. **Protein** (standard AA alphabet) → **do not** call `commec`; do not reverse-translate. v1 outcome: **`PASS` with `screen=skipped_aa`** logged, plus optional later #1 SoC stub (never BLOCK on weak homology alone)

| Input | Action |
| --- | --- |
| Unambiguous DNA | `commec` → map flags |
| Unambiguous RNA | `commec` → map flags |
| Unambiguous AA (today’s `/esm` `/boltz` `/design` path) | No `commec`; proceed under AA policy above |
| Mixed / ambiguous / cannot classify | **`REVIEW`** — never guess DNA from AA or strip ambiguity silently |
| Empty / missing sequence | Existing validation error (no screen) |

## Decision contract

| Outcome | Meaning | User-visible | GPU / Boltz / Biohub |
| --- | --- | --- | --- |
| `PASS` | Clear / low-concern (or AA skip under v1 policy) | Continue normal flow | Allowed |
| `REVIEW` | Needs human judgment | Short refuse caption; no compute | **Blocked** |
| `BLOCK` | High concern or tool failure | Short refuse caption; no compute | **Blocked** |

### Install pack (v1)

- **Thin open packs only:** `commec screen … --skip-tx` with biorisk / low-concern DBs from [commec-databases](https://github.com/ibbis-bio/commec-databases) (MIT). Local only; no sequence upload.
- **Full local NCBI taxonomy** (`nr` / `core_nt`) is a later ops upgrade — not a v1 ship blocker.
- Documented gap: without taxonomy, `commec` cannot taxonomically clear a sequence.

### `commec` flag → outcome (DNA/RNA only, `--skip-tx`)

- Explicit clear / low-concern **from open packs / biorisk-HMM** → **`PASS`**
- Biorisk-HMM / open-pack SoC hit → **`BLOCK`**
- High-concern **taxonomy** hit → **deferred** until full NCBI install (v1: never required for `BLOCK`)
- When taxonomy is skipped and there is **no** HMM/open-pack clear → prefer **`REVIEW`** over **`PASS`** (cannot taxonomically clear ≠ full clear)
- Partial hit, ambiguous bases, length below policy (~50–150 bp), or tool “needs human” → **`REVIEW`**
- Unknown result, timeout, crash, missing binary, or dependency down → **`BLOCK`** (fail-closed)

### Minimum Idiot Index rules (non-negotiable)

1. **One classifier:** `classify_alphabet(seq) → dna | rna | aa | ambiguous`. No second heuristic layer in v1.  
2. **No invented sequence:** never reverse-translate AA to call `commec`.  
3. **Fail closed:** any doubt about tool health → `BLOCK`, not `PASS`.  
4. **Same refuse shape** for `REVIEW` and `BLOCK`: one full-sentence research-use refuse (VOICE.md); no stack traces; no score dumps that teach bypass.  
5. **Gate once per spend path:** `/design` screens at confirm-time (and at `/design` if sequence already known); bare `/esm` `/boltz` screen before API; `/load` may classify early but must not burn GPU.

## Hook points (biomodels)

```
before Biohub/Boltz/design start:
  decision = bioscreen.gate(sequence)
  if decision in (REVIEW, BLOCK): reply refuse; return
  else: existing path
```

Suggested module: `src/bioscreen.py` (alphabet classify + `commec` wrapper + decision enum).  
Config: `COMMEC_BIN`, always pass `--skip-tx` in v1, timeout seconds; default timeout → `BLOCK`.

## Acceptance

1. DNA SoC-like fixture → `BLOCK`, zero API spend.  
2. Clear short DNA under length policy → `REVIEW`, zero API spend.  
3. Benign DNA fixture → `PASS`, existing fold/design path unchanged.  
4. KRAS AA `/design` path → no `commec` call; still runs after confirm (v1 AA skip).  
5. Mixed alphabet string → `REVIEW`, no `commec` DNA guess.  
6. `commec` killed / timed out → `BLOCK`.  
7. Captions remain Proper English full sentences; research-use only.

## Follow-ons (not this PR)

- **#1 stub:** AA SoC dual-signal (curated function hit **and** SoC-family support above calibrated FP budget) may later flip AA from skip/`REVIEW` → `BLOCK`. Single weak homology stays `REVIEW`.  
- **Full taxonomy:** local NCBI + drop `--skip-tx`; restore taxonomy → `BLOCK` in the flag map.
- **#3:** SeqScreen-Nano clinic streaming = separate product, not poller handlers.

## Split

- Spec — **biostrategist** (this file)  
- Threat map — **biosecurity** (signed 2026-09-13)  
- Wire `bioscreen` + handler hooks — **biomodels**  
- Voice of refuse strings — **biolang** (`docs/REFUSE-bioscreen.md`; ping if copy drifts)
