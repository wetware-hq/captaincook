"""Genetic-parts annotation (/annotate parts) — v1a Bakta.

Locked: docs/FEATURE-annotate-parts.md + bioplatform card.last_run.parts schema.
Primary emit: features + counts + seq_meta. gff_path optional under patient-store.
Omit gff3 from public / Discord paths. Chromosomal ClassifyCNV stays in annotate.py.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .bioscreen import Decision, GateResult, classify_alphabet, gate, normalize_sequence
from .context_card import load_card, store_card

logger = logging.getLogger(__name__)

# --- Locked copy ---
HELP_ONE_LINER = (
    "/annotate parts — Bakta genetic-parts map from the DNA/RNA sequence on the "
    "card (length + hash + feature counts). Research use only; not a diagnosis."
)

MSG_HINT_AFTER_SEQ = "Run /annotate parts for Bakta feature map."

MSG_NO_CARD = (
    "This request cannot proceed. There is no context card. "
    "Please /load a case first, then use /annotate parts."
)

MSG_NO_SEQ = (
    "This request cannot proceed. /annotate parts needs a DNA or RNA sequence "
    "on the card. Paste one via /annotate (or upload FASTA), then retry."
)

MSG_AA_REFUSE = (
    "This request cannot proceed. Genetic-parts annotation needs DNA or RNA, "
    "not an amino-acid sequence. Fold or design paths stay on /esm /boltz /design."
)

MSG_TOO_LARGE = (
    "This request cannot proceed. The sequence on the card exceeds the "
    "~500 kb size cap for /annotate parts. Please use a shorter construct."
)

MSG_BAKTA_MISSING = (
    "This request cannot proceed. The Bakta annotation service is not available "
    "on this host (set BAKTA_HOME / install bakta + database). No parts were written."
)

MSG_COMMEC_BLOCK = (
    "This request cannot proceed. The pre-compute biosecurity screen blocked "
    "this sequence, so genetic-parts annotation was not started."
)

MSG_TOOL_DOWN = (
    "This request cannot proceed. Bakta did not complete safely, so no parts "
    "brief was written. Please try again shortly."
)

MSG_OK = (
    "Parts annotation complete ({kind}, {n} nt; sha256 {hash12}…). "
    "Features: {counts}. Research use only; not a diagnosis. "
    "Open /app Laboratory Parts when a live view is available."
)

MSG_BANNER = (
    "Research use only. Genetic-parts annotations are not a diagnosis."
)

PARTS_MAX_NT = 500_000  # ~500 kb
DEFAULT_BAKTA_TIMEOUT_SEC = 600

# GFF type → locked schema type
_TYPE_MAP: dict[str, str] = {
    "cds": "CDS",
    "trna": "tRNA",
    "rrna": "rRNA",
    "ncrna": "other",
    "tmrna": "other",
    "crispr": "CRISPR",
    "ori": "ori",
    "oric": "ori",
    "oriv": "ori",
    "orit": "ori",
    "origin": "ori",
    "origin_of_replication": "ori",
    "promoter": "promoter",
    "rbs": "RBS",
    "ribosome_binding_site": "RBS",
    "terminator": "terminator",
}

_FEATURE_TYPES = frozenset(
    {"CDS", "tRNA", "rRNA", "promoter", "RBS", "terminator", "ori", "CRISPR", "other"}
)


def bakta_home() -> Path | None:
    env = (os.getenv("BAKTA_HOME") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent.parent / "third_party" / "bakta"
    candidates.append(here)
    candidates.append(Path("/opt/bakta"))
    for p in candidates:
        if p.is_dir():
            return p
    return None


def bakta_db() -> Path | None:
    env = (os.getenv("BAKTA_DB") or "").strip()
    if env and Path(env).is_dir():
        return Path(env)
    home = bakta_home()
    if home is None:
        return None
    for name in ("db", "database", "bakta_db"):
        cand = home / name
        if cand.is_dir():
            return cand
    return None


def bakta_bin() -> str | None:
    env = (os.getenv("BAKTA_BIN") or "").strip()
    if env:
        path = Path(env)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        found = shutil.which(env)
        if found:
            return found
    home = bakta_home()
    if home is not None:
        for name in ("bakta", "bin/bakta"):
            cand = home / name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    return shutil.which("bakta")


def bakta_available() -> bool:
    """True when bakta CLI is resolvable. DB optional at detect; run fails closed without it."""
    return bakta_bin() is not None


def _sha256_12(seq: str) -> str:
    return hashlib.sha256(seq.encode("utf-8")).hexdigest()[:12]


def _map_gff_type(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if not key or key in ("region", "source", "remark", "gap"):
        return None
    if key == "gene":
        return None  # prefer CDS/tRNA children; avoid double-count
    mapped = _TYPE_MAP.get(key)
    if mapped:
        return mapped
    if "crispr" in key:
        return "CRISPR"
    if "promoter" in key:
        return "promoter"
    if "terminator" in key:
        return "terminator"
    if key in ("rbs", "ribosome_binding_site"):
        return "RBS"
    return "other"


def _parse_gff_attrs(attr_field: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (attr_field or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
        elif " " in part:
            k, _, v = part.partition(" ")
            out[k.strip()] = v.strip()
    return out


def parse_gff3(gff_text: str) -> list[dict[str, Any]]:
    """Parse GFF3 → locked feature dicts. Never invents features beyond rows."""
    features: list[dict[str, Any]] = []
    idx = 0
    for raw_line in (gff_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 8:
            continue
        ftype = _map_gff_type(cols[2])
        if ftype is None:
            continue
        try:
            start = int(cols[3])
            end = int(cols[4])
        except ValueError:
            continue
        if end < start:
            start, end = end, start
        strand_raw = (cols[6] or ".").strip()
        strand = strand_raw if strand_raw in ("+", "-") else "+"
        attrs = _parse_gff_attrs(cols[8] if len(cols) > 8 else "")
        label = (
            attrs.get("Name")
            or attrs.get("gene")
            or attrs.get("product")
            or attrs.get("ID")
            or ftype
        )
        label = str(label).strip()[:80]
        source_col = (cols[1] or "").strip().lower()
        if "bakta" in source_col or source_col in ("prodigal", "pyrodigal", "."):
            source = "bakta"
        elif "promoteratlas" in source_col or source_col == "promoteratlas":
            source = "promoteratlas"
        elif source_col in ("curated", "igem", "addgene"):
            source = "curated"
        else:
            source = "bakta"
        fid = f"f{idx}"
        idx += 1
        features.append(
            {
                "id": fid,
                "type": ftype if ftype in _FEATURE_TYPES else "other",
                "start": start,
                "end": end,
                "strand": strand,
                "label": label,
                "source": source,
            }
        )
    return features


def feature_counts(features: list[dict[str, Any]]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for f in features:
        t = str(f.get("type") or "other")
        c[t] += 1
    return dict(sorted(c.items()))


def apply_regulatory_hooks(
    features: list[dict[str, Any]],
    seq: str,
) -> list[dict[str, Any]]:
    """v1a stub: PromoterAtlas / curated iGEM match hook (no-op until data present).

    Returns features unchanged when no regulatory DB is configured. Never invents.
    """
    atlas = (os.getenv("PROMOTERATLAS_PATH") or "").strip()
    curated = (os.getenv("CURATED_PARTS_PATH") or "").strip()
    if not atlas and not curated:
        return features
    # Hook reserved for v1b: match short motifs → promoter/RBS/terminator.
    # Fail-closed: do not invent when files are missing or unreadable.
    for path_str, source in ((atlas, "promoteratlas"), (curated, "curated")):
        if not path_str:
            continue
        p = Path(path_str)
        if not p.is_file():
            logger.info("regulatory hook path missing: %s", path_str)
            continue
        _ = (seq, source)
    return features


def run_bakta(seq: str, *, timeout_sec: float | None = None) -> str:
    """Run Bakta on a DNA/RNA string; return GFF3 text. Fail-closed on error."""
    binary = bakta_bin()
    if binary is None:
        raise RuntimeError("bakta missing")
    db = bakta_db()
    timeout = timeout_sec
    if timeout is None:
        raw = (os.getenv("BAKTA_TIMEOUT_SEC") or str(DEFAULT_BAKTA_TIMEOUT_SEC)).strip()
        try:
            timeout = float(raw)
        except ValueError:
            timeout = float(DEFAULT_BAKTA_TIMEOUT_SEC)

    with tempfile.TemporaryDirectory(prefix="annotate_parts_") as tmp:
        tmp_path = Path(tmp)
        fasta = tmp_path / "query.fna"
        compact = normalize_sequence(seq)
        fasta.write_text(f">query\n{compact}\n", encoding="utf-8")
        outdir = tmp_path / "out"
        outdir.mkdir()
        cmd = [
            binary,
            "--output",
            str(outdir),
            "--prefix",
            "query",
            "--force",
            "--keep-contig-headers",
        ]
        if db is not None:
            cmd.extend(["--db", str(db)])
        extra = (os.getenv("BAKTA_EXTRA_ARGS") or "").strip()
        if extra:
            cmd.extend(extra.split())
        cmd.append(str(fasta))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("bakta failed: %s", exc)
            raise RuntimeError("bakta failed") from exc
        if proc.returncode not in (0, None):
            logger.warning(
                "bakta rc=%s stderr=%s",
                proc.returncode,
                (proc.stderr or "")[:400],
            )
            raise RuntimeError("bakta non-zero exit")
        gff_candidates = list(outdir.glob("*.gff3")) + list(outdir.glob("*.gff"))
        if not gff_candidates:
            raise RuntimeError("bakta GFF missing")
        return gff_candidates[0].read_text(encoding="utf-8", errors="replace")


def _write_gff_artifact(
    user_data: dict[str, Any],
    gff_text: str,
    hash12: str,
) -> str | None:
    """Optional durable path under patient-store. Omit when write fails."""
    try:
        from . import store as store_mod
        from .context_card import CONTEXT_CARD_KEY

        dest_dir: Path | None = None
        shell = user_data.get(CONTEXT_CARD_KEY)
        patient = shell.get("patient") if isinstance(shell, dict) else None
        pid = None
        uid = None
        if isinstance(patient, dict):
            pid = patient.get("patient_id")
        if isinstance(shell, dict):
            uid = shell.get("telegram_user_id")
        uid = uid or user_data.get("telegram_user_id")

        if isinstance(pid, str) and pid.strip() and uid is not None:
            pdir = store_mod.patient_dir(str(uid), pid.strip())
            pdir.mkdir(parents=True, exist_ok=True)
            dest_dir = pdir
        else:
            dest_dir = store_mod.STORE_ROOT / "_parts" / hash12
            dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / f"parts_{hash12}.gff3"
        dest.write_text(gff_text, encoding="utf-8")
        try:
            return str(dest.relative_to(store_mod.STORE_ROOT))
        except ValueError:
            return str(dest)
    except OSError as exc:
        logger.warning("gff artifact write failed: %s", exc)
        return None


def build_parts_payload(
    *,
    seq: str,
    kind: str,
    features: list[dict[str, Any]],
    gff_path: str | None = None,
) -> dict[str, Any]:
    """Locked card.last_run.parts — never include gff3 or full sequence."""
    payload: dict[str, Any] = {
        "seq_meta": {
            "length": len(seq),
            "sha256_12": _sha256_12(seq),
            "kind": kind,
        },
        "features": features,
        "counts": feature_counts(features),
    }
    if gff_path:
        payload["gff_path"] = gff_path
    return payload


def store_parts_on_card(user_data: dict[str, Any], parts: dict[str, Any]) -> None:
    """Write parts onto card.last_run; preserve orthogonal CNV keys."""
    card = load_card(user_data)
    if card is None:
        raise RuntimeError("no card")
    clean = {k: v for k, v in parts.items() if k != "gff3"}
    prior = dict(card.last_run) if isinstance(card.last_run, dict) else {}
    prior["kind"] = "annotate_parts"
    prior["parts"] = clean
    card.last_run = prior
    store_card(user_data, card)


def get_parts_public(user_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Redacted parts for /app — features + counts + seq_meta (+ optional gff_path)."""
    if not user_data:
        return None
    card = load_card(user_data)
    if card is None or not isinstance(card.last_run, dict):
        return None
    raw = card.last_run.get("parts")
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for key in ("seq_meta", "features", "counts", "gff_path"):
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
    return out or None


