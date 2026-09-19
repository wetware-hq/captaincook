# Feature: KRAS Switch-II curated hotspot map for `/design binder`

**Status:** Locked + wired 2026-09-19 (poller)  
**Owners:** biostrategist · biomodels · bioresearch · biolang (COPY-design confirm wording)  
**Depends on:** `/load` card; `/design binder`; never invent hotspots

## Goal

When the user names **Switch-II** (or Switch 2 / SII) on a **KRAS** card, fill `pocket_residues` from a **curated fixture table** — not from an LLM and not by guessing.

## Locks

| Rule | Lock |
| --- | --- |
| Gene | Only **KRAS** (including G12C / G12D / G12V / WT on the catalytic-domain fixture). |
| Phrase triggers | `switch-ii`, `switch ii`, `switch 2`, `sii` (case-insensitive). |
| Residue list | Curated: **60–76** inclusive (human KRAS numbering on the 1–169 catalytic domain). Stored as `pocket_residues["A"] = [60..76]` (or chain key used by BindCraft). |
| Confirm copy | Say hotspot residues came from the **KRAS Switch-II fixture map**, not “user-supplied numbers,” when the map filled them. |
| No match | Gene ≠ KRAS, or unknown pocket name → **target-wide** + existing HELP tip (residue numbers or target-wide). |
| Never | LM-invented residues; silent hotspot when parse fails. |

## First-success smoke (after wire)

Default binder smoke may use **n=1** with Switch-II map applied (or keep n=5 with longer wall — ops choice). Safety unchanged: 0-filter / timeout → clean refuse.

## Acceptance

1. `/load design a de novo protein binder to KRAS G12C at the Switch-II pocket` → card has residues 60–76.  
2. `/design binder` confirm names **binder** + Switch-II fixture map (not target-wide).  
3. Non-KRAS + “Switch-II” → target-wide, no invented list.  
4. COPY-design matches (biolang).

## Split

- Spec + residue table — biostrategist / bioresearch  
- Parse + card field — biomodels  
- Confirm wording — biolang  
