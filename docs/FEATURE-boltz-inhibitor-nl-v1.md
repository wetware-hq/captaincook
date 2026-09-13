# Feature: `/boltz find me an inhibitor for KRAS` (v1)

> **UX update 2026-09-12:** NL on `/boltz` was dropped per user. Live path is now `/design <protein-sequence> [n]` → estimate → `/confirm`. `/boltz` is structure/binding only. `intent.py` / `targets.py` remain as helpers for sequence resolve.


**Status:** Locked 2026-09-12 (user + biomodels-aligned)  
**Owners:** biomodels → `BoltzClient` design/ADME wrapper; biostrategist → intent, confirm UX, target resolve plan  
**Repo:** `telegram-biomodel-bot`

## Cost (verified by biomodels)

- **US$0.025 per molecule**. API floor **10 molecules = US$0.25**.
- Requested n&lt;10 is clamped to 10; confirm UX must show “API minimum 10 — US$0.25”.
- Default n=10; 20 molecules = US$0.50 (hits typical max_usd).
- ADME Tier-1 fields ride on each design result (no extra fee).
- `chemical_space`: `enamine_real` | `none` only.

## Goal

Natural-language inhibitor requests on `/boltz` run **Boltz small-molecule design** against a resolved KRAS (or other curated) target, after an explicit **confirm card**. Not structure-only fold. Not clinical claims.

## Non-goals (v1)

- Library virtual screen (no curated library yet)
- Protein binder / antibody design
- Covalent-warhead enumeration libraries
- Silent defaults for bare “KRAS” → G12C
- Invented sequences
- Synthesis routes, ordering, wet-lab protocols
- Pathogen / reverse-genetics / GoF (existing refusals)

## Existing behavior (preserve)

| Input | Path |
| --- | --- |
| `/boltz <AA-sequence>` | `structure_and_binding` structure-only |
| `/boltz <AA-sequence> <smiles>` | structure + ligand–protein binding |

## New behavior

| Input | Path |
| --- | --- |
| `/boltz find me an inhibitor for KRAS` | NL → confirm card → `small-molecule:design` (+ optional ADME) |
| `/boltz find inhibitors for KRAS G12C GDP covalent` | Same; pre-fill parsed fields |

### Confirm card fields

```
intent: small_molecule_design
target: KRAS
variant: ? | WT | G12C | G12D | G12V   # ask if missing; keep if user said G12C
state: GDP | GTP | unspecified          # ask if missing for KRAS
covalent: true | false | unspecified    # ask if missing; G12C often true, still ask
n_designs: 10                            # hard min 10 / cap 100
max_usd: 0.50
sequence_source: uniprot:P01116[+mut] | user_paste | missing
sequence: <resolved AA string or empty>
```

Flow:

1. Parse NL → partial card  
2. If `sequence` missing → resolve UniProt P01116 isoform + apply mutation, or ask once for paste  
3. If `variant` / `state` / `covalent` unspecified → ask (Telegram inline buttons or numbered reply)  
4. Echo cost/latency estimate + card → user confirms  
5. Run design (+ optional ADME)  
6. Reply: ranked table + best CIF + research-use disclaimer  

## Module plan

### `src/intent.py` (new)

Rule-based (no LLM required for v1):

- Detect design intent: keywords `inhibitor`, `binder`, `ligand design`, `find me`, `design … for`
- Extract gene/target token (`KRAS`, `k-ras`, etc.)
- Extract variant regex: `G12[CDV]`, `WT`, `wild[- ]?type`
- Extract state: `GDP`, `GTP`
- Extract covalent: `covalent`, `non[- ]?covalent`, `acrylamide`
- If first arg validates as protein sequence → return `structure_mode` (existing path)

### `src/targets.py` (new)

- Curated entries: gene → UniProt accession, default isoform length (KRAS 1–169), known variants  
- `resolve_sequence(gene, variant) -> str` via UniProt REST (or cached FASTA in-repo for KRAS)  
- Optional pocket presets **only after confirm** (Switch-II for G12C/GDP); never apply silently without showing on card  
- Optional `reference_ligands` SMILES for pocket finding (e.g. sotorasib-class) listed on card  

### `src/boltz_client.py` (biomodels)

Add:

```python
def design_small_molecules(
    self,
    sequence: str,
    *,
    num_molecules: int = 10,
    chemical_space: str = "enamine_real",
    pocket_residues: dict[str, list[int]] | None = None,
    reference_ligands: list[str] | None = None,
    constraints: list[dict] | None = None,
    bonds: list[dict] | None = None,
) -> DesignResult: ...
```

`DesignResult`: ranked candidates with `smiles`, `binding_confidence`, `optimization_score`, `structure_confidence`, optional `cif_path`, run id.

Optional: `predict_adme(smiles_list)` if API available; attach flags to rows.

### `src/bot.py`

- Branch in `cmd_boltz`: sequence path vs NL design path  
- ConversationHandler or bot_data pending-confirm per `chat_id` for multi-step ask/confirm  
- Update `HELP_TEXT`  
- Keep `REFUSAL_KEYWORDS`  

### Docs / README

Document NL examples, confirm flow, cost disclaimer, research-use only.

## Telegram UX sketch

```
Parsed design request:
• target: KRAS
• variant: (pick) WT | G12C | G12D | G12V
• state: (pick) GDP | GTP
• covalent: (pick) yes | no
• n_designs: 10 | max_usd: ~0.50
• sequence: UniProt P01116 … (169 aa) [show first/last 10]

Reply /confirm to run, /cancel to abort.
```

After run:

```
Boltz small-molecule design — KRAS G12C · GDP · n=10
#  SMILES  binding_confidence  optimization_score  ADME
1  ...     0.82                0.71                …
…
Research-use only. In silico candidates — not validated inhibitors.
[+ best.cif]
```

## Acceptance tests

1. `/boltz MKTIIALSYIFCLVFA` — still structure-only (no design)  
2. `/boltz find me an inhibitor for KRAS` — confirm card; asks variant/state/covalent; no GPU until confirm  
3. `/boltz find inhibitor for KRAS G12C` — variant pre-filled; still ask state/covalent if missing  
4. Confirm with resolved sequence → design returns ≥1 ranked SMILES or clear API error  
5. Refusal keywords still refuse  
6. `n_designs` floored at 10 (API min)  

## Risks

| Risk | Mitigation |
| --- | --- |
| Design cost >> structure smoke (~$0.025) | Confirm card + `max_usd`; start with n=10 |
| Telegram SMILES `O`→`0` | Prefer file/CSV attach for results; monospace; warn |
| UniProt downtime | Ship cached KRAS FASTA fallback |
| SDK method names drift | biomodels verifies against `boltz-api` in bot venv |
| Overclaiming | Fixed disclaimer string on every design reply |

## Rollout

1. biomodels lands `design_small_molecules` (+ smoke with tiny n / test key if available)  
2. Add `intent.py` + `targets.py` + confirm conversation  
3. Wire `cmd_boltz` branch  
4. Manual Telegram E2E on allowlisted user  
5. README + help text  

## Open follow-ups (v1.1)

- Library screen once a library exists  
- Live UniProt for non-KRAS genes  
- Covalent bond constraints in API payload  
- Stricter allowlist before billing design runs broadly

## Smoke (biomodels, 2026-09-12)

- Run `sm_des_v2_AqoK43y40n3GrPyvJPFf`, n=10, estimate **US$0.25** matched.
- Wall time **~14–15 min**.
- Top `binding_confidence` 0.67 (below 0.7 high-confidence bar); ADME mixed.
- Confirm UX copy: “~15 min, US$0.25, scores are in-silico only.”
