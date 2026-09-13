"""Rule-based parsing of /boltz arguments into structure vs design requests."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import AMINO_ACID_ALPHABET

# API floor / bot defaults (see FEATURE-boltz-inhibitor-nl-v1.md).
DEFAULT_N_DESIGNS = 10
MIN_N_DESIGNS = 10
MAX_N_DESIGNS = 100

_VARIANT_RE = re.compile(
    r"\b(G12[CDV]|WT|wild[-\s]?type)\b",
    re.IGNORECASE,
)
_STATE_RE = re.compile(r"\b(GDP|GTP)\b", re.IGNORECASE)
_N_DESIGNS_RE = re.compile(
    r"\b(?:n_designs|n|num(?:ber)?)\s*[=:]?\s*(\d+)\b"
    r"|\b(\d+)\s*(?:designs?|molecules?)\b",
    re.IGNORECASE,
)
_GENE_RE = re.compile(
    r"\b(k-?ras|KRAS|hras|nras|egfr|braf)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StructureRequest:
    sequence: str
    smiles: str | None = None


@dataclass(frozen=True)
class DesignRequest:
    target: str
    variant: str | None = None  # WT | G12C | G12D | G12V
    state: str | None = None  # GDP | GTP
    covalent: bool | None = None
    n_designs: int = DEFAULT_N_DESIGNS
    n_designs_clamped_from: int | None = None


def looks_like_aa_sequence(token: str, *, min_len: int = 1) -> bool:
    """True if token is only IUPAC amino-acid letters (after whitespace strip)."""
    seq = "".join(token.split()).upper()
    if len(seq) < min_len:
        return False
    return all(c in AMINO_ACID_ALPHABET for c in seq)


def has_design_intent(text: str) -> bool:
    lower = text.lower()
    if "ligand design" in lower or "find me" in lower:
        return True
    if re.search(r"\bdesign\b.{0,40}\bfor\b", lower):
        return True
    for kw in ("inhibitor", "inhibitors", "binder", "binders", "design", "discover"):
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            return True
    return False


def _normalize_variant(raw: str) -> str:
    v = re.sub(r"[\s-]+", "", raw.upper())
    if v in ("WILDTYPE", "WT"):
        return "WT"
    return v


def _extract_covalent(text: str) -> bool | None:
    lower = text.lower()
    if re.search(r"\bnon[-\s]?covalent\b", lower):
        return False
    if re.search(r"\b(covalent|acrylamide)\b", lower):
        return True
    return None


def _extract_n_designs(text: str) -> tuple[int, int | None]:
    m = _N_DESIGNS_RE.search(text)
    if not m:
        return DEFAULT_N_DESIGNS, None
    raw = int(m.group(1) or m.group(2))
    if raw < MIN_N_DESIGNS:
        return MIN_N_DESIGNS, raw
    if raw > MAX_N_DESIGNS:
        return MAX_N_DESIGNS, raw
    return raw, None


def _extract_target(text: str) -> str | None:
    m = _GENE_RE.search(text)
    if not m:
        return None
    gene = m.group(1).upper().replace("-", "")
    return gene


def parse_structure_args(args: list[str]) -> StructureRequest:
    """Existing structure/binding path: protein token(s) + optional SMILES."""
    if not args:
        raise ValueError("Missing protein sequence.")
    protein_raw = args[0]
    ligand_raw = args[1] if len(args) > 1 else None
    if len(args) > 2:
        last = args[-1]
        if any(c in last for c in "=#@()[]\\/+") or any(ch.isdigit() for ch in last):
            protein_raw = "".join(args[:-1])
            ligand_raw = last
        else:
            protein_raw = "".join(args)
            ligand_raw = None
    seq = "".join(protein_raw.split()).upper()
    return StructureRequest(sequence=seq, smiles=ligand_raw)


def parse_design_args(args: list[str]) -> DesignRequest:
    text = " ".join(args)
    target = _extract_target(text)
    if not target:
        raise ValueError(
            "Could not parse a target gene. Try e.g. "
            "`/boltz find me an inhibitor for KRAS G12C GDP covalent`."
        )
    variant_m = _VARIANT_RE.search(text)
    variant = _normalize_variant(variant_m.group(1)) if variant_m else None
    state_m = _STATE_RE.search(text)
    state = state_m.group(1).upper() if state_m else None
    covalent = _extract_covalent(text)
    n_designs, clamped_from = _extract_n_designs(text)
    return DesignRequest(
        target=target,
        variant=variant,
        state=state,
        covalent=covalent,
        n_designs=n_designs,
        n_designs_clamped_from=clamped_from,
    )


def parse_boltz_args(args: list[str]) -> StructureRequest | DesignRequest:
    """Parse /boltz args into StructureRequest or DesignRequest.

    Design keywords win over a first-token that happens to look like AAs
    (e.g. ``FIND`` is valid letters but is NL here).
    """
    if not args:
        raise ValueError("empty")
    joined = " ".join(args)
    if has_design_intent(joined):
        return parse_design_args(args)
    if looks_like_aa_sequence(args[0]):
        return parse_structure_args(args)
    raise ValueError(
        "Unrecognized /boltz input. Provide an AA sequence, or an NL design "
        "request like: /boltz find me an inhibitor for KRAS"
    )


def missing_design_fields(req: DesignRequest) -> list[str]:
    missing: list[str] = []
    if req.variant is None:
        missing.append("variant (WT | G12C | G12D | G12V)")
    if req.state is None:
        missing.append("state (GDP | GTP)")
    if req.covalent is None:
        missing.append("covalent (yes | no)")
    return missing


if __name__ == "__main__":
    cases = [
        (["MKTIIALSYIFCLVFA"], StructureRequest),
        (["MKTIIALSYIFCLVFA", "CCO"], StructureRequest),
        (["find", "me", "an", "inhibitor", "for", "KRAS"], DesignRequest),
        (["find", "inhibitor", "for", "KRAS", "G12C"], DesignRequest),
        (
            ["find", "inhibitors", "for", "KRAS", "G12C", "GDP", "covalent"],
            DesignRequest,
        ),
        (["design", "8", "molecules", "for", "KRAS", "G12D", "GTP"], DesignRequest),
    ]
    ok = True
    for args, expected in cases:
        got = parse_boltz_args(args)
        if not isinstance(got, expected):
            print(f"FAIL type {args!r}: {type(got)} != {expected}")
            ok = False
            continue
        print(f"OK {args!r} -> {got}")
    d = parse_boltz_args(["find", "me", "an", "inhibitor", "for", "KRAS"])
    assert isinstance(d, DesignRequest)
    assert d.target == "KRAS" and d.variant is None and d.state is None
    assert d.covalent is None and d.n_designs == 10
    assert missing_design_fields(d)
    d2 = parse_boltz_args(
        ["find", "inhibitor", "for", "KRAS", "G12C", "GDP", "covalent", "n=8"]
    )
    assert isinstance(d2, DesignRequest)
    assert d2.variant == "G12C" and d2.state == "GDP" and d2.covalent is True
    assert d2.n_designs == 10 and d2.n_designs_clamped_from == 8
    s = parse_boltz_args(["MKTIIALSYIFCLVFA"])
    assert isinstance(s, StructureRequest) and s.smiles is None
    print("self-check passed" if ok else "self-check had failures")
    raise SystemExit(0 if ok else 1)
