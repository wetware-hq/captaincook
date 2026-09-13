# Feature: `/load` — NL → formal context card

**Status:** Locked 2026-09-12 (user: Lock /load context card MVP)  
**Owners:** biostrategist (schema/plan) · biomodels (bot `/load` + consumers)  
**Reuse:** `intent.py`, `targets.py`

## Goal

`/load <natural language>` parses a research request into a **formal context CARD** stored in the Telegram session. Later folding / binding / design commands read that card instead of requiring a pasted sequence every time.

Example:
```
/load find me an inhibitor for KRAS G12C in the GDP state, covalent, 10 molecules
```
→ card shown in chat → user runs `/design` or `/boltz` / `/esm` using the card’s sequence & flags.

## Non-goals

- Silently starting GPU jobs from `/load` (no Boltz/Biohub call on load)
- LLM parsing in v1 (rule-based, same as intent.py)
- Replacing `/design <sequence>` — both paths remain; card is optional context

## Context card schema (formal)

```
context_card:
  version: 1
  raw_text: str
  intent: fold | structure_binding | small_molecule_design | unspecified
  target:
    gene: str | null          # e.g. KRAS
    variant: WT|G12C|G12D|G12V | null
    uniprot: str | null       # e.g. P01116-2
    sequence: str | null      # resolved AA string when gene curated
    sequence_source: cached_uniprot | user_paste | missing
  ligand:
    smiles: str | null        # if user supplied a known ligand
  design:
    state: GDP|GTP|null
    covalent: bool|null
    n_designs: int            # floored at 10, cap 100
    n_designs_clamped_from: int|null
    chemical_space: enamine_real
    max_usd: float            # default 0.50
  pocket_residues: map|null   # optional, shown not auto-applied until design confirm
  reference_ligands: [smiles]|null
  missing_fields: [str]       # explicit gaps
  created_at: iso8601
```

## Command behavior

| Command | Behavior |
| --- | --- |
| `/load <nl…>` | Parse → resolve sequence if gene curated → reply with formatted card → stash `context.user_data["context_card"]` |
| `/load` (no args) | Show current card or “no card loaded” |
| `/load clear` | Drop card |
| `/esm` / `/boltz` / `/design` with **no** sequence arg | If card has `sequence`, use it; else existing usage error |
| `/design` with card | Prefill n / covalent / pending confirm from card; still require `/confirm` before spend |
| Explicit sequence arg | **Overrides** card for that one job (card unchanged) |

## Card display (chat text)

```
Context card
• intent: small_molecule_design
• target: KRAS G12C  (P01116-2, 169 aa)
• sequence: MTEY…KEK  (source: cached_uniprot)
• state: GDP
• covalent: true
• n_designs: 10  (API min; ~US$0.25)
• chemical_space: enamine_real
• missing: (none)
Next: /design   or   /boltz   or   /esm
/load clear to drop
```

No GPU on `/load`. Research-use disclaimer once on card.

## Implementation

| File | Change |
| --- | --- |
| `src/context_card.py` *(new)* | `ContextCard` dataclass, `parse_load_text`, `format_card`, serialize to user_data |
| `src/intent.py` | Generalize extractors for `/load` (or call from context_card) |
| `src/targets.py` | `resolve()` as today |
| `src/bot.py` | `cmd_load`; HELP; `/esm`/`/boltz`/`/design` optional-sequence-from-card |
| `README.md` | Document `/load` |

## Acceptance

1. `/load find inhibitor for KRAS G12C GDP covalent` → card with sequence + fields; no API spend.  
2. `/design` with no args after load → confirm flow using card sequence/n.  
3. `/boltz` with no args after load → structure on card sequence (+ PNG).  
4. `/load clear` → subsequent bare `/design` asks for sequence again.  
5. Missing gene → card with `sequence_source: missing` and clear missing_fields (no invented sequence).

## Split

- **biostrategist:** schema + FEATURE (this doc)  
- **biomodels:** `/load` handler, stash, wire consumers, poller  
