# Captain Cook

<img src="docs/cook.jpg" width="280" alt="Captain Cook">

Research-use Telegram agent for protein structure prediction and ligand design. Wetware Sydney.

## Abstract

Captain Cook accepts a protein sequence or a short natural-language request and returns a single result unit: one image and one clinically readable caption. Folding is performed with Biohub ESMFold2. Structure prediction, binding scores, and small-molecule design use Boltz (`boltz-2.1` and the design API). All scores are computational estimates. The agent does not diagnose disease, recommend therapy, or plan synthesis or wet-lab work. Operators remain responsible for Biohub and Boltz acceptable-use policies and for applicable law.

## Agent contract

| Concern | Specification |
| --- | --- |
| Channel | Telegram long-polling via `python-telegram-bot` v21+ on Python 3.11+. |
| Compute | Biohub ([`biohub.ai`](https://biohub.ai/learn/getting-started)) for folding; Boltz ([`api.boltz.bio`](https://api.boltz.bio/docs/)) for structure, binding, and design. |
| Success payload | One `reply_photo` with a 3C caption written for physician and patient readers. No diagnosis or drug claims. |
| Artifacts | mmCIF and design `candidates.csv` remain on the chat context card; `/download` sends them as documents. |
| Context | `/load` builds a formal card from natural language without GPU use. Bare `/esm`, `/boltz`, and `/design` consume that card. |
| Replay | `/view` returns the cached photo and caption when the new card fingerprint matches a prior completed run. Cache is chat-session only and uses no GPU. |
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
| `/load` | Shows the current card. |
| `/load clear` | Clears the card, session cache, and stashed files. |
| `/view` | Replays the stored photo and caption for a matching completed card. |
| `/download` | Sends the last-run CIF and, for design, the CSV. |
| `/confirm` | Runs the pending design job; returns a ligand-grid photo and caption. |
| `/cancel` | Aborts the pending design job. |

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

Optional: `TELEGRAM_ALLOWED_USER_ID` restricts the bot to one Telegram user. Missing required variables cause an immediate, clear exit.

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
  docs/          # feature specs, VOICE.md, RENDER-seed.md
  src/
    bot.py
    context_card.py    # /load → formal card
    card_cache.py      # fingerprint + /view
    downloads.py       # CIF/CSV stash
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

## Safety

Sequences use a validated amino-acid alphabet and a default length cap of 800 residues. Optional user allowlisting is supported. API failures return a short user-facing error without stack traces in chat. Help text and handlers refuse pathogen design, reverse genetics, synthesis planning, and wet-lab protocol requests.
