# Feature: `/app` — case-conference packet + optional live HTTPS view

**Status:** Locked 2026-09-20 (Minimum Idiot Index)  
**Owners:** biostrategist · biomodels · biolang · bioplatform (deploy/TTL) · editor (visual) · bioresearch  
**Supersedes user-facing name:** `/board` → `/app` (alias kept one release)

## Goal

Realtime **patient card → conference packet**: Telegram Markdown (same as today’s `/board`) **plus** optional colleague-share TTL HTTPS static page for the room screen. Publication modality: professional, simple/clean/minimal, white background, serif, scientific graphing. Research-use only. No diagnosis.

## Commands

| Command | Behavior |
| --- | --- |
| `/app` | Primary — fresh redacted snapshot |
| `/app update` | Strict alias of `/app` |
| `/board` | Strict alias of `/app` (one release) |
| `/board update` | Strict alias of `/app` |

## Projection (redaction parity — ship first)

Identical to locked `/board`:
- Case context, evidence Harvard, trials themes, non-secret measures, design ids  
- Secrets/biometrics: **counts only**  
- Never Discord-mirror if identifiers present  
- Research-use banner always  

## Live view (v1 after parity)

- **Static HTML+JS** artifact — no patient server DB  
- Layout: one column, white, serif, minimal chrome  
- **Vega-Lite** charts for non-secret time-series only: `hr`, `spo2`, `temp_c`, `glucose_mmol`  
- Evidence/trials: plain Harvard sections, not charts  
- Host: Cloudflare Pages/Workers or Vercel preview  
- **Signed URL** (7-day default / 30-day max); fail-closed if deploy creds missing  
- Telegram reply: MD packet + optional “Open live view” link  




## Style guide — live view (locked 2026-09-20 — user)

**Minimise text.** Where text is required, use **complete short sentences** and clear concise prose. A clinician or scientist must **grok** the case in one scroll.

| Element | Rule |
| --- | --- |
| Layout | White, one column ≤42rem, serif body; sans for nav only; simple/clean/minimal |
| Evidence / Lab prose | ≤3 claim bullets + Harvard at section bottom; one-line section intros only |
| Empty | “None yet.” |
| Charts | Vega-Lite non-secret vitals; thin muted lines; no clutter |
| Telegram caption | 1–2 sentences + link + expiry — page carries detail |
| Out | Dark mode, decorative art, Cook launch art on this page, text walls |

Visual lock from @editor applies. COPY from @biolang TEMPLATE-app.

## Merge clinic + lab into live view (locked 2026-09-20 — user)

One HTTPS page for **clinicians and scientists** — not two apps.

| Source | Section | Audience |
| --- | --- | --- |
| `clinic.md` | **Clinical** — Evidence (peer-reviewed), Meeting minutes, note stubs | Clinicians |
| `lab.ipynb` | **Laboratory** — structures, ligand/binder summaries + image refs, preprint `/research` | Scientists |
| Card snapshot | Case context, Measurements (Vega-Lite non-secret), open questions | Both |

**Rules**
- Top anchor nav: Clinical | Laboratory  
- White / serif / minimal; one research-use banner  
- **No tone bleed:** preprints stay Laboratory; peer-reviewed Evidence stays Clinical  
- Strip secrets / secret measures / note bodies (counts only)  
- Binder/ligand: ranked summary + image refs; CIF via download; up to 2 mmCIF in Mol* Structures on live deploy  
- Missing file → honest “none yet”  
- Render at `/app` time from sorter files — no new DB  
- TTL / revoke / redaction unchanged; Discord still no identifier links  

## Lifetime for colleague share (locked 2026-09-20 — user)

Minutes-only TTL is too short for monitoring/discussion in chat.

| Rule | Lock |
| --- | --- |
| Default lifetime | **7 days** |
| Hard max | **30 days**, then expire |
| Regenerate `/app` | Refresh same slug **or** new link + retire old |
| `/app revoke` | Kill link early |
| Projection | Redacted only — **never** secret values in HTML or URL |
| Banner | Research-use; **not a medical record** |
| Sharing | Paste HTTPS in Telegram/colleague chat; MD packet stays in bot thread |

Optional later: access code in caption (not in URL path).

## Out of scope

LLM layout; secrets in URL; permanent public apps; Chart.js/D3-from-scratch v1; diagnosis UI; Discord of conference links with PHI.

## Ship order

1. Rename + aliases + redaction parity tests  
2. Static HTML renderer (white/serif/minimal + Vega-Lite)  
3. TTL deploy + Telegram link  
4. README/HELP  

## Acceptance

1. `/app` ≡ `/board` content redaction.  
2. Live view omits all secret values.  
3. Missing deploy creds → MD only + clear refuse for link (not blank).  
4. HELP specialty-agnostic; `/board` documented as alias.

## Split

- Spec — biostrategist  
- Wire rename + HTML + deploy client — biomodels  
- TTL/host secrets — bioplatform  
- TEMPLATE-app / COPY — biolang  
- Visual pass — editor  
