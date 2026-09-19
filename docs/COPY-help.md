# `/help` and `/start` copy (locked)

**Owner:** biolang  
**Parity:** closes HELP language gap vs README dual `/design`

## `/start`

```
This is a research bot for Biohub, Boltz, and BindCraft models. Send /help for the list of commands. It predicts protein structure and binding, proposes in-silico small-molecule ligands, and designs in-silico protein binders after /design and /confirm. It does not offer clinical advice, and it does not guide laboratory work.
```

## HELP intro

```
*Research use only.* This bot predicts protein structure and binding via Biohub and Boltz, proposes in-silico small-molecule ligands via Boltz, and designs in-silico protein binders via BindCraft (optional Modal compute).
```

## HELP design cost blurb

```
Ligand design (/design ligand) requires at least ten molecules (about US$0.25) and at most one hundred. Binder design (/design binder) defaults to five designs and caps at twenty; jobs can take tens of minutes to a few hours. The confirm card states mode, count, and any cost estimate before work begins. Candidates are computer suggestions only. They are not validated inhibitors or therapeutics, and this bot does not advise synthesis or laboratory work.
```

## HELP `/trials` one-liner (locked)

```
/trials [condition or gene variant] — Shortlist public ClinicalTrials.gov studies for the card or query. Eligibility themes only. Research use only; human review required; this bot does not enroll.
```

## HELP `/app` + aliases (locked — TEMPLATE-app.md)

```
/app — Assemble a Markdown case-conference packet from the current card and patient stores. Optional short-lived web view when configured. Research use only; not a clinical record.
/app update — Same as /app (fresh snapshot; not an incremental merge).
/board — Alias of /app for one release.
/board update — Alias of /app for one release.
```

## HELP `/measure` one-liner (locked)

```
/measure — Paste patient observations onto the current card (HR, BP, weight_kg=…, optional secret). /measure list shows keys; secret values are never shown. Research use only; not a diagnosis.
```

## HELP `/measure` commands (locked)

```
/measure — Arm the next message as a measurement paste.
/measure <lines> — Parse a short paste immediately.
/measure list — List keys and counts. Secret measures appear only as a count.
/measure clear [key|all] — Clear one key series or all measurements on this card.
```

## `/measure` v1.1 examples (HELP)

```
Messy one-liners are OK when they clearly name a vital (e.g. HR was 72, BP 120 over 80). Free paragraphs are not parsed.
```