def _card_sequence_kind(seq: str) -> str | None:
    alph = classify_alphabet(seq)
    if alph in ("dna", "rna"):
        return alph
    letters = set(normalize_sequence(seq))
    if letters <= set("ACGTU") and letters:
        return "dna" if "U" not in letters else "rna"
    if alph == "aa":
        return "aa"
    return None


def process_parts(
    user_data: dict[str, Any],
    *,
    gff_override: str | None = None,
) -> tuple[str, dict[str, Any] | None, GateResult | None, str]:
    """Run Bakta parts pipeline on card DNA/RNA.

    Returns (reply, parts_payload|None, gate|None, status).
    status: ok|no_card|no_seq|aa|oversize|tool|block|review
    gff_override: test hook — skip bakta, parse this GFF3 text.
    """
    card = load_card(user_data)
    if card is None:
        return MSG_NO_CARD, None, None, "no_card"

    seq = normalize_sequence(card.sequence or "")
    if not seq:
        return MSG_NO_SEQ, None, None, "no_seq"

    kind = _card_sequence_kind(seq)
    if kind == "aa":
        return MSG_AA_REFUSE, None, None, "aa"
    if kind not in ("dna", "rna"):
        return MSG_NO_SEQ, None, None, "no_seq"

    if len(seq) > PARTS_MAX_NT:
        return MSG_TOO_LARGE, None, None, "oversize"

    gate_result = gate(seq)
    if gate_result.decision is Decision.BLOCK:
        return MSG_COMMEC_BLOCK, None, gate_result, "block"
    if gate_result.decision is Decision.REVIEW:
        from .bioscreen import refuse_message

        return refuse_message(gate_result), None, gate_result, "review"

    if gff_override is None and not bakta_available():
        return MSG_BAKTA_MISSING, None, gate_result, "tool"

    try:
        if gff_override is not None:
            gff_text = gff_override
        else:
            gff_text = run_bakta(seq)
    except RuntimeError:
        return MSG_TOOL_DOWN, None, gate_result, "tool"

    features = parse_gff3(gff_text)
    features = apply_regulatory_hooks(features, seq)
    hash12 = _sha256_12(seq)
    gff_path = _write_gff_artifact(user_data, gff_text, hash12)
    parts = build_parts_payload(
        seq=seq, kind=kind, features=features, gff_path=gff_path
    )
    store_parts_on_card(user_data, parts)

    counts = parts.get("counts") or {}
    if counts:
        counts_s = ", ".join(f"{k}={v}" for k, v in counts.items())
    else:
        counts_s = "none detected"
    msg = MSG_OK.format(
        kind=kind.upper(),
        n=len(seq),
        hash12=hash12,
        counts=counts_s,
    )
    return msg, parts, gate_result, "ok"


def get_parts_meta(user_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convenience for /app: seq_meta + counts only (no features list)."""
    pub = get_parts_public(user_data)
    if not pub:
        return None
    out: dict[str, Any] = {}
    if "seq_meta" in pub:
        out["seq_meta"] = pub["seq_meta"]
    if "counts" in pub:
        out["counts"] = pub["counts"]
    return out or None


# Stable chip order for Laboratory Parts SEQ view
_TYPE_ORDER = (
    "CDS",
    "tRNA",
    "rRNA",
    "promoter",
    "RBS",
    "terminator",
    "ori",
    "CRISPR",
    "other",
)
