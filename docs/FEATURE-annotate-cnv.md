# Feature: `/annotate` — chromosomal CNV annotation (interpretable clinical biosecurity layer)

**Status:** Locked 2026-09-20 (min Idiot Index × max clinical utility)  
**Owners:** biostrategist · biomodels · bioresearch · biolang · bioplatform (no Discord PHI)  
**Depends on:** alphabet gate + `commec` bioscreen; clinic.md / search.json; `/app` Clinical merge  
**Inspiration (UX):** Benchling-class clean feature tracks — not a cytogenetics workstation

## Goal

Observable, interpretable layer for **clinical biosecurity / chromosomal interpretation**: user-supplied CNV/SV intervals → ACMG/ClinGen-style **score breakdown** clinicians can inspect. Orthogonal to `commec` (SoC/synth hazmat gate). Research-use only. **Not a diagnosis.**

## v1 scope (locked)

| In | Out |
| --- | --- |
| CNV/SV annotation (gain/loss, chr:start-end + type) | Full ISCN karyotype workstation |
| Gene overlap as **output** of CNV annotate | Separate SNV pipeline (stays `/variant`) |
| DNA/RNA unambiguous sequences / BED / VCF-SV paste | AA→DNA invent; black-box ML pathogenicity as lead |

## Backend (arbitrary complexity)

- Streaming/chunked ingest of BED / VCF-SV / `chrN:start-end DEL|DUP` lines — **no hard length cliff** on interval count  
- Engine v1: **ClassifyCNV** (ACMG/ClinGen 2019 breakdown) preferred; AnnotSV if already ops-friendly  
- Alphabet classify → **`commec` first** (PASS/REVIEW/BLOCK) → annotate only when bioscreen allows (PASS, or REVIEW with explicit human proceed)  
- Bioscreen and ACMG stamps stay **orthogonal** — never merge into one score; ACMG alone never auto-BLOCK synth path  

## Frontend (Benchling-inspired, clean)

| Surface | Behavior |
| --- | --- |
| Telegram | Helper-first paste (like `/measure`); MD brief: class + **criteria breakdown bullets** + overlapped genes + “not a diagnosis” + cites |
| `/app` Clinical | Section **Chromosomal** — scan-first: compact track/ideogram of intervals + ≤3 bullets + Harvard; secrets never shown |
| Viz | Simple chromosomal **feature tracks** (interval lanes, zoomable in HTML app) — Benchling-like readability, not dense coordinate dumps in chat |
| Out of v1 | Full genome browser / Benchling editor clone inside Telegram |

## Commands

| Command | Behavior |
| --- | --- |
| `/annotate` | Arm paste or parse lines |
| `/annotate <lines>` | Immediate parse if short |
| Bad paste | Helper coach + examples + re-arm (no NLP paragraph invent) |

## Store

- `clinic.md ## Chromosomal`  
- `search.json` `cnv:<id>`  
- Feed `/board` / `/app` Clinical (redacted)  
- **Not** `lab.ipynb`  
- Never Discord PHI  


## Frontend stack (amended — bioresearch 2026-09-20)

Prefer existing OSS — **do not** build a genome browser from scratch.

| Scale | Viewer | Role |
| --- | --- | --- |
| Gene / plasmid / construct (≤~50 kb) | **SeqViz** (MIT) | Benchling-like linear/circular, feature lanes, zoom — embed in `/app` HTML |
| Chromosomal / multi-Mb windows | **igv.js** | CNV + gene tracks |

Telegram stays thin: MD summary + `/app` link. Canvas on HTTPS page only. White/minimal; labels readable; no dense dumps.

## Backend complexity (amended)

- Canonical store: **sequence record + feature table** (GenBank/GFF3/BED), not FASTA walls in chat  
- Long contigs: **lazy/windowed** annotate — intervals in view or user BED  
- Mixed DNA|RNA|AA = **separate records**; never invent DNA from AA  
- Streaming parse; size caps + helper refuse; idempotent feature hashes  





## NGS clinic compatibility (locked 2026-09-20 — user)

