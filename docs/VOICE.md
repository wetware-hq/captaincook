# Bot voice — Proper English, Colonial cadence (clinical first)

**Status:** Locked direction 2026-09-12  
**Applies to:** all user-visible Telegram copy — `/start`, `/help`, small talk, errors, cards, 3C captions, `/download`, progress pings.

## Cadence (inspired by, not portraying, Captain James Cook)

Write as a careful expedition journal might: measured, exact, courteous, and complete. Prefer full sentences. Prefer plain truth over flourish.

**Do not** speak *as* Cook, narrate voyages, use nautical roleplay, first-person adventure, or period costume (“Ahoy”, “the Crown”, “my commission”). The historical cadence is flavour only.

## Priorities (in order)

1. **Clinical utility** — a physician or patient must grasp what happened and what it does *not* mean  
2. **Truth** — no overclaim; research-use limits stated clearly  
3. **Clarity** — one idea per sentence where possible  
4. **Proper English** — complete sentences; restrained vocabulary; avoid slang, emoji, and chat shorthand  

## Style rules

- Full sentences with terminal punctuation.  
- Prefer “This model predicts…” / “No structure file is available…” over fragments (“API error”, “No card”).  
- Keep technical terms when needed; gloss once in plain language.  
- Captions remain one short paragraph (Telegram ≤1024).  
- Errors: state what failed and what to do next, without blame.  
- No diagnosis, dosing, or treatment advice.

## Examples

| Avoid | Prefer |
| --- | --- |
| No card loaded. | No context card is loaded. Please use /load with a clear request, then run a job. |
| API error: timeout | The remote service did not finish in time. Please try again shortly. |
| Job started… | The structure prediction has begun. This may take several minutes. |
| Refused: pathogen… | This request cannot be fulfilled. The bot does not support pathogen design or related misuse. |

## 3C captions

Keep dual physician/patient clarity. Open with what the image shows; close with research-use limits. Cook cadence = composure and completeness, not archaic spellings (“shew”, “whilst” sparingly—prefer modern Proper English).

## Ownership

- **biostrategist:** VOICE.md + interpret.py caption refresh  
- **biomodels:** rewrite bot.py / context_card format_card / HELP /start / errors / progress to match; poller restart  
