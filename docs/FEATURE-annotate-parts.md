# FEATURE: `/annotate parts` → `/app` Laboratory Parts

**Status:** shipping v1a Bakta (locked 2026-09-20 GC)  
**Owners:** biomodels (wire) · bioplatform (`/app` deploy) · biolang (TEMPLATE/HELP) · biostrategist (this FEATURE)  
**Depends on:** `commec` bioscreen PASS; DNA/RNA alphabet; `/app` Laboratory merge  
**Orthogonal:** `/annotate` CNV/SV (ClassifyCNV) unchanged — Chromosomal stays CNV-only.

## Goal

Full **genetic-parts** annotation layer: named open tools → GenBank/GFF → Telegram brief + `/app` Laboratory **Parts** (SEQ chips + TABLE). Never invent features. Research-use only — not a diagnosis.

## Locked stack

| Role | Tool |
| --- | --- |
| Biosecurity hard gate | `commec` (DNA/RNA); AA refuse invent |
| Unified structural lead | **Bakta** (+ Pyrodigal) → GenBank/GFF (CDS / tRNA / rRNA / CRISPR / ori …) |
| Regulatory minset add-on | PromoterAtlas *or* curated iGEM/Addgene match → promoter / RBS / terminator |
| Viewer | SeqViz (optional later); GFF drives chips/table first |
| Avoid as lead | HF foundation nets (GENERanno / GENA-LM) — estimate-only if ever added |

## Telegram contract

- Input: card SEQUENCE (DNA/RNA) after `/load`, or FASTA upload; refuse AA invent
- Gate: alphabet → `commec` → Bakta (+ optional regulatory)
- Reply: **length + hash + feature counts** only; never dump sequence body
- Fail-closed if Bakta/`commec` missing
- Store: GFF/GenBank artifact on card + `lab.ipynb` via history_sorter; `search.json` indexes feature types/counts only (no seq)

## `/app` integration (Laboratory **Parts**)

Prefer **Laboratory** for construct/parts. Chromosomal stays CNV-only.

| View | Behaviour |
| --- | --- |
| **SEQ** | Horizontal chips / interval bars per feature type (color by type); tap → breakdown |
| **TABLE** | Color-coded rows: type · name/product · start–end · strand · length |
| Tap panel | Short sentences: product/span; end with “research annotation — not a diagnosis.” |
| Sequence body | Length + hash only — never full seq in HTML |
| Redaction | No patient secrets; Discord dark |

## Ship bar (acceptance)

1. DNA/RNA → `commec` first; AA refuse invent  
2. Bakta → GenBank/GFF; promoter/RBS/terminator via PromoterAtlas or curated match  
3. Telegram: length+hash + feature counts; never dump seq  
4. `/app` Laboratory **Parts**: SEQ chips + TABLE; tap → product/span  
5. Discord dark; Chromosomal untouched  

## Out of scope v1 parts

- Clinical ACMG CNV (ClassifyCNV path)
- Nucleotide letter canvas as default
- Merging `commec` stamps into GFF feature types
- HF as lead annotator

## HELP (biolang)

`/annotate` = CNV/SV + biosecurity only.  
`/annotate parts` = Bakta (+ PromoterAtlas/curated) genetic-parts — separate line.

## E2E smoke (locked 2026-09-20)

| # | Case | Expect |
| --- | --- | --- |
| 1 | DNA FASTA on card → `/annotate parts` | `commec` then Bakta; Telegram length+hash+counts; `last_run.parts` (no seq body) |
| 2 | AA-only sequence → `/annotate parts` | Refuse invent (fail-closed) |
| 3 | `/app` after parts | Laboratory **Parts** SEQ chips + TABLE; tap → product/span; no full seq in HTML |
| 4 | Coords `/annotate` then `/app` | Chromosomal CNV unchanged; Parts absent or prior only |
| 5 | Discord | Dark (no PHI / no seq dump) |

Pass = all five green on same tip. Owners: biomodels (1–2,4 wire) · bioplatform (3,5 + smoke run).

## Laboratory Parts visual (locked — editor + biolang)

- SEQ chips = feature **class counts** only (CDS / tRNA / …) — no sequence dump  
- TABLE = sparse rows (type · start–end · product); tap → one short panel  
- Same white ≤42rem serif; no Mol* chrome unless a structure id already exists  
- Empty = “None yet.”  
- Tap panel ends “research annotation — not a diagnosis.”

## Production notify (user lock 2026-09-20)

Notify user in this room **once all** are true:
1. `/annotate parts` + `/app` Laboratory Parts on `main`
2. E2E smoke (five cases) green
3. README hybrid row updated
4. Discord dark throughout

Owners: bioplatform posts the notify; biolang README; biomodels wire.
