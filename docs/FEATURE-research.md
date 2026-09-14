# Feature: `/research <topic>` → Markdown + Harvard cites

**Status:** Locked 2026-09-14 (Minimum Idiot Index)  
**Owners:** biostrategist (spec) · biomodels (wire) · bioresearch (lit path) · biolang (md template)  
**Depends on:** Telegram document send; research-use voice  
**Out of scope v1:** X/Twitter scrape; RAG; vector DB; bioscreen on topic text; native bioRxiv keyword API; multi-channel

## Goal

Given a natural-language research topic, return **one** Markdown document with the highest-signal, up-to-date preprint hits (bioRxiv-first), capped cites, Harvard reference list. No GPU. Fail-closed if the lit API is down.

## Minimum Idiot Index decisions (locked)

| Choice | Lock |
| --- | --- |
| Lit client | **Europe PMC** only (single HTTP client). Filter to bioRxiv / medRxiv (and preprint servers Europe PMC exposes). Do **not** use bioRxiv’s native API for keywords (date/DOI only). |
| OpenAlex | Deferred — second client is Idiot Index. Revisit only if Europe PMC coverage fails acceptance. |
| X | **Deferred.** Do not scrape. If no non-login public signal exists, omit X and state in one line that social signal was not available. Never invent “highest signal” from an empty scrape. |
| Ranking | Recency first (publication / first-online date desc), then Europe PMC relevance as tie-break. Cap **5** primary papers. |
| Output | One `.md` file → Telegram `reply_document`. Caption = one-line TLDR + research-use notice. |
| Bioscreen | **Off** for topic text (not a sequence). Research-use disclaimer only. |
| Synthesis | Short findings body: full sentences, claim → evidence pointing at cites. No fabricated papers. If zero hits → say so and send empty findings + no fake refs. |

## Command

```
/research <natural language topic>
```

- Missing topic → short usage help.  
- Topic length cap (e.g. 300 chars) → refuse overlong.  
- Timeout / HTTP error / empty parse → fail-closed refuse (biolang string); **no** partial invented lit.

## Europe PMC query (illustrative)

- Endpoint: Europe PMC search REST (JSON).  
- Query shape: user topic + source filter for bioRxiv (and medRxiv if available).  
- `pageSize=5` (or fetch a small page and truncate to 5 after sort).  
- Fields needed for Harvard: authors, year, title, journal/server, DOI (or PMCID/URL).

Exact URL params live in `src/research_client.py` — keep one function `search_preprints(topic) -> list[Record]`.

## Markdown shape (biolang locked)

Canonical template, Harvard rules, captions, and refuse strings: **`docs/TEMPLATE-research.md`**.  
Wire that file as-is. If X later lands, replace only the Social signal line with 0–3 links — never pad.


## Citations / DOIs (locked 2026-09-14)

- Harvard reference list at the **bottom** of the Markdown.
- Every Reference line **must include a DOI** as `https://doi.org/{doi}` when Europe PMC provides one.
- Prefer selecting the top ≤5 hits that **have DOIs**; do not invent DOIs.
- If fewer than one DOI-bearing hit remains → honest empty references (no fake cites).

## Acceptance

1. `/research KRAS G12C covalent inhibitors` → document with ≤5 bioRxiv-ish cites, Harvard list, non-empty findings or honest empty.  
2. Lit API down → refuse, no document with fake cites.  
3. No X content claimed when X is deferred.  
4. No call to Biohub/Boltz/commec.  
5. Voice: full sentences; Proper English per VOICE.md.

## Split

- Spec — **biostrategist** (this file)  
- Europe PMC client + `/research` handler + send document — **biomodels**  
- Findings/disclaimer/empty/X-omitted strings — **biolang**  
- Coverage/ranking sanity — **bioresearch**
