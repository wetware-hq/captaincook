"""Formal context card for /load — rule-based NL parse, no GPU.

Schema v1 locked in docs/FEATURE-load-context-card.md.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .intent import (
    DEFAULT_N_DESIGNS,
    _extract_covalent,
    _extract_n_designs,
    _extract_target,
    _normalize_variant,
    _STATE_RE,
    _VARIANT_RE,
    has_design_intent,
    looks_like_aa_sequence,
    missing_design_fields,
    DesignRequest,
)
from .targets import (
    HOTSPOT_SOURCE_KRAS_SWITCH_II,
    is_kras_gene,
    kras_switch_ii_pocket_copy,
    resolve,
)

Intent = Literal["fold", "structure_binding", "small_molecule_design", "unspecified"]
SeqSource = Literal["cached_uniprot", "user_paste", "missing"]

CONTEXT_CARD_KEY = "context_card"
CARD_VERSION = 1
DEFAULT_MAX_USD = 0.50

_SMILES_HINT = re.compile(r"[=#@\[\]\\/+]")
_FOLD_RE = re.compile(r"\b(fold|esmfold|structure)\b", re.IGNORECASE)
_BIND_RE = re.compile(r"\b(bind(?:ing)?|complex|dock)\b", re.IGNORECASE)

# Phrase triggers for curated KRAS Switch-II hotspot map (FEATURE-kras-switch2-hotspot).
_SWITCH_II_RE = re.compile(
    r"\b(?:switch[\s-]*ii|switch[\s-]*2|sii)\b",
    re.IGNORECASE,
)


@dataclass
class ContextCard:
    version: int = CARD_VERSION
    raw_text: str = ""
    intent: Intent = "unspecified"
    gene: str | None = None
    variant: str | None = None
    uniprot: str | None = None
    sequence: str | None = None
    sequence_source: SeqSource = "missing"
    smiles: str | None = None
    state: str | None = None
    covalent: bool | None = None
    n_designs: int = DEFAULT_N_DESIGNS
    n_designs_clamped_from: int | None = None
    chemical_space: str = "enamine_real"
    max_usd: float = DEFAULT_MAX_USD
    pocket_residues: dict[str, list[int]] | None = None
    hotspot_source: str | None = None  # e.g. kras_switch_ii_fixture; never LM
    reference_ligands: list[str] | None = None
    missing_fields: list[str] = field(default_factory=list)
    created_at: str = ""
    last_run: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: MappingLike) -> "ContextCard":
        # Accept both flat (this module) and nested schema (FEATURE doc).
        if not data:
            raise ValueError("empty card")
        if "target" in data and isinstance(data["target"], dict):
            t = data["target"]
            lig = data.get("ligand") or {}
            des = data.get("design") or {}
            return cls(
                version=int(data.get("version") or CARD_VERSION),
                raw_text=str(data.get("raw_text") or ""),
                intent=data.get("intent") or "unspecified",
                gene=t.get("gene"),
                variant=t.get("variant"),
                uniprot=t.get("uniprot"),
                sequence=t.get("sequence"),
                sequence_source=t.get("sequence_source") or "missing",
                smiles=lig.get("smiles"),
                state=des.get("state"),
                covalent=des.get("covalent"),
                n_designs=int(des.get("n_designs") or DEFAULT_N_DESIGNS),
                n_designs_clamped_from=des.get("n_designs_clamped_from"),
                chemical_space=des.get("chemical_space") or "enamine_real",
                max_usd=float(des.get("max_usd") or DEFAULT_MAX_USD),
                pocket_residues=data.get("pocket_residues"),
                hotspot_source=data.get("hotspot_source"),
                reference_ligands=data.get("reference_ligands"),
                missing_fields=list(data.get("missing_fields") or []),
                created_at=str(data.get("created_at") or ""),
                last_run=data.get("last_run"),
            )
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


MappingLike = dict[str, Any]


def _infer_intent(text: str, smiles: str | None) -> Intent:
    if has_design_intent(text):
        return "small_molecule_design"
    if smiles or _BIND_RE.search(text):
        return "structure_binding"
    if _FOLD_RE.search(text):
        return "fold"
    return "unspecified"


def _extract_smiles(text: str) -> str | None:
    for tok in text.split():
        if _SMILES_HINT.search(tok) and not looks_like_aa_sequence(tok, min_len=3):
            if re.search(r"[A-Za-z]", tok) and len(tok) >= 2:
                return tok
    return None


def _extract_pasted_sequence(text: str) -> str | None:
    best: str | None = None
    for tok in text.replace(",", " ").split():
        if looks_like_aa_sequence(tok, min_len=10):
            seq = "".join(tok.split()).upper()
            if best is None or len(seq) > len(best):
                best = seq
    return best


def parse_load_text(text: str) -> ContextCard:
    """Parse NL into a context card. Never calls Biohub/Boltz. Never invents a sequence."""
    raw = (text or "").strip()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    smiles = _extract_smiles(raw)
    pasted = _extract_pasted_sequence(raw)
    gene = _extract_target(raw)
    variant_m = _VARIANT_RE.search(raw)
    variant = _normalize_variant(variant_m.group(1)) if variant_m else None
    state_m = _STATE_RE.search(raw)
    state = state_m.group(1).upper() if state_m else None
    covalent = _extract_covalent(raw)
    n_designs, clamped = _extract_n_designs(raw)
    intent = _infer_intent(raw, smiles)

    sequence: str | None = None
    source: SeqSource = "missing"
    uniprot: str | None = None
    pocket = None
    refs = None
    notes_missing: list[str] = []

    if pasted:
        sequence = pasted
        source = "user_paste"
    elif gene:
        try:
            resolved = resolve(gene, variant)
            sequence = resolved.sequence
            source = "cached_uniprot"
            uniprot = resolved.accession
            pocket = resolved.pocket_residues
            refs = resolved.reference_ligands
        except ValueError:
            notes_missing.append("sequence (gene not curated; paste an AA sequence)")
    else:
        notes_missing.append("target gene or amino-acid sequence")

    hotspot_source: str | None = None
    # Curated KRAS Switch-II map only — never LM-invent residues for other genes.
    if _SWITCH_II_RE.search(raw):
        if is_kras_gene(gene):
            pocket = kras_switch_ii_pocket_copy()
            hotspot_source = HOTSPOT_SOURCE_KRAS_SWITCH_II
        # Non-KRAS + Switch-II → leave pocket unset (target-wide); do not invent.

    missing = list(notes_missing)
    if intent == "small_molecule_design":
        req = DesignRequest(
            target=gene or "UNKNOWN",
            variant=variant,
            state=state,
            covalent=covalent,
            n_designs=n_designs,
            n_designs_clamped_from=clamped,
        )
        missing.extend(missing_design_fields(req))
    if intent == "structure_binding" and not smiles and not pasted:
        # ligand optional; sequence already covered
        pass

    return ContextCard(
        raw_text=raw,
        intent=intent,
        gene=gene,
        variant=variant,
        uniprot=uniprot,
        sequence=sequence,
        sequence_source=source,
        smiles=smiles,
        state=state,
        covalent=covalent,
        n_designs=n_designs,
        n_designs_clamped_from=clamped,
        pocket_residues=pocket,
        hotspot_source=hotspot_source,
        reference_ligands=refs,
        missing_fields=missing,
        created_at=now,
    )


def format_card(card: ContextCard, patient: dict[str, Any] | None = None) -> str:
    seq = card.sequence or "not yet assigned"
    if card.sequence and len(card.sequence) > 16:
        seq_show = f"{card.sequence[:8]}…{card.sequence[-8:]}"
    else:
        seq_show = seq
    target = card.gene or "not named"
    if card.variant:
        target = f"{target} {card.variant}"
    if card.uniprot:
        aa = f"{len(card.sequence)} amino acids" if card.sequence else "no sequence"
        target = f"{target} (UniProt {card.uniprot}, {aa})"
    elif card.sequence:
        target = f"{target} ({len(card.sequence)} amino acids)"

    if card.n_designs_clamped_from is not None:
        n_line = (
            f"{card.n_designs}; {card.n_designs_clamped_from} were requested, "
            "and the service minimum of ten will be used (about US$0.25)"
        )
    else:
        n_line = f"{card.n_designs} (the service minimum; about US$0.25)"

    if card.covalent is None:
        cov = "unspecified"
    elif card.covalent:
        cov = "requested"
    else:
        cov = "not requested"
    if card.missing_fields:
        missing = "These fields remain to be specified: " + ", ".join(card.missing_fields) + "."
    else:
        missing = "No required fields are missing."
    lines = [
        "This is the present context card. No computation has been started.",
        f"The intent is {card.intent.replace('_', ' ')}.",
        f"The target is {target}.",
        f"The sequence is {seq_show}. The source is {card.sequence_source.replace('_', ' ')}.",
        f"The ligand SMILES is {card.smiles or 'not set'}.",
        f"The nucleotide state is {card.state or 'not set'}.",
        f"Covalent design is {cov}.",
        f"The requested molecule count is {n_line}.",
        f"The chemical space is {card.chemical_space}.",
        f"The spending cap is US${card.max_usd:.2f}.",
        missing,
    ]
    if card.pocket_residues:
        if card.hotspot_source == HOTSPOT_SOURCE_KRAS_SWITCH_II:
            lines.append(
                "Hotspot residues from the KRAS Switch-II fixture map: "
                f"{card.pocket_residues}."
            )
        else:
            lines.append(f"Optional pocket residues: {card.pocket_residues}.")
    if card.last_run and card.last_run.get("interpretation"):
        lines.append("The last completed run was of kind " + str(card.last_run.get("kind") or "result") + ".")
        lines.append(card.last_run["interpretation"])
        files = card.last_run.get("files") or []
        names = [str(f.get("filename") or "") for f in files if isinstance(f, dict)]
        names = [n for n in names if n]
        if names:
            lines.append(
                "Stored files: " + ", ".join(names) + ". Send /download to retrieve them."
            )
    if patient is None:
        patient_line = "Patient: not on file."
    elif patient.get("complete") and patient.get("age_years") is not None:
        patient_line = "Patient: on file."
    elif any(patient.get(k) is not None for k in ("age_years", "sex", "weight_kg", "height_cm")):
        patient_line = "Patient: incomplete."
    else:
        patient_line = "Patient: not on file."
    lines.append(patient_line)
    lines.extend(
        [
            "Next, send /design, /boltz, or /esm. Send /load clear to discard this card and its stored files.",
            "These notes are for research. No inhibitor has been validated, and no synthesis is advised.",
        ]
    )
    return "\n".join(lines)




def attach_last_run(
    card: ContextCard,
    *,
    kind: str,
    interpretation: str,
    metrics: dict[str, Any] | None = None,
    run_id: str | None = None,
    files: list[dict[str, Any]] | None = None,
    result_png: str | None = None,
) -> ContextCard:
    """Write last_run onto an existing card. New /load creates a fresh card without it."""
    card.last_run = {
        "kind": kind,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "interpretation": interpretation,
        "metrics": dict(metrics or {}),
        "run_id": run_id,
        "files": list(files or []),
        "result_png": result_png,
    }
    return card

def load_card(user_data: dict[str, Any]) -> ContextCard | None:
    raw = user_data.get(CONTEXT_CARD_KEY)
    if not raw:
        return None
    try:
        return ContextCard.from_dict(raw)
    except Exception:
        return None


def store_card(user_data: dict[str, Any], card: ContextCard) -> None:
    """Persist formal card fields. Preserve patient secrets and patient_files."""
    existing = user_data.get(CONTEXT_CARD_KEY)
    patient = None
    patient_files = None
    if isinstance(existing, dict):
        patient = existing.get("patient")
        patient_files = existing.get("patient_files")
    data = card.to_dict()
    if patient is not None:
        data["patient"] = patient
    if patient_files is not None:
        data["patient_files"] = patient_files
    user_data[CONTEXT_CARD_KEY] = data


def clear_card(user_data: dict[str, Any]) -> bool:
    """Drop the context card, patient secrets, and patient_files."""
    return user_data.pop(CONTEXT_CARD_KEY, None) is not None


if __name__ == "__main__":
    c = parse_load_text("find inhibitor for KRAS G12C GDP covalent")
    assert c.intent == "small_molecule_design"
    assert c.gene == "KRAS" and c.variant == "G12C" and c.state == "GDP"
    assert c.covalent is True and c.sequence and c.sequence[11] == "C"
    assert c.sequence_source == "cached_uniprot"
    assert not c.missing_fields
    print(format_card(c))
    print("---")
    c2 = parse_load_text("find me an inhibitor for KRAS")
    assert c2.sequence and c2.sequence[11] == "G"
    assert c2.missing_fields
    c3 = parse_load_text("fold something unknown")
    assert c3.sequence is None and c3.sequence_source == "missing"
    c4 = parse_load_text(
        "design a de novo protein binder to KRAS G12C at the Switch-II pocket"
    )
    assert c4.gene == "KRAS" and c4.variant == "G12C"
    assert c4.pocket_residues == {"A": list(range(60, 77))}
    assert c4.hotspot_source == HOTSPOT_SOURCE_KRAS_SWITCH_II
    c5 = parse_load_text("design a binder to EGFR at the Switch-II pocket")
    assert c5.gene == "EGFR"
    assert c5.pocket_residues is None
    assert c5.hotspot_source is None
    print("self-check passed")
