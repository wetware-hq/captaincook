# Feature: user session superstructure — per-patient clinical `.md` + biological `.ipynb`

**Status:** Locked 2026-09-14 · renamed clinic.md + lab.ipynb · search.json sidecar · biostrategist  
**Owners:** biostrategist · biomodels · biolang (clinical md voice) · bioresearch (sort taxonomy)  
**Idiot Index bar:** biomedical engineering clarity + software standards (one schema, two files, one daemon)

## Hierarchy

```
USER (telegram user_id)
├── message_history[]          # append-only events
├── cards[]                    # /load contexts
│   └── patient_id → binds card to patient record
├── patients[]
│   ├── clinic.md            # ONE file; ## headers by DEPARTMENT/SPECIALTY
│   ├── lab.ipynb       # ONE notebook; cells tagged by specialty
│   ├── biometrics (secrets)   # not echoed into md body
│   └── embeddings (optional)  # search index over sections/cells
└── inbox/                     # unlinked outputs (/scribe v1) until assigned to a patient
```

## Superstructures (locked shape)

**For each patient — exactly two core files:**

1. **`clinic.md`** — clinician + well-educated patient prose; section headers = department/specialty (`## Oncology`, `## Cardiology`, `## Meeting minutes`, `## Evidence`, …).  
2. **`lab.ipynb`** — code/data cells for structures, designs, metrics, artifact paths (CIF/CSV/PNG), preprint/methods notes.

No third “misc dump” file. Unassigned material stays in **user inbox** until a patient exists or `/assign` (later).

## Command → store map (Minimum Idiot Index)

| Command | Structure | Store |
| --- | --- | --- |
| `/start` `/help` | — | history event only |
| `/load` | card JSON | card under user; link `patient_id` if onboarded |
| `/onboard` | biometrics secrets | secrets store; clinic.md gets **Demographics: on file** stub only (no raw values) |
| `/note` | prose note | append under clinic.md `## Notes` (or specialty if tagged) |
| `/scribe` | minutes md | inbox if unlinked; else clinic.md `## Meeting minutes` / specialty |
| `/research` | preprint brief + Harvard | **lab.ipynb** markdown cell `## Literature (preprint)` only — no care-framed clinic route |
| `/evidence` | peer-reviewed brief + Harvard | clinic.md `## Evidence` |
| `/esm` `/boltz` | photo+caption + CIF meta | lab.ipynb code/md cells + artifact paths |
| `/design` `/confirm` | grid+caption + CSV/CIF | lab.ipynb |
| `/view` | replay | history + pointer; no duplicate blob if fingerprint hit |
| `/download` | send files | history; paths already in ipynb |
| `/cancel` | — | history only |
| Bioscreen REVIEW/BLOCK | refuse | clinic.md `## Biosecurity` (no sequence dump) |

## Background daemons (sort)

**One worker type:** `history_sorter` (asyncio task or queue consumer on the poller host).

1. Every user-visible success (and optional plain messages) appends a **typed event** to `message_history`.  
2. Daemon dequeues → classifies `clinical | biological | skip` with a **fixed rule table** first (command → bucket above); optional LLM only for free-text ambiguity.  
3. Updates the patient’s **one** `clinic.md` or **one** `lab.ipynb` (section upsert by specialty header / cell tag).  
4. Idempotent: event `id` recorded; retries safe.  
5. Fail-closed: sorter down → events queue; files not half-written (temp + rename).

No per-command custom writers beyond emitting events — **daemons own file mutation** (software standard: single writer).

## Specialty headers (starter set)

`General` · `Oncology` · `Haematology` · `Cardiology` · `Infectious disease` · `Meeting minutes` · `Evidence` · `Notes` · `Biosecurity` · `Imaging` · `Pharmacy`

Expand via config list — not free-string proliferation.


## Daemon authority (user lock 2026-09-14)

Background daemons are the **sole mutators** of per-patient durable clinical/biological state. They have **full read/write** access required to keep patient information consistent:

| Access | Scope |
| --- | --- |
| Read | `message_history`, cards, patient metadata, `clinic.md`, `lab.ipynb`, inbox, artifact paths, embeddings index |
| Write / edit | Create, append, rewrite sections/cells, dedupe, merge, retitle specialty headers, fix cross-refs, update embeddings, move inbox → patient files, reconcile after `/view`/`/download` |
| Not allowed | Echo biometric **secret values** into `.md`/`.ipynb` bodies; mirror patient files to Discord; send secrets to hosted LLMs; delete the user root without an explicit user command |

**Consistency duties (edit functions):**

1. Upsert the correct specialty section/cell for each event.  
2. Dedupe by event `id` (idempotent).  
3. Rewrite stale summaries when newer evidence/structure supersedes.  
4. Keep Harvard/DOI blocks intact when merging literature.  
5. Repair broken artifact links when files move under the patient tree.  
6. Re-embed changed sections when embeddings are enabled.

Handlers **emit events only**; they do not bypass the daemon to patch `clinic.md` / `lab.ipynb` directly (single-writer rule).


## Lit + voice constraints on daemon edits (room 2026-09-14)

From @bioresearch / @biolang — bind into daemon R/W:

1. **DOI idempotency:** upsert `/evidence` and `/research` material by DOI; never paste the same paper twice into a section.  
2. **Harvard intact:** never strip or scramble the bottom `## References` block from an Evidence (or research) block; rewrites must keep claim→cite alignment.  
3. **Tone fence:** daemon may compress prose for consistency but must **not** upgrade preprint language into peer-reviewed tone, or the reverse.  
4. **No invented claims** when retitling specialty headers or merging.  
5. Embeddings over sections OK later; **no** silent re-fetch of lit; **no** secrets into hosted embed APIs.


## Session search index (v1)

Per patient, alongside the two core files:

```
patients/<id>/
  clinic.md
  lab.ipynb
  search.json          # real-time chat lookup sidecar
```

`search.json` (Minimum Idiot Index — no embeddings in v1):

```json
{
  "updated_at": "iso8601",
  "entries": [
    {"doi": "10.…", "file": "clinic.md"|"lab.ipynb", "section": "Evidence|…", "offset": 0, "title": "…", "tokens": ["…"]}
  ]
}
```

- Daemon updates the sidecar on every upsert (same transaction as file write).  
- Chat search = token / DOI / section lookup over `search.json` (O(entries), fine for session scale).  
- Embeddings deferred; Discord never indexes or mirrors this.

## Acceptance (when locked)

1. With patient onboarded, `/evidence` + `/confirm` land in `.md` vs `.ipynb` respectively.  
2. `/scribe` unlinked → inbox; after patient link → clinic.md minutes section.  
3. Biometrics never appear as raw values in either file.  
4. Restart: durable user store recovers both files; sorter resumes queue.  
5. Exactly two core files per patient.

## Split

- Spec — biostrategist  
- Event bus + daemon + file writers — biomodels  
- clinic.md voice — biolang (`docs/TEMPLATE-clinic-md.md`)  
- Specialty taxonomy — bioresearch  
- Discord — never mirrors these files (bioplatform)
