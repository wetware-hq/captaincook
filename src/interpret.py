"""Clinical result captions — Concise, Clear, Clinically understandable.

Voice: full sentences; truth and clarity; Proper English with a measured
Colonial-period cadence (not a portrayal of any historical person).
Include the target name. Weave biostatistics into the prose. Do not append
free-floating score fragments. Research-use only.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _f(val: Any, digits: int = 2) -> str | None:
    if val is None:
        return None
    try:
        return f"{float(val):.{digits}f}"
    except (TypeError, ValueError):
        return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def target_label(gene: str | None = None, variant: str | None = None) -> str:
    """Human target name for captions, e.g. 'KRAS G12C' or 'the submitted protein'."""
    if gene:
        g = gene.strip().upper().replace("-", "")
        if variant and str(variant).upper() not in ("", "NONE"):
            return f"{g} {str(variant).strip().upper()}"
        return g
    return "the submitted protein"


def interpret_fold(
    *,
    n_aa: int,
    target: str | None = None,
    structure_confidence: float | None = None,
    ptm: float | None = None,
) -> str:
    name = target or "the submitted protein"
    conf = _f(structure_confidence)
    ptm_s = _f(ptm)
    if conf and ptm_s:
        stats = (
            f"with an overall model confidence of about {conf} and a predicted "
            f"TM score of about {ptm_s}"
        )
    elif conf:
        stats = f"with an overall model confidence of about {conf}"
    elif ptm_s:
        stats = f"with a predicted TM score of about {ptm_s}"
    else:
        stats = "with the confidence metrics that this run returned"

    return (
        f"This image presents a computer-predicted three-dimensional form of {name}, "
        f"spanning roughly {n_aa} amino acids and {stats}. "
        "It may assist inquiry into folds and possible binding pockets. "
        "It is not an experimental structure, and it neither diagnoses disease nor "
        "directs treatment. For research use only."
    )


def interpret_binding(
    *,
    n_aa: int,
    target: str | None = None,
    binding_confidence: float | None = None,
    optimization_score: float | None = None,
    structure_confidence: float | None = None,
) -> str:
    name = target or "the submitted protein"
    bind = _f(binding_confidence)
    opt = _f(optimization_score)
    sc = _f(structure_confidence)
    parts: list[str] = []
    if bind:
        parts.append(f"a binder likelihood of about {bind}")
    if opt:
        parts.append(f"a relative ranking score of about {opt}")
    if sc:
        parts.append(f"a structure confidence of about {sc}")
    if len(parts) == 0:
        stats = "the binding metrics available from this run"
    elif len(parts) == 1:
        stats = parts[0]
    elif len(parts) == 2:
        stats = f"{parts[0]} and {parts[1]}"
    else:
        stats = f"{parts[0]}, {parts[1]}, and {parts[2]}"

    return (
        f"This image shows a computer-predicted complex of {name} "
        f"({n_aa} residues) with a small molecule, reporting {stats}. "
        "These figures may guide research discussion; they do not prove activity "
        "in cells or in patients, and they are not a treatment recommendation. "
        "For research use only."
    )


def interpret_design(
    *,
    n: int,
    candidates: Sequence[Any],
    target: str | None = None,
) -> str:
    name = target or "the present target"
    top = candidates[0] if candidates else None
    bind = _f(_get(top, "binding_confidence")) if top else None
    opt = _f(_get(top, "optimization_score")) if top else None
    sol = _get(top, "adme_solubility") if top else None

    lead_bits: list[str] = []
    if bind:
        lead_bits.append(f"a binder score of about {bind}")
    if opt:
        lead_bits.append(f"a relative score of about {opt}")
    if sol:
        lead_bits.append(f"a preliminary solubility triage of {sol}")
    if len(lead_bits) == 0:
        lead = "the leading scores available from this run"
    elif len(lead_bits) == 1:
        lead = lead_bits[0]
    elif len(lead_bits) == 2:
        lead = f"{lead_bits[0]} and {lead_bits[1]}"
    else:
        lead = f"{lead_bits[0]}, {lead_bits[1]}, and {lead_bits[2]}"

    return (
        f"This grid displays {n} computer-suggested small molecules for {name}, "
        f"ordered from strongest to weakest in-silico signal "
        f"(left to right, then top to bottom), with the leading candidate showing {lead}. "
        "These are starting points for research, not validated medicines, and not "
        "a prescription. For research use only."
    )
