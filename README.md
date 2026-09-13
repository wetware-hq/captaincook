# captaincook

<img src="docs/cook.jpg" width="280" alt="Captain Cook">

"I've been shipping since 1770" 🇬🇧🛳️

🪪 Head Engineer of Wetware Sydney

Research-use Telegram bot that folds protein sequences, scores ligand binding, and (with confirm) runs Boltz small-molecule design via **official hosted APIs**:

- **Biohub** ESMFold2 / ESMC — [`biohub.ai`](https://biohub.ai/learn/getting-started)
- **Boltz** structure_and_binding (`boltz-2.1`) — [`api.boltz.bio`](https://api.boltz.bio/docs/)

Python 3.11+. Long polling with `python-telegram-bot` v21+.

> **Disclaimer:** Research use only. Not for clinical decisions. This bot does **not** provide pathogen design, reverse-genetics, synthesis planning, or wet-lab protocols. Users are responsible for complying with Biohub and Boltz acceptable-use policies and applicable law.

## Commands

| Command | Action |
| --- | --- |
| `/start` `/help` | Short intro + research-use notice |
| `/esm <sequence>` | Biohub ESMFold2 → one photo + 3C caption |
| `/boltz <sequence>` | Boltz-2.1 structure only → one photo + 3C caption |
| `/boltz <sequence> <smiles>` | Boltz-2.1 structure + binding → one photo + 3C caption |
| `/design <sequence>` | Boltz small-molecule design confirm card (cost estimate; then `/confirm`) |
| `/design <sequence> <n>` | Same; n molecules (API minimum 10 ≈ US$0.25; cap 100) |
| `/load <nl>` | Parse a request into a context card (no GPU). Bare `/esm` `/boltz` `/design` then use the card sequence |
| `/load` | Show current card |
| `/load clear` | Drop card, cache, and stashed files |
| `/view` | Replay the stored photo + caption for a matching completed card (no GPU) |
| `/download` | Send last-run CIF (and design CSV) from the current card |
| `/confirm` | Run pending `/design` job → ligand-grid photo + 3C caption (CIF/CSV via `/download`) |
| `/cancel` | Abort pending design job |

Example dummy sequence (README only): `MKTIIALSYIFCLVFA`

Successful slash results are **one** Telegram photo with a 3C caption. CIF and design CSV stay on the card — pull them with `/download`. If image render fails, the caption still sends as text. In-silico scores only — not validated inhibitors; no synthesis/wet-lab guidance.

### Design confirm flow

1. Optional `/load find me an inhibitor for KRAS G12C GDP covalent` — context card only (no GPU). Then bare `/design` uses the card.
2. `/design <protein-sequence> [n]` — validates sequence, estimates cost, stores a pending job (does **not** start GPU yet).
2. Confirm card shows n, estimated US$, and disclaimer. Reply `/confirm` to spend or `/cancel` to abort.
3. `/confirm` calls `BoltzClient.design_small_molecules` (biomodels wrapper) and replies with one RDKit ligand-grid photo + 3C caption. CIF and `candidates.csv` stay on the card for `/download`.
4. Results are ranked in-silico candidates only — research-use; not validated inhibitors; no synthesis/wet-lab text.

`covalent=true` without an explicit bonds payload surfaces a clear API/client error (v1 does not invent warheads).

## Prerequisites — three secrets

1. **Telegram** — talk to [@BotFather](https://t.me/BotFather), create a bot, copy the token → `TELEGRAM_BOT_TOKEN`
2. **Biohub** — create a key at [Developer Console → API keys](https://biohub.ai/developer-console/api-keys) → `BIOHUB_API_TOKEN`
3. **Boltz** — create a key at [API Console](https://api.boltz.bio/console) → `BOLTZ_API_KEY` (sent as `x-api-key`)

Optional: `TELEGRAM_ALLOWED_USER_ID` (your numeric Telegram user id) to lock the bot to one user.

## Local setup

```bash
cd captaincook
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with the three secrets
python -m src.bot
```

Missing required env vars exit immediately with a clear message (no silent crash).

## Docker

```bash
cd captaincook
docker build -t captaincook .
docker run --rm --env-file .env captaincook
```

## Project layout

```
captaincook/
  README.md
  .env.example
  .gitignore
  requirements.txt
  Dockerfile
  docs/
    FEATURE-boltz-inhibitor-nl-v1.md
    FEATURE-photo-png-from-results.md
    RENDER-seed.md
  src/
    __init__.py
    bot.py                   # handlers + polling entrypoint
    context_card.py          # /load NL → formal context card
    downloads.py             # durable CIF/CSV stash for /download
    card_cache.py            # fingerprint + /view result cache
    biohub_client.py         # ESMFold2 + ESMC fallback
    boltz_client.py          # structure_and_binding + design facade
    small_molecule_design.py # biomodels design/ADME wrapper
    result_photo.py          # RDKit + Pillow design-grid PNG
    photo.py                 # thin helpers to attach result PNGs
    structure_photo.py       # seed: mmCIF → PNG (PyMOL / Mol*)
    intent.py                # legacy NL parse helpers (unused by live slash flow)
    targets.py               # curated KRAS resolve + mutations
    config.py                # env + sequence validation
```

## API notes (verified against live docs)

**Biohub** (`pip install esm`):

```python
from esm.sdk.forge import SequenceStructureForgeInferenceClient, ESMCForgeInferenceClient
# url="https://biohub.ai", token=BIOHUB_API_TOKEN
# ESMFold2 model: esmfold2-fast-2026-05  →  client.fold_all_atom(...)
# ESMC model:     esmc-6b-2024-12
```

**Boltz** (`pip install boltz-api`):

```python
from boltz_api import Boltz
client = Boltz(base_url="https://api.boltz.bio", api_key=BOLTZ_API_KEY)
prediction = client.predictions.structure_and_binding.start(model="boltz-2.1", input={...})
# poll with .retrieve(id); download via client.experiments.download_results(...)
```

Docs: [predictions](https://api.boltz.bio/docs/guides/predictions/), [authentication](https://api.boltz.bio/docs/guides/authentication/).

## Safety

- Amino-acid alphabet validated; sequence length capped (default **800**).
- Optional allowlist via `TELEGRAM_ALLOWED_USER_ID`.
- API failures return a short user-facing error (no stack traces in chat).
- Help text and handlers refuse pathogen / reverse-genetics / synthesis / wet-lab requests.
