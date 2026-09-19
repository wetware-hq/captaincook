"""Curated target sequences for NL small-molecule design (research-use only)."""

from __future__ import annotations

from dataclasses import dataclass, field

# Human KRAS isoform B (KRAS4B) UniProt P01116-2, catalytic domain residues 1–169.
# Cached so UniProt downtime does not block the confirm card.
_KRAS4B_FULL = (
    "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAG"
    "QEEYSAMRDQYMRTGEGFLCVFAINNTKSFEDIHHYREQIKRVKDSEDVPMVLVGNKCDL"
    "PSRTVDTKQAQDLARSYGIPFIETSAKTRQGVDDAFYTLVREIRKHKEKMSKDGKKKKKK"
    "SKTKCVIM"
)
KRAS_CATALYTIC_1_169 = _KRAS4B_FULL[:169]
assert len(KRAS_CATALYTIC_1_169) == 169
assert KRAS_CATALYTIC_1_169[11] == "G"  # G12

KRAS_ACCESSION = "P01116"
KRAS_ISOFORM = "P01116-2"

# Curated KRAS Switch-II hotspot (human numbering on catalytic 1–169).
# Applied only when NL names Switch-II / Switch 2 / SII — never LM-invented.
# Inclusive 60–76 → list(range(60, 77)).
KRAS_SWITCH_II_POCKET: dict[str, list[int]] = {
    "A": list(range(60, 77)),
}
HOTSPOT_SOURCE_KRAS_SWITCH_II = "kras_switch_ii_fixture"

# Public reference SMILES for pocket finding (sotorasib-class); card display only
# until confirm. Research-use in-silico reference — not a synthesis instruction.
SOTORASIB_SMILES = (
    "CC1CN(CCN1C2=NC(=O)N(C3=NC(=C(C=C32)F)C4=C(C=CC=C4F)O)"
    "C5=C(C=CN=C5C(C)C)C)C(=O)C=C"
)

def is_kras_gene(gene: str | None) -> bool:
    if not gene:
        return False
    return gene.upper().replace("-", "") == "KRAS"


def kras_switch_ii_pocket_copy() -> dict[str, list[int]]:
    """Fresh copy of the curated Switch-II residue map (chain A, 60–76)."""
    return {k: list(v) for k, v in KRAS_SWITCH_II_POCKET.items()}


def pocket_residues_to_hotspot_list(
    pocket: dict[str, list[int]] | None,
) -> list[str] | None:
    """Flatten pocket_residues to BindCraft-style hotspot tokens (e.g. A60)."""
    if not pocket:
        return None
    out: list[str] = []
    for chain, residues in pocket.items():
        for r in residues:
            out.append(f"{chain}{int(r)}")
    return out or None


_SUPPORTED_VARIANTS = {"WT", "G12C", "G12D", "G12V"}


@dataclass
class ResolvedTarget:
    sequence: str
    accession: str
    variant: str | None
    notes: str
    pocket_residues: dict[str, list[int]] | None = None
    reference_ligands: list[str] | None = field(default=None)


def _apply_g12_mutation(sequence: str, variant: str) -> str:
    if variant == "WT":
        return sequence
    aa = variant[-1]  # C / D / V
    if sequence[11] != "G":
        raise ValueError("Cached KRAS sequence does not have G at position 12.")
    chars = list(sequence)
    chars[11] = aa
    return "".join(chars)


def resolve(gene: str, variant: str | None) -> ResolvedTarget:
    """Resolve a curated gene (+ optional variant) to a protein sequence.

    Bare KRAS does **not** default to G12C — ``variant`` may be ``None``.
    """
    key = gene.upper().replace("-", "")
    if key != "KRAS":
        raise ValueError(
            f"Target {gene!r} is not curated yet (v1 supports KRAS only). "
            "Paste a sequence via the structure path, or wait for live UniProt."
        )
    if variant is not None and variant not in _SUPPORTED_VARIANTS:
        raise ValueError(
            f"Unsupported KRAS variant {variant!r}. Use WT, G12C, G12D, or G12V."
        )

    seq = KRAS_CATALYTIC_1_169
    notes_parts = [
        f"Cached human KRAS4B catalytic domain 1–169 (UniProt {KRAS_ISOFORM}).",
    ]
    pocket: dict[str, list[int]] | None = None
    refs: list[str] | None = None

    if variant is None:
        notes_parts.append("No variant applied (not silently defaulted to G12C).")
        accession = KRAS_ACCESSION
    elif variant == "WT":
        accession = KRAS_ACCESSION
        notes_parts.append("Variant: WT (no mutation).")
    else:
        seq = _apply_g12_mutation(seq, variant)
        accession = f"{KRAS_ACCESSION}+{variant}"
        notes_parts.append(f"Applied {variant} on residue 12.")

    # G12C: optional sotorasib-class reference ligand for ligand path.
    # Switch-II hotspot residues are NOT auto-attached here — only when NL
    # names Switch-II (see context_card.parse_load_text + FEATURE-kras-switch2).
    if variant == "G12C":
        refs = [SOTORASIB_SMILES]
        notes_parts.append(
            "Optional sotorasib-class reference ligand listed on confirm card."
        )

    return ResolvedTarget(
        sequence=seq,
        accession=accession,
        variant=variant,
        notes=" ".join(notes_parts),
        pocket_residues=pocket,
        reference_ligands=refs,
    )


if __name__ == "__main__":
    wt = resolve("KRAS", None)
    assert wt.variant is None
    assert wt.sequence[11] == "G"
    assert len(wt.sequence) == 169
    g12c = resolve("KRAS", "G12C")
    assert g12c.sequence[11] == "C"
    assert g12c.sequence[:11] == KRAS_CATALYTIC_1_169[:11]
    assert g12c.sequence[12:] == KRAS_CATALYTIC_1_169[12:]
    assert g12c.pocket_residues is None  # Switch-II only via NL phrase
    assert KRAS_SWITCH_II_POCKET["A"] == list(range(60, 77))
    g12d = resolve("k-ras", "G12D")
    assert g12d.sequence[11] == "D"
    g12v = resolve("KRAS", "G12V")
    assert g12v.sequence[11] == "V"
    bare_wt = resolve("KRAS", "WT")
    assert bare_wt.sequence == KRAS_CATALYTIC_1_169
    try:
        resolve("EGFR", None)
        raise SystemExit("FAIL: EGFR should not resolve")
    except ValueError:
        pass
    print("targets self-check passed")
    print(f"KRAS WT 1-169 ({len(wt.sequence)} aa): {wt.sequence[:10]}…{wt.sequence[-10:]}")
    print(f"G12C pos12={g12c.sequence[11]} accession={g12c.accession}")
