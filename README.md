# Captain Cook

<img src="docs/cook.jpg" width="280" alt="Captain Cook">

Research-use Telegram agent for structure prediction, ligand and protein-binder design, literature briefs, meeting minutes, and session-scoped clinical context. Wetware Sydney.

## Abstract

Captain Cook accepts a protein sequence or a short natural-language request and returns a single result unit: one image and one clinically readable caption. Folding uses Biohub ESMFold2. Structure prediction, binding scores, and small-molecule (**ligand**) design use Boltz (`boltz-2.1` and the design API). Protein **binder** design uses BindCraft via optional Modal compute-only jobs (fail-closed until configured). All scores are computational estimates. A pre-compute biosecurity gate classifies DNA and RNA before paid GPU work. `/research` returns a preprint literature brief (bioRxiv and medRxiv). `/evidence` returns a peer-reviewed MEDLINE brief with preprints excluded. Both use Europe PMC and Harvard references. `/scribe` organises user-supplied meeting text into structured minutes; unlinked minutes sit in a user inbox until assigned to a patient. Per patient, a background sorter maintains exactly two core files — `clinic.md` (clinical prose, including peer-reviewed Evidence) and `lab.ipynb` (structures, designs, preprint literature) — plus a `search.json` sidecar for fast DOI and section lookup. Session biometrics stay secret on the card and never appear as raw values in those files, language-model prompts, research briefs, or Discord. `/app` (with `/board` alias), `/annotate`, `/variant`, and `/trials` support case discussion, variant literature, and public trial shortlists without diagnosing, dosing, or enrolling anyone. The agent does not diagnose disease, recommend therapy, or plan synthesis or wet-lab work. Operators remain responsible for Biohub and Boltz acceptable-use policies and for applicable law.

## Agent contract

