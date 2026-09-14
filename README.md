# Captain Cook

<img src="docs/cook.jpg" width="280" alt="Captain Cook">

Research-use Telegram agent for structure prediction, ligand design, literature briefs, and session-scoped clinical context. Wetware Sydney.

## Abstract

Captain Cook accepts a protein sequence or a short natural-language request and returns a single result unit: one image and one clinically readable caption. Folding uses Biohub ESMFold2. Structure prediction, binding scores, and small-molecule design use Boltz (`boltz-2.1` and the design API). All scores are computational estimates. A pre-compute biosecurity gate classifies DNA and RNA before paid GPU work. `/research` returns a short Markdown literature brief from Europe PMC (bioRxiv and medRxiv), with Harvard references. Session biometrics and patient files stay on the Telegram context card and are never sent to language models, research briefs, or Discord in this version. The agent does not diagnose disease, recommend therapy, or plan synthesis or wet-lab work. Operators remain responsible for Biohub and Boltz acceptable-use policies and for applicable law.

## Agent contract

| Concern | Specification |
| --- | --- |
| Channel | Telegram long-polling via `python-telegram-bot` v21+ on Python 3.11+. |
| Compute | Biohub ([`biohub.ai`](https://biohub.ai/learn/getting-started)) for folding; Boltz ([`api.boltz.bio`](https://api.boltz.bio/docs/)) for structure, binding, and design. |
| Bioscreen | Before GPU or paid API calls: `PASS`, `REVIEW`, or `BLOCK`. Unambiguous DNA or RNA is screened with local IBBIS `commec` (thin MIT packs, `--skip-tx` in v1). Amino-acid paths skip `commec` and do not reverse-translate. Tool-down fails closed (`BLOCK`). |
| Success payload | One `reply_photo` with a 3C caption written for physician and patient readers. No diagnosis or drug claims. |
| Literature | `/research` → one Markdown document (findings + Harvard references, ≤5 preprints) via Europe PMC. Social (X) signal is deferred and stated as unavailable. |
| Artifacts | mmCIF and design `candidates.csv` remain on the chat context card; `/download` sends them as documents. |
| Context | `/load` builds a formal card from natural language without GPU use. Bare `/esm`, `/boltz`, and `/design` consume that card. |
| Biometrics | `/onboard` stores secret age, sex, weight, and height on the card. `/load` shows only Patient: on file or incomplete — never raw values. |
| Patient files | `/note` appends session notes to `patient_files[]`, separate from biometric secrets. Bodies are not shown in `/load` or list output. |
| Privacy | Biometric secrets and patient files never enter language-model prompts, `/research` Markdown, captions, or Discord mirrors in v1. |
| Replay | `/view` returns the cached photo and caption when the new card fingerprint matches a prior completed run. Cache is chat-session only and uses no GPU. Fingerprints exclude patient secrets and patient files. |
| Spend gate | `/design` estimates cost and waits. `/confirm` starts design. `/cancel` aborts. |

Dummy sequence for documentation only: `MKTIIALSYIFCLVFA`.

## Commands

| Command | Action |
| --- | --- |
| `/start` `/help` | Introduction and research-use notice. |
| `/esm <sequence>` | Biohub ESMFold2 fold; returns photo and caption. |
| `/boltz <sequence>` | Boltz structure prediction; returns photo and caption. |
| `/boltz <sequence> <smiles>` | Boltz structure and binding; returns photo and caption. |
| `/design <sequence>` `[n]` | Queues a design job with cost estimate (API floor 10 molecules ≈ US$0.25; cap 100). Requires `/confirm`. |
| `/load <nl>` | Parses intent into a context card without GPU use. |
| `/load` | Shows the current card (Patient: on file / incomplete only; no secrets or note bodies). |
| `/load clear` | Clears the card, session cache, stashed files, biometrics, and patient files. |
| `/view` | Replays the stored photo and caption for a matching completed card. |
| `/download` | Sends the last-run CIF and, for design, the CSV. |
| `/confirm` | Runs the pending design job; returns a ligand-grid photo and caption. |
| `/cancel` | Aborts the pending design job or stops an active onboard Q&A. |
| `/research <topic>` | Europe PMC preprint brief → Markdown document with Harvard references (≤5). |
| `/onboard` | Collects biometric secrets one question at a time. |
| `/onboard status` | Complete or incomplete — no raw values. |
| `/onboard clear` | Clears biometric secrets and patient files. |
| `/note` | If a patient exists, saves the next message to patient files. |
| `/note list` | Shows patient-file count only. |
| `/note clear` | Clears patient files; biometric secrets unchanged. |

If image render fails, the caption is still sent as text.

## Design flow

1. Optional: `/load find me an inhibitor for KRAS G12C GDP` builds a card without calling GPU. Bare `/design` then uses the card sequence.
2. `/design <sequence> [n]` validates input, estimates cost, and stores a pending job. It does not start compute.
3. The confirm card shows molecule count, estimated cost in US dollars, and the research disclaimer. Reply `/confirm` to spend or `/cancel` to stop.
4. `/confirm` runs Boltz small-molecule design and returns one RDKit ligand grid with a 3C caption. CIF and CSV remain on the card for `/download`.

Candidates are ranked in silico only. A covalent design request without an explicit bonds payload returns a clear client or API error. Version 1 does not invent warheads.

## Credentials

Three environment variables are required:

1. `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
2. `BIOHUB_API_TOKEN` — from the [Biohub developer console](https://biohub.ai/developer-console/api-keys)
3. `BOLTZ_API_KEY` — from the [Boltz API console](https://api.boltz.bio/console) (header `x-api-key`)

Optional:

- `TELEGRAM_ALLOWED_USER_ID` — restrict the bot to one Telegram user
- `COMMEC_BIN` / `COMMEC_TIMEOUT_SEC` — local IBBIS `commec` for DNA/RNA bioscreen (fail-closed if missing)
- `DISCORD_WEBHOOK_URL` — optional outbound `/research` TLDR mirror (unset = disabled; never echoes the URL)

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
  docs/          # FEATURE-*, VOICE.md, COPY-*, TEMPLATE-research.md, REFUSE-bioscreen.md
  src/
    bot.py
    context_card.py    # /load → formal card
    card_cache.py      # fingerprint + /view
    downloads.py       # CIF/CSV stash
    bioscreen.py       # PASS / REVIEW / BLOCK pre-GPU gate
    research_client.py # Europe PMC
    research_md.py     # Harvard brief render
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

**Literature:** Europe PMC search REST only for `/research`. bioRxiv native keyword API and OpenAlex are out of scope for v1.

**Bioscreen:** Local open-source IBBIS [`commec`](https://github.com/ibbis-bio/common-mechanism) with MIT [`commec-databases`](https://github.com/ibbis-bio/commec-databases) packs. Sequences are written to a temporary FASTA on the host; nothing is uploaded to IBBIS.

## Safety

Sequences use a validated alphabet and a default protein length cap of 800 residues. DNA and RNA requests are gated with `PASS` / `REVIEW` / `BLOCK` before compute; refuse copy never includes scores or internals that teach bypass. Optional user allowlisting is supported. API failures return a short user-facing error without stack traces in chat. Help text and handlers refuse pathogen design, reverse genetics, synthesis planning, wet-lab protocols, and diagnosis or dosing from biometrics or patient files.
