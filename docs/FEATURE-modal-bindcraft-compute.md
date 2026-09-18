# Feature: Modal compute for `/design binder` (BindCraft)

**Status:** Locked 2026-09-19 (Minimum Idiot Index)  
**Owners:** biostrategist · biomodels (ops/wire) · bioresearch · biolang (refuse copy)  
**Depends on:** FEATURE-bindcraft dual-mode `/design binder`

## Decision

**Modal = GPU compute only.** Durable patient store stays on the poller host (`clinic.md` / `lab.ipynb` / `search.json` / secrets). Artifacts sync **back** to the poller after the job; Modal is not the system of record for patient files.

## What we need

| Need | Purpose |
| --- | --- |
| Modal account + token | Deploy/run jobs (`MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` or equivalent) |
| GPU image | BindCraft + AF2 (and deps) baked or pulled at start |
| Persistent **volume** | Weights under BindCraft home; optional scratch for runs — **not** clinic/secrets |
| Job entrypoint | Poller calls Modal with target CIF/seq + optional hotspot + N → returns ranked binders + FASTA/CIF bytes (or signed download URLs with short TTL) |
| Timeouts | Hard wall clock; fail-closed refuse (biolang) — no partial invented binders |
| Secrets on Modal | Only Modal creds + whatever the job needs for BindCraft; **no** Telegram token, **no** biometrics, **no** `patient_files` |
| Sync-back | Poller writes artifacts into card `last_run` + emits sorter event → `lab.ipynb` / `search.json` `binder:` |

## Explicit non-goals

- Storing `clinic.md` / biometrics / notes on Modal  
- Discord mirror of binder jobs  
- Using Modal for `/design ligand` (Boltz stays hosted Boltz API) in v1  

## Acceptance

1. With Modal creds + volume weights: `/design binder` → `/confirm` → binders on Telegram + local lab store.  
2. Modal down/timeout → same refuse shape as missing `BINDCRAFT_HOME`.  
3. No patient PHI leaves the poller host.

## Split

- Spec — biostrategist  
- Modal app + poller client — biomodels  
- Refuse strings — biolang  
