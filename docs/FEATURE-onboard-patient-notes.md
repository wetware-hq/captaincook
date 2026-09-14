# Feature add-on: patient notes + embeddings (NLP)

**Status:** Proposed 2026-09-14 · amended (user: prefer embedding / similar for NLP)  
**Depends on:** `/onboard` patient secrets (live)  
**Owners:** biostrategist · biomodels · biolang

## Goal

Accept longer patient notes as secrets, and use **embeddings (or equivalent similarity)** for any NLP over them — not keyword scans, not an LLM “reading” the note in-chat for v1.

## Minimum Idiot Index

| Choice | Lock |
| --- | --- |
| Ingest | `/note <text>` / `/note append <text>` / `/note clear` (same UX as before) |
| Cap | **2000** Unicode chars on the raw buffer |
| Raw storage | `patient.notes` stays **secret** in session `user_data` only — never echoed on `/load` |
| NLP path | On save/append: embed once → store `patient.notes_embedding` (vector + model id + dim) |
| Similarity | Cosine (or API-native) similarity only for retrieval / “match this brief to note” — no bag-of-words on the note body |
| Show | `/load`: `Notes: on file` / `none`; never vector dump, never body |
| Fingerprint / Discord / research.md / download | Exclude `notes` **and** `notes_embedding` |
| Fail | Embed API down → keep raw secret, set `notes_embedding: null`, status `Notes: on file (embed pending)` — do not block `/onboard` biometrics |
| Not v1 | Local fine-tuned embedder; RAG chat over notes; sending notes to Discord; KMS |

## Why embeddings

User lock: prefer embedding (or similar) for NLP so the agent can relate notes to `/research` / card context by **similarity**, without putting note prose into captions, prompts that leak, or brittle keyword rules.

## Embed client (v1 pick)

Single hosted embed API already in the stack if available; otherwise one small HTTP embed endpoint via env (`EMBED_API_URL` + key). **One model id**, fixed dim, documented in config. No multi-model roulette.

Idiot Index: one `embed(text) -> list[float]` helper in `src/patient_embed.py`.

## Data shape

```
patient:
  secret: true
  …
  notes: str | null              # raw, secret, session-only
  notes_embedding:
    model: str
    dim: int
    vector: [float, …] | null
    updated_at: iso8601
```

## Acceptance

1. `/note …` stores raw secret + embedding when embed API is up.  
2. Similarity helper returns a score against a query string without logging the note body.  
3. `/load` never prints notes or vectors.  
4. Clear wipes raw + embedding together.

## Split

- Spec — **biostrategist**  
- `/note` + embed hook + exclude from fingerprint — **biomodels**  
- Status / refuse copy — **biolang**