| Concern | Specification |
| --- | --- |
| Channel | Telegram long-polling via `python-telegram-bot` v21+ on Python 3.11+. |
| Compute | Biohub ([`biohub.ai`](https://biohub.ai/learn/getting-started)) for folding; Boltz ([`api.boltz.bio`](https://api.boltz.bio/docs/)) for structure, binding, and ligand design; BindCraft (optional Modal GPU) for protein binders. |
| Bioscreen | Before GPU or paid API calls: `PASS`, `REVIEW`, or `BLOCK`. Unambiguous DNA or RNA is screened with local IBBIS `commec` (thin MIT packs, `--skip-tx` in v1). Amino-acid paths skip `commec` and do not reverse-translate. Tool-down fails closed (`BLOCK`). |
| Success payload | One `reply_photo` with a 3C caption written for physician and patient readers. Binder photos: target default colour, binder accent; N=1 single complex, N>1 grid. No diagnosis or drug claims. |
| Literature | `/research` → preprint brief → Telegram `.md` and `lab.ipynb` literature cell (bioRxiv/medRxiv only; no care-framed route to clinic). `/evidence` → peer-reviewed brief → Telegram `.md` and `clinic.md` `## Evidence` (MEDLINE; preprints excluded). Each brief uses Harvard references (≤5, DOI preferred). Social (X) signal is deferred. |
| App / variant / trials | `/app` (and `/app update`; `/board` / `/board update` aliases one release) → case-conference MD packet from session stores + optional short-TTL HTTPS live view (7-day default / 30-day max; fail-closed without `APP_DEPLOY_*`). `/app revoke` ends sharing early. Live view merges clinic.md → Clinical and lab.ipynb → Laboratory (no tone bleed). `/variant` → papers-first peer-reviewed gene/variant brief (no FM scores in v1). `/trials` → ClinicalTrials.gov shortlist (eligibility themes only; never enroll). Specialty-agnostic; research-use only. |
| Minutes | `/scribe` → one structured Markdown meeting-minutes document from user-supplied text. Unlinked by default (user inbox); when linked, the sorter appends under `clinic.md` `## Meeting minutes`. Fail-closed if the scribe LLM is unset or down. |
| Artifacts | mmCIF and design `candidates.csv` remain on the chat context card; `/download` sends them as documents. |
| Context | `/load` builds a formal card from natural language without GPU use. Bare `/esm`, `/boltz`, and `/design` consume that card. |
| Biometrics | `/onboard` stores secret age, sex, weight, and height on the card. `/load` shows only Patient: on file or incomplete — never raw values. |
| Patient files | `/note` appends session notes to `patient_files[]`, separate from biometric secrets. Bodies are not shown in `/load` or list output. |
| Patient store | Per patient: `clinic.md` + `lab.ipynb` + `search.json`. Handlers emit events; one background daemon is the sole file writer (DOI-idempotent Evidence upserts; Harvard bottoms never stripped). Design hits index as `ligand:` or `binder:` in `search.json` and land in `lab.ipynb` only. |
| Privacy | Biometric secrets never appear as raw values in `clinic.md` / `lab.ipynb`. Secrets and note bodies never enter language-model prompts, lit briefs, or captions. `/scribe` must not invent decisions absent from the source. Discord outbound is optional and **not live** until `DISCORD_WEBHOOK_URL` is set; patient files, `/annotate` results, and `/app` live links are never mirrored. |
| Replay | `/view` returns the cached photo and caption when the new card fingerprint matches a prior completed run. Cache is chat-session only and uses no GPU. Fingerprints exclude patient secrets and patient files. |
| Spend gate | `/design ligand` or `/design binder` estimates cost and waits (explicit mode; bare `/design` asks which). `/confirm` starts the pending job. `/cancel` aborts. |

Dummy sequence for documentation only: `MKTIIALSYIFCLVFA`.

## Commands

| Command | Action |
| --- | --- |
| `/start` `/help` | Introduction and research-use notice. |
| `/esm <sequence>` | Biohub ESMFold2 fold; returns photo and caption. |
| `/boltz <sequence>` | Boltz structure prediction; returns photo and caption. |
| `/boltz <sequence> <smiles>` | Boltz structure and binding; returns photo and caption. |
| `/design` | Asks for an explicit mode: `ligand` or `binder`. |
| `/design ligand` `[n]` | Queues Boltz small-molecule design (API floor 10 molecules ≈ US$0.25; cap 100). Requires `/confirm`. |
| `/design binder` `[n]` | Queues BindCraft protein-binder design (default 5; cap 20). Requires `/confirm`. Fail-closed until Modal/BindCraft is configured. |
| `/bind` | Withdrawn stub — use `/design binder`. |
| `/load <nl>` | Parses intent into a context card without GPU use. |
| `/load` | Shows the current card (Patient: on file / incomplete only; no secrets or note bodies). |
| `/load clear` | Clears the card, session cache, stashed files, biometrics, and patient files. |
| `/view` | Replays the stored photo and caption for a matching completed card. |
| `/download` | Sends the last-run CIF and, for ligand design, the CSV (binder FASTA/CIF when available). |
| `/confirm` | Runs the pending ligand or binder job; returns one photo and a research-use caption. |
| `/cancel` | Aborts the pending design job, onboard Q&A, or armed `/scribe` / `/note` capture. |
| `/research <topic>` | Europe PMC preprint brief → Markdown document with Harvard references (≤5). |
| `/evidence <question>` | Europe PMC peer-reviewed brief (MEDLINE; preprints excluded) → Markdown with Harvard references (≤5). |
| `/onboard` | Collects biometric secrets one question at a time. |
| `/onboard status` | Complete or incomplete — no raw values. |
| `/onboard clear` | Clears biometric secrets and patient files. |
| `/note` | If a patient exists, saves the next message to patient files. |
| `/note list` | Shows patient-file count only. |
| `/note clear` | Clears patient files; biometric secrets unchanged. |
| `/scribe` | Arms the next message as meeting notes or a transcript (unlinked). |
| `/scribe <text>` | Organises short text into meeting minutes immediately. |
| `/app` | Case-conference MD + optional TTL live view (`APP_DEPLOY_*`). **Clinical** includes Chromosomal (**SEQ** horizontal labeled CNV chips + **TABLE** toggle; tap → ACMG breakdown; GRCh38/37). **Laboratory** includes Structures (Mol* mmCIF + 3Dmol ligands). Discord never mirrors `/app` or annotate. |
| `/app update` | Same as `/app` — fresh snapshot (not an incremental merge). |
| `/app revoke` | Ends sharing of the current live view early. Markdown packet unchanged. |
| `/board` | Alias of `/app` for one release. |
| `/board update` | Alias of `/app` for one release. |
| `/annotate` | NGS clinic paste: **BED / VCF-SV** (or `chr:start-end DEL|DUP`) with **GRCh38** (default) or **GRCh37** tagged; helper if assembly missing. ClassifyCNV ACMG/ClinGen breakdown → `clinic.md ## Chromosomal` + live `/app` **SEQ/TABLE** strip. Orthogonal bioscreen; refuse FASTA-as-chromosome / AA-invented DNA; **not a diagnosis**; Discord dark. |
| `/variant <gene> <change>` | Peer-reviewed gene/variant brief (papers-first; not a diagnosis). |
| `/trials` `[query]` | Public ClinicalTrials.gov shortlist (≤10); eligibility themes only; never enrolls. |

If image render fails, the caption is still sent as text.

## Design flow

Modes are **explicit**. Bare `/design` asks for `ligand` or `binder` and never auto-guesses.

### Ligand (Boltz)

1. Optional: `/load find me an inhibitor for KRAS G12C GDP` builds a card without calling GPU.
2. `/design ligand` `[n]` validates input, estimates cost, and stores a pending job. It does not start compute.
3. The confirm card shows molecule count, estimated cost in US dollars, and the research disclaimer. Reply `/confirm` to spend or `/cancel` to stop.
4. `/confirm` runs Boltz small-molecule design and returns one RDKit ligand grid with a 3C caption. CIF and CSV remain on the card for `/download`.

Candidates are ranked in silico only. A covalent design request without an explicit bonds payload returns a clear client or API error. Version 1 does not invent warheads.

### Binder (BindCraft)

1. `/load` a target and obtain a structure (for example `/esm` or `/boltz`). For KRAS G12C, “Switch-II” maps to curated hotspot residues **60–76** (fixture only; never LM-invented).
2. `/design binder` `[n]` shows a confirm card (default N=5, cap 20). Hotspot residues are used only if present on the card (or from the KRAS Switch-II fixture map); otherwise the run is target-wide and stated as such. Hotspots are not invented. Binder jobs can take tens of minutes to a few hours.
3. `/confirm` runs BindCraft on optional Modal compute-only GPU (or local `BINDCRAFT_HOME`). Missing Modal/BindCraft configuration **fail-closes** — no invented binders.
4. Success returns one Telegram **`reply_photo`**: **N=1** is a single target+binder cartoon; **N>1** is a ranked ligand-style grid of complex views. The **target** keeps the default cartoon colour; the **binder** chain is coloured distinctly (orange) so the design is visually separable. If image render fails, a text caption plus `/download` is used — never a blank chat. CIF/FASTA stay on the card for `/download`; sorter writes `lab.ipynb` and `search.json` under `binder:`. Patient files and biometrics never go to Modal.

## Credentials

Three environment variables are required:

1. `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
2. `BIOHUB_API_TOKEN` — from the [Biohub developer console](https://biohub.ai/developer-console/api-keys)
3. `BOLTZ_API_KEY` — from the [Boltz API console](https://api.boltz.bio/console) (header `x-api-key`)

Optional:

- `TELEGRAM_ALLOWED_USER_ID` — restrict the bot to one Telegram user
- `COMMEC_BIN` / `COMMEC_TIMEOUT_SEC` — local IBBIS `commec` for DNA/RNA bioscreen (fail-closed if missing)
- `DISCORD_WEBHOOK_URL` — optional outbound `/research` TLDR mirror only (unset = disabled / **not live**; never echoes the URL; never sends clinic or lab files)
- `SCRIBE_LLM_URL` / `SCRIBE_LLM_KEY` / `SCRIBE_LLM_MODEL` — optional OpenAI-compatible chat endpoint for `/scribe` (unset = fail-closed)
- `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` — Modal API tokens for compute-only BindCraft (`/design binder`)
- `BINDCRAFT_HOME` / `BINDCRAFT_TIMEOUT_SEC` — local BindCraft alternative; unset with Modal missing → binder fail-closed

Missing required variables cause an immediate, clear exit. Secrets live in process environment (local `.env`); they are never committed and never echoed in chat.

## Local setup

```bash
cd captaincook
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python -m src.bot
```

## Docker

```bash
cd captaincook
docker build -t captaincook .
docker run --rm --env-file .env captaincook
```

## Layout

```
captaincook/
  README.md
  .env.example
  requirements.txt
  Dockerfile
  docs/          # FEATURE-*, VOICE.md, COPY-*, TEMPLATE-*.md (incl. clinic), REFUSE-bioscreen.md
  src/
    bot.py
    context_card.py    # /load → formal card
    card_cache.py      # fingerprint + /view
    downloads.py       # CIF/CSV stash
    bioscreen.py       # PASS / REVIEW / BLOCK pre-GPU gate
    research_client.py # Europe PMC
    research_md.py     # Harvard preprint brief
    evidence_client.py # peer-reviewed Europe PMC
    evidence_md.py     # Harvard evidence brief
    scribe_client.py   # optional LLM for /scribe
    scribe_md.py       # meeting-minutes render
    # patient store: clinic.md + lab.ipynb + search.json (daemon sole writer)
    onboard.py         # biometric secrets Q&A
    patient_files.py   # /note patient_files[]
    discord_webhook.py # optional outbound /research TLDR
    biohub_client.py
    boltz_client.py
    small_molecule_design.py
    interpret.py       # 3C captions
    result_photo.py    # design grid PNG
    structure_photo.py # mmCIF → PNG
    targets.py         # curated KRAS resolve
    config.py
```

## API notes

**Biohub** (`pip install esm`): Forge clients at `https://biohub.ai` with `BIOHUB_API_TOKEN`. Fold model `esmfold2-fast-2026-05` via `fold_all_atom`. ESMC fallback model `esmc-6b-2024-12`.

**Boltz** (`pip install boltz-api`): `Boltz(base_url="https://api.boltz.bio", api_key=BOLTZ_API_KEY)`. Structure and binding use `predictions.structure_and_binding` with model `boltz-2.1`. See [predictions](https://api.boltz.bio/docs/guides/predictions/) and [authentication](https://api.boltz.bio/docs/guides/authentication/).

**Literature:** Europe PMC search REST for `/research` (preprints) and `/evidence` (peer-reviewed MEDLINE; `NOT SRC:PPR`). bioRxiv native keyword API and OpenAlex are out of scope for v1.

**Bioscreen:** Local open-source IBBIS [`commec`](https://github.com/ibbis-bio/common-mechanism) with MIT [`commec-databases`](https://github.com/ibbis-bio/commec-databases) packs. Sequences are written to a temporary FASTA on the host; nothing is uploaded to IBBIS.

## Safety

Sequences use a validated alphabet and a default protein length cap of 800 residues. DNA and RNA requests are gated with `PASS` / `REVIEW` / `BLOCK` before compute; refuse copy never includes scores or internals that teach bypass. Optional user allowlisting is supported. API failures return a short user-facing error without stack traces in chat. Help text and handlers refuse pathogen design, reverse genetics, synthesis planning, wet-lab protocols, and diagnosis or dosing from biometrics or patient files. `/scribe` organises only what the source states and does not invent decisions. `/design binder` does not invent binders when BindCraft/Modal is unavailable.
