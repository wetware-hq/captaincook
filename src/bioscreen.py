"""Fail-closed pre-GPU biosecurity gate (commec for DNA/RNA; AA skip in v1).

Research-use only. Defensive screen — no pathogen-design capability.
Refuse copy: docs/REFUSE-bioscreen.md (locked; do not invent strings).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Alphabet = Literal["dna", "rna", "aa", "ambiguous"]

# Standard AA alphabet (matches config.AMINO_ACID_ALPHABET).
AA_ALPHABET = set("ACDEFGHIKLMNPQRSTVWYBXZJU")
# Residues that mark a string as protein (not pure ACGTU nucleic acid).
PROTEIN_DEFINING = set("DEFHIKLMNPQRSVWYBXZJ")
DNA_LETTERS = set("ACGT")
RNA_LETTERS = set("ACGU")

# Nucleotide length below this → REVIEW (no commec). Never expose in user copy.
MIN_NT_LENGTH = 50

DEFAULT_COMMEC_BIN = "commec"
DEFAULT_COMMEC_TIMEOUT_SEC = 60

# Locked refuse strings — docs/REFUSE-bioscreen.md
REFUSE_BLOCK_SCREENED = (
    "This request cannot be fulfilled. The sequence did not pass the pre-compute "
    "biosecurity screen, and no structure or design job was started. Research use "
    "only; this agent does not support misuse."
)
REFUSE_BLOCK_TOOL = (
    "This request cannot proceed. The biosecurity screen did not complete safely, "
    "so no structure or design job was started. Please try again shortly, or "
    "contact the operator if the problem continues."
)
REFUSE_REVIEW_AMBIGUOUS = (
    "This request needs a clearer sequence before any compute can run. Please "
    "send an unambiguous DNA or RNA string, or a protein sequence on the "
    "amino-acid path. No structure or design job was started."
)
REFUSE_REVIEW_INCONCLUSIVE = (
    "This request cannot proceed without further review. The sequence is "
    "incomplete or inconclusive for an automated screen, and no structure or "
    "design job was started. Please lengthen or clarify the input, or ask an "
    "operator to review it."
)


class Decision(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    alphabet: Alphabet | None
    screen: str
    detail: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.PASS


def normalize_sequence(seq: str) -> str:
    """Strip whitespace and upper-case. Empty stays empty."""
    return "".join((seq or "").split()).upper()


def classify_alphabet(seq: str) -> Alphabet:
    """One classifier: dna | rna | aa | ambiguous. No second heuristic."""
    s = normalize_sequence(seq)
    if not s:
        return "ambiguous"
    letters = set(s)
    # DNA preferred over AA even though A/C/G/T are also amino acids.
    if letters <= DNA_LETTERS:
        return "dna"
    # Unambiguous RNA: only ACGU and at least one U.
    if letters <= RNA_LETTERS and "U" in letters:
        return "rna"
    # Protein: standard AA alphabet and at least one protein-defining residue.
    if letters <= AA_ALPHABET and (letters & PROTEIN_DEFINING):
        return "aa"
    return "ambiguous"


def _commec_bin() -> str:
    return (os.getenv("COMMEC_BIN") or DEFAULT_COMMEC_BIN).strip() or DEFAULT_COMMEC_BIN


def _commec_timeout() -> float:
    raw = (os.getenv("COMMEC_TIMEOUT_SEC") or str(DEFAULT_COMMEC_TIMEOUT_SEC)).strip()
    try:
        val = float(raw)
    except ValueError:
        return float(DEFAULT_COMMEC_TIMEOUT_SEC)
    return val if val > 0 else float(DEFAULT_COMMEC_TIMEOUT_SEC)


def _resolve_commec_executable(bin_name: str) -> str | None:
    """Return path to executable, or None if missing."""
    path = Path(bin_name)
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return shutil.which(bin_name)


def _write_temp_fasta(seq: str, alphabet: Alphabet) -> Path:
    fd, name = tempfile.mkstemp(prefix="bioscreen_", suffix=".fasta")
    os.close(fd)
    path = Path(name)
    header = "query_rna" if alphabet == "rna" else "query"
    path.write_text(f">{header}\n{seq}\n", encoding="utf-8")
    return path


def _parse_commec_output(
    returncode: int | None,
    stdout: str,
    stderr: str,
) -> tuple[Decision, str]:
    """Map stdout/stderr/returncode. Returns (decision, screen_tag). Unknown → BLOCK."""
    blob = f"{stdout}\n{stderr}".upper()
    tokens = set(blob.replace(":", " ").replace("=", " ").replace(",", " ").split())

    # Screened concern / SoC / regulated / high-concern / Flag outcome
    if (
        "SOC" in tokens
        or "SEQUENCE_OF_CONCERN" in tokens
        or "SEQUENCE OF CONCERN" in blob
        or "REGULATED" in blob
        or "HIGH-CONCERN" in blob
        or "HIGH_CONCERN" in tokens
        or "HIGH CONCERN" in blob
        or ("BIORISK" in blob and "CLEAR" not in tokens)
        or ("FLAG" in tokens and "CLEAR" not in tokens)
    ):
        return Decision.BLOCK, "commec_soc"

    # Partial / needs-human / warning → REVIEW
    if (
        "PARTIAL" in tokens
        or "WARNING" in blob
        or "NEEDS HUMAN" in blob
        or "NEEDS-HUMAN" in blob
        or "NEEDS_HUMAN" in tokens
        or ("AMBIGUOUS" in blob and "CLEAR" not in tokens)
        or ("REVIEW" in tokens and "CLEAR" not in tokens)
    ):
        return Decision.REVIEW, "commec_review"

    # Explicit clear / low-concern → PASS
    if (
        "CLEAR" in tokens
        or "LOW-CONCERN" in tokens
        or "LOW_CONCERN" in tokens
        or "LOW CONCERN" in blob
        or "PASS" in tokens
    ):
        return Decision.PASS, "commec_clear"

    # v1 --skip-tx: no HMM/open-pack clear ≠ taxonomic clear → REVIEW, not PASS.
    # Tool health problems (non-zero, crash) stay BLOCK.
    if returncode in (0, None):
        return Decision.REVIEW, "commec_no_tax_clear"
    return Decision.BLOCK, "commec_unknown"


def run_commec(
    seq: str,
    alphabet: Alphabet,
    *,
    bin_name: str | None = None,
    timeout_sec: float | None = None,
) -> GateResult:
    """Invoke commec on a temp FASTA. Fail-closed on any tool problem."""
    bin_name = bin_name if bin_name is not None else _commec_bin()
    timeout_sec = timeout_sec if timeout_sec is not None else _commec_timeout()

    exe = _resolve_commec_executable(bin_name)
    if exe is None:
        logger.warning("commec binary missing: %s", bin_name)
        return GateResult(
            decision=Decision.BLOCK,
            alphabet=alphabet,
            screen="commec_missing",
            detail=f"binary not found: {bin_name}",
        )

    fasta = _write_temp_fasta(seq, alphabet)
    try:
        # Real package: `commec screen <fasta>`. Fake test scripts: `<bin> <fasta>`.
        exe_base = Path(exe).name
        if exe_base in ("commec", "commec.py") or bin_name.strip() == "commec":
            cmd = [exe, "screen", str(fasta)]
        else:
            cmd = [exe, str(fasta)]
            if alphabet == "rna":
                cmd.append("--rna")
        # v1 thin pack: never pull NCBI taxonomy.
        cmd.append("--skip-tx")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("commec timed out after %ss", timeout_sec)
            return GateResult(
                decision=Decision.BLOCK,
                alphabet=alphabet,
                screen="commec_timeout",
                detail=f"timeout after {timeout_sec}s",
            )
        except OSError as exc:
            logger.warning("commec failed to start: %s", exc)
            return GateResult(
                decision=Decision.BLOCK,
                alphabet=alphabet,
                screen="commec_crash",
                detail=str(exc),
            )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode is not None and proc.returncode < 0:
            return GateResult(
                decision=Decision.BLOCK,
                alphabet=alphabet,
                screen="commec_crash",
                detail=f"signal {-proc.returncode}",
            )

        decision, screen = _parse_commec_output(proc.returncode, stdout, stderr)
        # Non-zero exit with no clear/soc/partial token already → unknown BLOCK.
        # If exit non-zero and we somehow got PASS, fail closed.
        if decision is Decision.PASS and proc.returncode not in (0, None):
            decision, screen = Decision.BLOCK, "commec_unknown"
        return GateResult(
            decision=decision,
            alphabet=alphabet,
            screen=screen,
            detail=(stdout or stderr)[:200],
        )
    finally:
        try:
            fasta.unlink(missing_ok=True)
        except OSError:
            pass


def gate(
    seq: str,
    *,
    bin_name: str | None = None,
    timeout_sec: float | None = None,
) -> GateResult:
    """Classify then screen. Empty sequence is not screened (caller validates)."""
    s = normalize_sequence(seq)
    if not s:
        return GateResult(
            decision=Decision.PASS,
            alphabet=None,
            screen="empty_skip",
            detail="empty sequence; caller must validate",
        )

    alphabet = classify_alphabet(s)

    if alphabet == "ambiguous":
        return GateResult(
            decision=Decision.REVIEW,
            alphabet=alphabet,
            screen="ambiguous_alphabet",
            detail="mixed or unclassifiable alphabet",
        )

    if alphabet == "aa":
        return GateResult(
            decision=Decision.PASS,
            alphabet=alphabet,
            screen="skipped_aa",
            detail="v1 AA policy: no commec",
        )

    # dna / rna
    if len(s) < MIN_NT_LENGTH:
        return GateResult(
            decision=Decision.REVIEW,
            alphabet=alphabet,
            screen="nt_too_short",
            detail=f"length {len(s)} < {MIN_NT_LENGTH}",
        )

    return run_commec(s, alphabet, bin_name=bin_name, timeout_sec=timeout_sec)


def refuse_message(result: GateResult | None = None) -> str:
    """User-visible refuse from locked REFUSE-bioscreen.md. No scores or internals."""
    if result is None:
        return REFUSE_BLOCK_TOOL
    screen = result.screen
    if screen == "ambiguous_alphabet":
        return REFUSE_REVIEW_AMBIGUOUS
    if screen in ("nt_too_short", "commec_review"):
        return REFUSE_REVIEW_INCONCLUSIVE
    if screen == "commec_soc":
        return REFUSE_BLOCK_SCREENED
    if screen in ("commec_missing", "commec_timeout", "commec_crash", "commec_unknown"):
        return REFUSE_BLOCK_TOOL
    # Fallback by decision
    if result.decision is Decision.REVIEW:
        return REFUSE_REVIEW_INCONCLUSIVE
    if result.decision is Decision.BLOCK:
        return REFUSE_BLOCK_SCREENED
    return REFUSE_BLOCK_TOOL
