# `/note` copy (locked)

**Owner:** biolang  
**Cadence:** docs/VOICE.md  
**Two stores — never merge in user-facing text:**
1. **Biometric secrets** — from `/onboard` (`patient`)
2. **Patient files** — from `/note` (`patient_files[]`)

Never say “patient data” for either. Never echo biometric values or full note bodies in status/captions/Discord/research.

## Arm

```
Send your note in the next message. It will be saved to patient files on this card. Biometric secrets from /onboard are separate and are not changed.
```

## Saved

```
Note saved to patient files ({n} on file). Biometric secrets are unchanged.
```

## List (count only)

```
Patient files on this card: {n}. Contents are not shown. Biometric secrets are separate.
```

Zero:

```
No patient files on this card. Biometric secrets, if any, are separate.
```

## Clear files only

```
Patient files have been cleared. Biometric secrets are unchanged.
```

## Refuse — no patient on card

```
This request cannot proceed. There is no patient on the current card. Complete /onboard first, then use /note to add patient files. Biometric secrets and patient files are separate stores.
```

## Refuse — note too long

```
This note is too long. Please shorten it to 2000 characters or fewer and send it again.
```

## Refuse — LM / diagnose from notes or biometrics

```
This request cannot be fulfilled. Patient files and biometric secrets stay on this chat’s card for research context only. They are not sent to language models, research briefs, or Discord, and this bot does not diagnose from them.
```

## Do not say

- “Patient data saved.”  
- “Your age/weight/…” (any biometric echo)  
- Full note body in the ack  
- That notes will be “analysed” or “embedded” in v1
