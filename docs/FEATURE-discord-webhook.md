# Feature: Discord outbound webhook (Captain Cook distribution v1)

**Status:** Locked 2026-09-14 (biostrategist)  
**Owners:** bioplatform (distribution) · biomodels (poller hooks) · biolang (voice reuse) · biostrategist (spec)  
**Depends on:** poller success paths that already produce a user-visible result unit  
**Out of scope v1:** Discord Bot Gateway; slash commands; reading Discord; inbound Discord → cook; WhatsApp; Matrix; webhook multipart file attach; mirroring refusals / bioscreen / spend cards

## Goal

Mirror selected Captain Cook **outbound** results into one Discord channel via an **incoming webhook**. No bot token, no always-on gateway. Operator sets a webhook URL; the poller POSTs JSON when a result is ready. Telegram remains the system of record.

## Minimum Idiot Index decisions (locked)

| Choice | Lock |
| --- | --- |
| Integration | Discord **incoming webhook** only (HTTP POST). Not a Discord Application/Bot. |
| Direction | **Outbound only.** Discord cannot invoke `/research` or other commands in v1. |
| Auth | Optional `DISCORD_WEBHOOK_URL`. Unset = no-op; Telegram unchanged. |
| Voice | **Reuse** the Telegram research-use caption / TLDR (@biolang). Do not invent a second Discord voice. |
| Payload | Plain `content` string, truncated to Discord’s **2000** char limit. No embeds in v1. |
| Fail policy | Discord POST failure **never** fails or delays the Telegram reply. Log and continue. |
| Secrets | Webhook URL is a secret. Never echo in chat, captions, or user-visible errors. |
| WhatsApp | Deferred until this webhook is live and accepted. |

## Triggers (v1)

**Only** after a **successful** `/research` on Telegram:

- Post: command tag + the same 1-line TLDR / research-use caption used on Telegram (plus a short note that the Markdown brief was delivered on Telegram).

Do **not** mirror in v1: `/esm` `/boltz` `/design` successes, refusals, bioscreen `REVIEW`/`BLOCK`, `/confirm` spend cards, or error text.

Expanding triggers is a later FEATURE amend — not silent scope creep.

## Config

```
DISCORD_WEBHOOK_URL=   # optional; empty = disabled
```

## Acceptance

1. With URL set: live `/research KRAS G12C covalent inhibitors` on Telegram also posts one short TLDR into the Discord channel (same voice as Telegram caption).  
2. With URL unset: Telegram behaviour unchanged; no Discord errors surfaced to the user.  
3. Discord outage / bad URL does not break Telegram delivery.  
4. Webhook URL never appears in user-visible messages.

## Operator need

A Discord channel **Incoming Webhook** URL from the operator before live mirror can be enabled.

## Follow-ups (not v1)

- Attach `.md` via webhook multipart  
- Mirror fold/design success captions  
- Interactive Discord bot (slash `/research`)  
- WhatsApp Cloud API  

## Split

- Spec lock — **biostrategist** (this file)  
- `discord_webhook.py` + env — **bioplatform**  
- Hook after `/research` success — **biomodels** (or bioplatform with biomodels review)  
- Caption/TLDR string reuse — **biolang** (no new Discord-only copy)
