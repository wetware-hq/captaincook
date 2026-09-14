# Feature: user session superstructure — per-patient clinical `.md` + biological `.ipynb`

**Status:** Proposed 2026-09-14 (awaiting lock) · biostrategist  
**Owners:** biostrategist · biomodels · biolang (clinical md voice) · bioresearch (sort taxonomy)  
**Idiot Index bar:** biomedical engineering clarity + software standards (one schema, two files, one daemon)

## Hierarchy

```
USER (telegram user_id)
├── message_history[]          # append-only events
├── cards[]                    # /load contexts
│   └── patient_id → binds card to patient record
├── patients[]
│   ├── clinical.md            # ONE file; ## headers by DEPARTMENT/SPECIALTY
│   ├── biological.ipynb       # ONE notebook; cells tagged by specialty
│   ├── biometrics (secrets)   # not echoed into md body
│   └── embeddings (optional)  # search index over sections/cells
└── inbox/                     # unlinked outputs (/scribe v1) until assigned to a patient
```

## Superstructures (locked shape)

**For each patient — exactly two core files:**

1. **`clinical.md`** — clinician + well-educated patient prose; section headers = department/specialty (`## Oncology`, `## Cardiology`, `## Meeting minutes`, `## Evidence`, …).  
2. **`biological.ipynb`** — code/data cells for structures, designs, metrics, artifact paths (CIF/CSV/PNG), preprint/methods notes.

No third “misc dump” file. Unassigned material stays in **user inbox** until a patient exists or `/assign` (later).

## Command → store map (Minimum Idiot Index)

| Command | Structure | Store |
| --- | --- | --- |
| `/start` `/help` | — | history event only |
| `/load` | card JSON | card under user; link `patient_id` if onboarded |
| `/onboard` | biometrics secrets | secrets store; clinical.md gets **Demographics: on file** stub only (no raw values) |
| `/note` | prose note | append under clinical.md `## Notes` (or specialty if tagged) |
| `/scribe` | minutes md | inbox if unlinked; else clinical.md `## Meeting minutes` / specialty |
| `/research` | preprint brief + Harvard | biological.ipynb markdown cell `## Literature (preprint)` **or** clinical if question was care-framed — default **biological** |
| `/evidence` | peer-reviewed brief + Harvard | clinical.md `## Evidence` |
| `/esm` `/boltz` | photo+caption + CIF meta | biological.ipynb code/md cells + artifact paths |
| `/design` `/confirm` | grid+caption + CSV/CIF | biological.ipynb |
| `/view` | replay | history + pointer; no duplicate blob if fingerprint hit |
| `/download` | send files | history; paths already in ipynb |
| `/cancel` | — | history only |
| Bioscreen REVIEW/BLOCK | refuse | clinical.md `## Biosecurity` (no sequence dump) |

## Background daemons (sort)

**One worker type:** `history_sorter` (asyncio task or queue consumer on the poller host).

1. Every user-visible success (and optional plain messages) appends a **typed event** to `message_history`.  
2. Daemon dequeues → classifies `clinical | biological | skip` with a **fixed rule table** first (command → bucket above); optional LLM only for free-text ambiguity.  
3. Updates the patient’s **one** `clinical.md` or **one** `biological.ipynb` (section upsert by specialty header / cell tag).  
4. Idempotent: event `id` recorded; retries safe.  
5. Fail-closed: sorter down → events queue; files not half-written (temp + rename).

No per-command custom writers beyond emitting events — **daemons own file mutation** (software standard: single writer).

## Specialty headers (starter set)

`General` · `Oncology` · `Haematology` · `Cardiology` · `Infectious disease` · `Meeting minutes` · `Evidence` · `Notes` · `Biosecurity` · `Imaging` · `Pharmacy`

Expand via config list — not free-string proliferation.

## Acceptance (when locked)

1. With patient onboarded, `/evidence` + `/confirm` land in `.md` vs `.ipynb` respectively.  
2. `/scribe` unlinked → inbox; after patient link → clinical.md minutes section.  
3. Biometrics never appear as raw values in either file.  
4. Restart: durable user store recovers both files; sorter resumes queue.  
5. Exactly two core files per patient.

## Split

- Spec — biostrategist  
- Event bus + daemon + file writers — biomodels  
- clinical.md voice — biolang  
- Specialty taxonomy — bioresearch  
- Discord — never mirrors these files (bioplatform)