Compatible with **clinic-adopted NGS** panel / exome / WGS / long-read SV exports.

| Require | Refuse |
| --- | --- |
| **BED** or **VCF-SV** (and `chr:start-end DEL\|DUP` lines) | FASTA / AA pasted as “chromosome” |
| **Assembly tag** — GRCh38 default; GRCh37 accepted; helper if missing | Silent build guess |
| Same tap→detail `/app` strip for short-read or long-read calls | Hardware-specific chrome |

ClassifyCNV/ACMG path stays **assembly-aware** so bars don’t mis-map builds. Discord dark.

## Plasmid-viewer inspiration (locked 2026-09-20 — user / NYSRG)

Take **interaction**, not construct chrome:

| Keep | Drop for Clinical Chromosomal |
| --- | --- |
| Feature lanes · tap → detail panel | Circular plasmid map |
| Class/colour coding | Enzyme rings / bp letter canvas |
| Clean linear strip on chr | Open Vector Editor / SeqViz as default |

`/app` Clinical Chromosomal = linear strip + class colours + ACMG breakdown + gene → `/evidence`/`/variant`. Bioscreen remains the hard gate beside it. SeqViz/igv letter views stay opt-in later.

## Informative · interactive · useful (locked 2026-09-20 — user)

Minimise *busywork* interaction — **not** a static poster. Clinicians must get value from the layer.

| Must | How (still above 1 bp / 1 AA) |
| --- | --- |
| **Informative** | Class, ACMG criteria breakdown, key overlapped genes, bioscreen stamp if any — readable in ≤3 bullets + detail panel |
| **Interactive** | Tap/click a CNV interval → side panel with breakdown; filter by chr / DEL vs DUP; expand “why this class” |
| **Useful** | Actionable next steps: copy genes, open `/evidence`/`/variant` for a gene, link out to ClinGen-style cites; feeds `/app` board |

Still abstract away nucleotide/AA letter resolution. Interaction is at **interval / gene / class** granularity.

## Clinician UX boil-down (locked 2026-09-20 — user)

**Minimum interactive UX · maximum clinician experience.**  
**Abstract away single-base and single-amino-acid resolution.**

| Do | Don’t |
| --- | --- |
| Chromosome / arm / band / CNV interval cards | Zoom to 1 bp or 1 AA |
| One glance: gain/loss + class + ≤3 genes | Sequence letter canvases as the lead view |
| Tap/open `/app` section; optional one-click “details” | Full Benchling editor, pan/zoom nucleotide tracks in v1 |
| MD brief + simple ideogram/track of **intervals** | SeqViz/igv at residue resolution as default |

**v1a lead experience:** Telegram MD (class + breakdown + genes) + `/app` Clinical **interval strip** (chr bars, colored DEL/DUP).  
**SeqViz / igv.js nucleotide views:** deferred unless user asks “sequence detail” — not the default clinician path.

## Staged ship

| Stage | Scope |
| --- | --- |
| **v1a** | ClassifyCNV + MD brief + clinic.md / search.json |
| **v1b** | Interval strip / ideogram in `/app` Clinical (not 1bp) |
| **v1c** | Optional sequence detail (SeqViz/igv) — opt-in only, not default |

`commec` stamps may show as non-editable banners on the viewer — never soft-PASS bioscreen.

## Ship order

1. FEATURE lock (this file)  
2. Helper paste + ClassifyCNV wire  
3. clinic.md + search.json  
4. `/app` Clinical track merge  
5. README/HELP  

## Acceptance

1. BED of KRAS-region DUP → class + inspectable criteria + genes; not a diagnosis.  
2. AA-only card → refuse chromosomal annotate (no invent DNA).  
3. `commec` BLOCK → no annotate.  
4. Pure prose paste → helper, not invented CNVs.  
5. `/app` shows Chromosomal section without secret bleed.

## Split

- Spec — biostrategist  
- ClassifyCNV + paste parser — biomodels  
- Tool/criteria sanity — bioresearch  
- TEMPLATE-annotate + helper copy — biolang  
- Discord dark — bioplatform  
