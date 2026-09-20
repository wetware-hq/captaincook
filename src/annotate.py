"""Paste-friendly chromosomal CNV annotation (/annotate) — v1a.

Locked: docs/FEATURE-annotate-cnv.md + docs/TEMPLATE-annotate-cnv.md (verbatim).
Engine: ClassifyCNV (ACMG/ClinGen 2019). Bioscreen and ACMG stamps stay orthogonal.
UX: MD brief + /app interactive interval strip (tap → breakdown; filter chr/DEL/DUP;
gene→evidence links). No 1bp/1AA letter zoom; SeqViz/igv deferred.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bioscreen import Decision, GateResult, classify_alphabet, gate, normalize_sequence
from .context_card import CONTEXT_CARD_KEY, load_card

logger = logging.getLogger(__name__)

ANNOTATE_KEY = "annotate"  # arm state on user_data
CNV_FIELD = "cnv_annotations"  # optional session cache on card shell

DEFAULT_GENOME_BUILD = "hg38"
DEFAULT_CLASSIFYCNV_TIMEOUT_SEC = 120

# --- Locked TEMPLATE-annotate-cnv.md (verbatim) ---
HELP_ONE_LINER = (
    "/annotate — One-shot coords, paste sequence, or upload FASTA/FASTQ/VCF/BED (GRCh38 default; refuse BAM/CRAM). Research use only; not a diagnosis."
)

MSG_ARMED = (
    "Send one interval, for example:\n"
    "chr12:25205246-25250929 DUP\n"
    "\n"
    "Or paste a DNA/RNA/AA sequence to store on the card (length + hash only in chat). "
    "GRCh38 is the default for intervals (add ##assembly=GRCh37 only if needed). "
    "BED / VCF-SV multi-line paste also works. You can also upload FASTA, FASTQ, VCF, or BED (not BAM/CRAM). "
    "Research use only; this is not a diagnosis. Send /cancel to stop."
)

MSG_FASTA_REFUSE = (
    "That looks like FASTA headers without clear intervals. "
    "Use `/annotate chr12:25205246-25250929 DUP`, or paste plain sequence "
    "(no `>` headers) to store length + hash on the card."
)


MSG_UPLOAD_REFUSE_BAM = (
    "BAM and CRAM uploads are not accepted for /annotate. "
    "Please upload FASTA, FASTQ, VCF-SV, or BED (size-capped)."
)

MSG_UPLOAD_OVERSIZE = (
    "That file is too large for /annotate. "
    "Please use a smaller FASTA/FASTQ (≤2 MB) or VCF/BED (≤5 MB), or paste intervals."
)

MSG_UPLOAD_BAD_TYPE = (
    "Unsupported file type for /annotate. "
    "Accepted: FASTA, FASTQ, VCF-SV, BED. BAM/CRAM are refused."
)

ANNOTATE_MAX_FASTA_BYTES = 2 * 1024 * 1024
ANNOTATE_MAX_FASTQ_BYTES = 2 * 1024 * 1024
ANNOTATE_MAX_VCF_BED_BYTES = 5 * 1024 * 1024
ANNOTATE_FASTQ_MAX_READS = 500


MSG_SAVED = (
    "Chromosomal annotation complete: {n} interval(s). Research use only; "
    "not a diagnosis. Open /app for the Clinical Chromosomal section when a "
    "live view is available."
)

MSG_HELPER = (
    "I could not read that as CNV intervals. Please send one interval, for example:\n"
    "chr12:25205246-25250929 DUP\n"
    "Free paragraphs are not parsed. Send /cancel to stop."
)

MSG_SEQ_STORED = (
    "Sequence stored on the card ({kind}, {n} residues; sha256 {hash12}…). "
    "Not shown in full here. Research use only; not a diagnosis."
)

MSG_SEQ_BLOCK = (
    "This request cannot proceed. The pre-compute biosecurity screen blocked "
    "this sequence, so it was not stored on the card."
)

MSG_AA_ONLY = (
    "This request cannot proceed. Chromosomal annotation needs DNA or RNA "
    "intervals, not an amino-acid sequence. Fold or design paths stay on "
    "/esm /boltz /design."
)

MSG_COMMEC_BLOCK = (
    "This request cannot proceed. The pre-compute biosecurity screen blocked "
    "this sequence, so chromosomal annotation was not started."
)

MSG_TOOL_DOWN = (
    "This request cannot proceed. The CNV annotation service did not respond "
    "safely, so no brief was written. Please try again shortly."
)

MSG_NO_CARD = (
    "This request cannot proceed. There is no context card. "
    "Please /load a case first, then use /annotate."
)

MSG_CANCELLED = (
    "The pending chromosomal annotation paste was cancelled."
)

MSG_BANNER = (
    "Research use only. Chromosomal annotations are not a diagnosis."
)

CLINIC_NONE_YET = "None yet."

BRIEF_INTRO = (
    "This brief summarises copy-number / structural intervals you supplied. "
    "It is for research use only. It is not a diagnosis, not a prognosis, "
    "and not treatment advice."
)

# ACMG criterion short glosses (plain language; not clinical advice).
_CRITERION_GLOSS: dict[str, str] = {
    "1A-B": "Contains established / predicted haploinsufficient or triplosensitive gene content",
    "1": "Contains established / predicted dosage-sensitive gene content",
    "2A": "Complete overlap of an established HI/TS gene",
    "2B": "Partial overlap of an established HI gene — transcription disrupted",
    "2C": "Partial overlap of an established HI gene — last exon only / unclear",
    "2D": "Partial overlap of an established HI gene — 5′ region only",
    "2E": "Both or either breakpoint within an established HI gene",
    "2F": "Overlaps established benign copy-number polymorphism",
    "2G": "Overlaps genes without established dosage sensitivity evidence",
    "2H": "Two or more HI predictors agree",
    "2I": "Number of protein-coding genes",
    "2J": "Number of genes in region",
    "2K": "Decipher / population frequency evidence",
    "2L": "Overlap with established pathogenic region (opposite class)",
    "3": "Number of protein-coding RefSeq genes",
    "4A": "Complete overlap of an established HI region",
    "4B": "Partial overlap of established HI region — continues past breakpoint",
    "4C": "Overlap of an established HI region — unclear clinical significance",
    "4D": "Patient phenotype highly specific / consistent with gene",
    "4E": "Reported phenotype consistent with gene",
    "4F-H": "Case-control / segregation / de novo evidence bundle",
    "4I": "Inheritance / segregation evidence",
    "4J": "De novo occurrence",
    "4K": "Non-segregation evidence",
    "4L": "Case reports without detailed phenotypes",
    "4M": "Overlaps pathogenic region of opposite class",
    "4N": "Population frequency among cases",
    "4O": "Population frequency among controls",
    "5A": "Contains established TS gene / region",
    "5B": "Partial overlap of established TS gene",
    "5C": "Breakpoint within established TS gene",
    "5D": "Phenotype highly specific for TS gene",
    "5E": "Phenotype consistent with TS gene",
    "5F": "Case-control evidence (gain)",
    "5G": "Inheritance evidence (gain)",
    "5H": "Population / benign polymorphism evidence (gain)",
}

_REF_LINES = (
    "Riggs, E.R., et al., 2020. Technical standards for the interpretation and "
    "reporting of constitutional copy-number variants: a joint consensus "
    "recommendation of the American College of Medical Genetics and Genomics "
    "(ACMG) and the Clinical Genome Resource (ClinGen). Genetics in Medicine. "
    "https://doi.org/10.1038/s41436-019-0686-8",
    "Gurbich, T.A., Ilinsky, V.V., 2020. ClassifyCNV: a tool for clinical "
    "annotation of copy-number variants. Scientific Reports. "
    "https://doi.org/10.1038/s41598-020-76400-y",
)

# chr:start-end DEL|DUP (flexible whitespace / optional commas in coords)
_INTERVAL_RE = re.compile(
    r"(?i)^\s*(?:chr)?(?P<chrom>\d{1,2}|X|Y|M|MT)\s*[:\s]\s*"
    r"(?P<start>[\d,]+)\s*[-–—]\s*(?P<end>[\d,]+)\s+"
    r"(?P<svtype>DEL|DUP|DELETION|DUPLICATION|LOSS|GAIN)\s*$"
)
# BED: chrom start end type
_BED_RE = re.compile(
    r"(?i)^\s*(?:chr)?(?P<chrom>\d{1,2}|X|Y|M|MT)\s+"
    r"(?P<start>[\d,]+)\s+(?P<end>[\d,]+)\s+"
    r"(?P<svtype>DEL|DUP|DELETION|DUPLICATION|LOSS|GAIN)\b"
)
# VCF-SV ALT=<DEL|DUP> with END= or SVLEN=
_VCF_RE = re.compile(
    r"(?i)^\s*(?:chr)?(?P<chrom>\d{1,2}|X|Y|M|MT)\s+"
    r"(?P<pos>\d+)\s+\S+\s+\S+\s+<(?P<alt>DEL|DUP|DUP:TANDEM)>"
    r".*?(?:END=(?P<end>\d+)|SVLEN=(?P<svlen>-?\d+))"
)

_AA_ONLY_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZJU\s\d]+$", re.IGNORECASE)


@dataclass
class CnvInterval:
    chrom: str  # normalised chrN
    start: int  # 0-based BED start (inclusive)
    end: int  # exclusive end (BED) / inclusive genomic end+1 storage as BED
    svtype: str  # DEL | DUP
    source: str = "paste"  # bed | interval | vcf

    @property
    def length_bp(self) -> int:
        return max(0, self.end - self.start)

    @property
    def label(self) -> str:
        # Clinician-facing: Mb/kb abstraction, not 1bp dump
        return f"{self.chrom}:{self.start}-{self.end} {self.svtype}"

    @property
    def span_label(self) -> str:
        n = self.length_bp
        if n >= 1_000_000:
            return f"{n / 1_000_000:.2f} Mb"
        if n >= 1_000:
            return f"{n / 1_000:.1f} kb"
        return f"{n} bp"

    def cnv_id(self) -> str:
        raw = f"{self.chrom}:{self.start}-{self.end}:{self.svtype}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def to_bed_line(self) -> str:
        return f"{self.chrom}\t{self.start}\t{self.end}\t{self.svtype}"


@dataclass
class CnvResult:
    interval: CnvInterval
    classification: str
    total_score: float
    criteria: dict[str, float] = field(default_factory=dict)
    dosage_genes: list[str] = field(default_factory=list)
    coding_genes: list[str] = field(default_factory=list)
    variant_id: str = ""

    def genes_display(self) -> str:
        genes = self.dosage_genes or self.coding_genes
        if not genes:
            return "none yet"
        # Cap for MD; full list available in /app panel
        shown = genes[:12]
        extra = len(genes) - len(shown)
        text = ", ".join(shown)
        if extra > 0:
            text += f" (+{extra} more)"
        return text

    def to_public_dict(self) -> dict[str, Any]:
        """Redacted JSON for /app strip — no PHI beyond genomic intervals."""
        return {
            "id": self.interval.cnv_id(),
            "chrom": self.interval.chrom,
            "start": self.interval.start,
            "end": self.interval.end,
            "svtype": self.interval.svtype,
            "span": self.interval.span_label,
            "classification": self.classification,
            "total_score": self.total_score,
            "criteria": {k: v for k, v in self.criteria.items() if abs(v) > 1e-9},
            "dosage_genes": list(self.dosage_genes),
            "coding_genes": list(self.coding_genes)[:40],
            "label": self.interval.label,
        }


def _norm_chrom(raw: str) -> str:
    c = raw.strip().upper().lstrip("CHR")
    if c == "MT":
        c = "M"
    return f"chr{c}" if c != "M" else "chrM"


def _norm_svtype(raw: str) -> str:
    u = raw.strip().upper()
    if u in ("DEL", "DELETION", "LOSS") or u.startswith("DEL"):
        return "DEL"
    if u in ("DUP", "DUPLICATION", "GAIN") or u.startswith("DUP"):
        return "DUP"
    return u


def _parse_int(raw: str) -> int:
    return int(str(raw).replace(",", "").strip())


def parse_cnv_lines(text: str) -> list[CnvInterval]:
    """Parse BED / VCF-SV / chr:start-end DEL|DUP. No NLP invent. Streaming-friendly."""
    out: list[CnvInterval] = []
    seen: set[str] = set()
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.upper().startswith("BROWSER") or line.upper().startswith("TRACK"):
            continue
        # strip leading VCF CHROM header
        if line.startswith("##") or line.upper().startswith("#CHROM"):
            continue
        iv: CnvInterval | None = None
        m = _INTERVAL_RE.match(line)
        if m:
            start = _parse_int(m.group("start"))
            end = _parse_int(m.group("end"))
            if end > start:
                iv = CnvInterval(
                    chrom=_norm_chrom(m.group("chrom")),
                    start=start,
                    end=end,
                    svtype=_norm_svtype(m.group("svtype")),
                    source="interval",
                )
        if iv is None:
            m = _BED_RE.match(line)
            if m:
                start = _parse_int(m.group("start"))
                end = _parse_int(m.group("end"))
                if end > start:
                    iv = CnvInterval(
                        chrom=_norm_chrom(m.group("chrom")),
                        start=start,
                        end=end,
                        svtype=_norm_svtype(m.group("svtype")),
                        source="bed",
                    )
        if iv is None:
            m = _VCF_RE.search(line)
            if m:
                start = _parse_int(m.group("pos"))  # VCF POS 1-based; BED uses 0-based
                # Convert to 0-based start for BED engine
                start0 = start - 1 if start > 0 else 0
                end_s = m.group("end")
                svlen = m.group("svlen")
                if end_s:
                    end = _parse_int(end_s)
                elif svlen:
                    sl = abs(_parse_int(svlen))
                    end = start0 + sl
                else:
                    continue
                if end > start0:
                    iv = CnvInterval(
                        chrom=_norm_chrom(m.group("chrom")),
                        start=start0,
                        end=end,
                        svtype=_norm_svtype(m.group("alt")),
                        source="vcf",
                    )
        if iv is None:
            continue
        key = iv.cnv_id()
        if key in seen:
            continue
        seen.add(key)
        out.append(iv)
    return out


def _extract_sequence_blob(text: str) -> str | None:
    """Longest ACGTU run ≥50 nt if present (for commec). None if none."""
    best = ""
    for m in re.finditer(r"[ACGTUacgtu]{50,}", text or ""):
        s = m.group(0)
        if len(s) > len(best):
            best = s
    return best.upper() if best else None



_ASSEMBLY_RE = re.compile(
    r"(?im)^(?:##\s*)?assembly\s*[=:]\s*(GRCh38|GRCh37|hg38|hg19)\b"
)


def extract_assembly(text: str) -> str | None:
    """Return ClassifyCNV build hg38|hg19 from ##assembly=… or None if missing."""
    m = _ASSEMBLY_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).upper()
    if raw in ("GRCH38", "HG38"):
        return "hg38"
    if raw in ("GRCH37", "HG19"):
        return "hg19"
    return None


def looks_fasta_as_chromosome(text: str) -> bool:
    """True when paste looks like FASTA / nt canvas without CNV interval lines."""
    if parse_cnv_lines(text or ""):
        return False
    raw = text or ""
    if re.search(r"(?m)^>\S+", raw):
        return True
    compact = re.sub(r"[^ACGTUacgtu]", "", raw)
    if len(compact) >= 80 and len(compact) >= 0.6 * max(1, len(re.sub(r"\s+", "", raw))):
        return True
    return False

def looks_aa_only(text: str) -> bool:
    """True when paste is protein alphabet without any CNV interval lines."""
    if parse_cnv_lines(text):
        return False
    compact = normalize_sequence(text or "")
    if len(compact) < 20:
        return False
    # Reject if clearly nucleotide
    letters = set(compact)
    if letters <= set("ACGTU"):
        return False
    alph = classify_alphabet(compact)
    return alph == "aa"


def bioscreen_for_paste(text: str) -> GateResult:
    """Alphabet → commec when DNA/RNA present; interval-only → PASS (orthogonal stamp).

    No human-proceed path exists for REVIEW → callers treat non-PASS as refuse.
    """
    seq = _extract_sequence_blob(text)
    if seq:
        return gate(seq)
    # Interval-only (or empty after parse) — no sequence to screen.
    return GateResult(
        decision=Decision.PASS,
        alphabet=None,
        screen="cnv_interval_no_seq",
        detail="interval-only paste; no DNA/RNA sequence screened",
    )


def bioscreen_stamp_sentence(result: GateResult) -> str:
    """One-sentence bioscreen stamp; never merges with ACMG."""
    d = result.decision.value
    if result.screen == "cnv_interval_no_seq":
        return (
            f"{d}. No DNA or RNA sequence accompanied these intervals, so no "
            "sequence-of-concern check was required. This stamp is separate from "
            "the ACMG classification below."
        )
    if result.decision is Decision.PASS:
        return (
            f"{d} (biosecurity screen clear). This stamp is separate from the "
            "ACMG classification below."
        )
    if result.decision is Decision.REVIEW:
        return (
            f"{d}. The biosecurity screen needs human review; chromosomal "
            "annotation was not started. This stamp is separate from ACMG."
        )
    return (
        f"{d}. The biosecurity screen blocked this sequence; chromosomal "
        "annotation was not started. This stamp is separate from ACMG."
    )


def classifycnv_home() -> Path | None:
    env = (os.getenv("CLASSIFYCNV_HOME") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent.parent / "third_party" / "ClassifyCNV"
    candidates.append(here)
    candidates.append(Path("/opt/ClassifyCNV"))
    for p in candidates:
        if (p / "ClassifyCNV.py").is_file():
            return p
    return None


def classifycnv_available() -> bool:
    if classifycnv_home() is None:
        return False
    return shutil.which("bedtools") is not None


def run_classifycnv(
    intervals: list[CnvInterval],
    *,
    genome_build: str = DEFAULT_GENOME_BUILD,
    timeout_sec: float | None = None,
) -> list[CnvResult]:
    """Invoke ClassifyCNV; fail-closed on missing binary or bad exit."""
    if not intervals:
        return []
    home = classifycnv_home()
    if home is None or not shutil.which("bedtools"):
        raise RuntimeError("ClassifyCNV or bedtools missing")
    timeout = timeout_sec
    if timeout is None:
        raw = (os.getenv("CLASSIFYCNV_TIMEOUT_SEC") or str(DEFAULT_CLASSIFYCNV_TIMEOUT_SEC)).strip()
        try:
            timeout = float(raw)
        except ValueError:
            timeout = float(DEFAULT_CLASSIFYCNV_TIMEOUT_SEC)
    build = genome_build if genome_build in ("hg19", "hg38") else DEFAULT_GENOME_BUILD
    script = home / "ClassifyCNV.py"
    outdir_name = f"cc_{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="annotate_cnv_") as tmp:
        bed_path = Path(tmp) / "input.bed"
        bed_path.write_text(
            "".join(iv.to_bed_line() + "\n" for iv in intervals),
            encoding="utf-8",
        )
        # ClassifyCNV writes results under CWD (or ClassifyCNV_results depending on version)
        cmd = [
            "python3",
            str(script),
            "--infile",
            str(bed_path),
            "--GenomeBuild",
            build,
            "--outdir",
            outdir_name,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=str(home),
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("ClassifyCNV failed: %s", exc)
            raise RuntimeError("ClassifyCNV failed") from exc
        if proc.returncode not in (0, None):
            logger.warning(
                "ClassifyCNV rc=%s stderr=%s",
                proc.returncode,
                (proc.stderr or "")[:400],
            )
            raise RuntimeError("ClassifyCNV non-zero exit")
        sheet = _find_scoresheet(home, outdir_name)
        if sheet is None:
            raise RuntimeError("ClassifyCNV Scoresheet missing")
        return _parse_scoresheet(sheet, intervals)


def _find_scoresheet(home: Path, outdir_name: str) -> Path | None:
    candidates = [
        home / outdir_name / "Scoresheet.txt",
        home / "ClassifyCNV_results" / outdir_name / "Scoresheet.txt",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Fallback: newest Scoresheet under home
    found = sorted(home.rglob("Scoresheet.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0] if found else None


def _parse_scoresheet(path: Path, intervals: list[CnvInterval]) -> list[CnvResult]:
    by_key = {
        (iv.chrom, iv.start, iv.end, iv.svtype): iv for iv in intervals
    }
    results: list[CnvResult] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            chrom = _norm_chrom(str(row.get("Chromosome") or ""))
            try:
                start = int(str(row.get("Start") or "0"))
                end = int(str(row.get("End") or "0"))
            except ValueError:
                continue
            svtype = _norm_svtype(str(row.get("Type") or "DEL"))
            iv = by_key.get((chrom, start, end, svtype))
            if iv is None:
                iv = CnvInterval(chrom=chrom, start=start, end=end, svtype=svtype, source="engine")
            try:
                score = float(str(row.get("Total score") or "0") or "0")
            except ValueError:
                score = 0.0
            classification = str(row.get("Classification") or "Uncertain significance").strip()
            criteria: dict[str, float] = {}
            for key, raw in row.items():
                if key in (
                    "VariantID",
                    "Chromosome",
                    "Start",
                    "End",
                    "Type",
                    "Classification",
                    "Total score",
                    "Known or predicted dosage-sensitive genes",
                    "All protein coding genes",
                ):
                    continue
                try:
                    val = float(str(raw or "0") or "0")
                except ValueError:
                    continue
                if abs(val) > 1e-12:
                    criteria[key] = val
            dosage = _split_genes(row.get("Known or predicted dosage-sensitive genes") or "")
            coding = _split_genes(row.get("All protein coding genes") or "")
            results.append(
                CnvResult(
                    interval=iv,
                    classification=classification,
                    total_score=score,
                    criteria=criteria,
                    dosage_genes=dosage,
                    coding_genes=coding,
                    variant_id=str(row.get("VariantID") or ""),
                )
            )
    # Preserve input order when possible
    order = {iv.cnv_id(): i for i, iv in enumerate(intervals)}
    results.sort(key=lambda r: order.get(r.interval.cnv_id(), 10_000))
    return results


def _split_genes(raw: str) -> list[str]:
    parts = re.split(r"[,;\s]+", (raw or "").strip())
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        g = p.strip()
        if not g or g.lower() in ("none", "na", "."):
            continue
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


def criteria_breakdown_bullets(result: CnvResult, *, limit: int = 12) -> list[str]:
    """Inspectable ACMG criteria bullets (plain language)."""
    items = sorted(result.criteria.items(), key=lambda kv: abs(kv[1]), reverse=True)
    bullets: list[str] = []
    for key, val in items[:limit]:
        gloss = _CRITERION_GLOSS.get(key, f"ACMG evidence field {key}")
        sign = f"{val:+.2f}" if val != 0 else "0"
        bullets.append(f"- {key} ({sign}): {gloss}")
    if not bullets:
        bullets.append(
            "- No non-zero ACMG evidence fields were scored for this interval "
            "(ClassifyCNV total score reported as "
            f"{result.total_score:.2f})."
        )
    return bullets


def render_annotate_md(
    results: list[CnvResult],
    bioscreen: GateResult,
) -> str:
    """Telegram MD brief per TEMPLATE-annotate-cnv.md shape."""
    lines: list[str] = [
        "# Chromosomal annotation",
        "",
        BRIEF_INTRO,
        "",
        "## Biosecurity screen",
        "",
        bioscreen_stamp_sentence(bioscreen),
        "",
    ]
    if bioscreen.decision is Decision.BLOCK:
        lines.extend(
            [
                "## Findings",
                "",
                "No ACMG findings are listed because the biosecurity screen blocked annotation.",
                "",
                "## References",
                "",
            ]
        )
        lines.extend(f"- {r}" for r in _REF_LINES)
        lines.append("")
        return "\n".join(lines)

    lines.extend(["## Findings", ""])
    if not results:
        lines.append("No intervals were annotated.")
        lines.append("")
    else:
        for r in results:
            lines.append(f"- Interval: {r.interval.label} ({r.interval.span_label})")
            lines.append(
                f"- Classification: {r.classification} "
                "(ACMG/ClinGen-style criteria below)"
            )
            lines.append(f"- Overlapped genes: {r.genes_display()}")
            lines.append("")
    lines.extend(["## Criteria breakdown", ""])
    if results:
        for r in results:
            lines.append(f"### {r.interval.label}")
            lines.append("")
            lines.extend(criteria_breakdown_bullets(r))
            lines.append("")
    else:
        lines.append("- None.")
        lines.append("")
    lines.extend(["## References", ""])
    for ref in _REF_LINES:
        lines.append(f"- {ref}")
    lines.append("")
    return "\n".join(lines)


def clinic_chromosomal_block(results: list[CnvResult], *, ts: str | None = None) -> str:
    """Scan-first clinic.md ## Chromosomal body (≤3 bullets per event + cites)."""
    when = ts or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    parts = [
        "## Chromosomal",
        "",
        MSG_BANNER,
        "",
        f"Track note ({when}): {len(results)} interval(s); span abstracted to kb/Mb — "
        "not a nucleotide browser.",
        "",
    ]
    for r in results[:3]:
        genes = r.genes_display()
        parts.append(
            f"- {r.interval.label} ({r.interval.span_label}) — "
            f"{r.classification}; genes: {genes} "
            f"(id `cnv:{r.interval.cnv_id()}`)"
        )
    if len(results) > 3:
        parts.append(f"- …and {len(results) - 3} more interval(s) on file.")
    parts.append("")
    parts.append("Method: ClassifyCNV / ACMG-ClinGen 2019 "
                 "(https://doi.org/10.1038/s41436-019-0686-8).")
    parts.append("")
    return "\n".join(parts)


def end_annotate(user_data: dict[str, Any]) -> bool:
    if user_data.pop(ANNOTATE_KEY, None) is not None:
        return True
    return False


def is_armed(user_data: dict[str, Any]) -> bool:
    return bool(user_data.get(ANNOTATE_KEY))


def start_annotate(user_data: dict[str, Any]) -> str:
    if load_card(user_data) is None:
        end_annotate(user_data)
        return MSG_NO_CARD
    user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
    return MSG_ARMED


def _stash_results_on_card(user_data: dict[str, Any], results: list[CnvResult], brief_md: str) -> None:
    """Session cache for /app strip (redacted public dicts)."""
    from .context_card import store_card

    card = load_card(user_data)
    if card is None:
        return
    prior = dict(card.last_run) if isinstance(card.last_run, dict) else {}
    prior["kind"] = "annotate_cnv"
    prior["cnv"] = [r.to_public_dict() for r in results]
    prior["annotate_brief_md"] = brief_md[:50_000]
    card.last_run = prior
    store_card(user_data, card)
    # Also keep a thin list on user_data shell for board without re-parse
    shell = user_data.get(CONTEXT_CARD_KEY)
    if isinstance(shell, dict):
        shell[CNV_FIELD] = prior["cnv"]


def get_cnv_public(user_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not user_data:
        return []
    card = load_card(user_data)
    if card and isinstance(card.last_run, dict):
        raw = card.last_run.get("cnv")
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    shell = user_data.get(CONTEXT_CARD_KEY)
    if isinstance(shell, dict):
        raw2 = shell.get(CNV_FIELD)
        if isinstance(raw2, list):
            return [x for x in raw2 if isinstance(x, dict)]
    return []


def extract_raw_sequence(text: str) -> tuple[str, str] | None:
    """Return (compact_seq, kind) for AA/DNA/RNA paste; None if not a sequence.

    Strips FASTA `>` headers. Never invents DNA from AA.
    """
    raw = text or ""
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith(">"):
            continue
        if s.startswith("#") or s.upper().startswith("BROWSER") or s.upper().startswith("TRACK"):
            continue
        lines.append(s)
    blob = "".join(lines) if lines else raw
    compact = normalize_sequence(blob)
    if len(compact) < 16:
        return None
    # Reject if it still looks like interval coords dominating
    if parse_cnv_lines(raw):
        return None
    alph = classify_alphabet(compact)
    if alph == "aa":
        return compact, "aa"
    if alph in ("dna", "rna"):
        return compact, alph
    # Ambiguous long ACGT-only
    letters = set(compact.upper())
    if letters <= set("ACGTU") and len(compact) >= 16:
        return compact.upper(), "dna" if "U" not in letters else "rna"
    return None


def store_sequence_on_card(
    user_data: dict[str, Any], seq: str, kind: str
) -> tuple[str, str]:
    """Store full sequence on card; return (kind_label, sha256_12). Never echo body."""
    from .context_card import store_card

    card = load_card(user_data)
    if card is None:
        raise RuntimeError("no card")
    digest = hashlib.sha256(seq.encode("utf-8")).hexdigest()
    card.sequence = seq
    card.sequence_source = "user_paste"
    prior = dict(card.last_run) if isinstance(card.last_run, dict) else {}
    prior["kind"] = "annotate_sequence"
    prior["sequence_meta"] = {
        "kind": kind,
        "length": len(seq),
        "sha256": digest,
        # never put full sequence in last_run public mirrors
    }
    card.last_run = prior
    store_card(user_data, card)
    return kind, digest[:12]



def classify_upload_name(filename: str) -> str | None:
    """Return kind: fasta|fastq|vcf|bed|bam|cram|None."""
    name = (filename or "").lower().strip()
    for suf, kind in (
        (".bam", "bam"),
        (".cram", "cram"),
        (".fastq.gz", "fastq"),
        (".fq.gz", "fastq"),
        (".fastq", "fastq"),
        (".fq", "fastq"),
        (".fasta.gz", "fasta"),
        (".fa.gz", "fasta"),
        (".fna.gz", "fasta"),
        (".fasta", "fasta"),
        (".fa", "fasta"),
        (".fna", "fasta"),
        (".vcf.gz", "vcf"),
        (".vcf", "vcf"),
        (".bed.gz", "bed"),
        (".bed", "bed"),
    ):
        if name.endswith(suf):
            return kind
    return None


def _decode_upload(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _fastq_to_sequence_blob(text: str, max_reads: int = ANNOTATE_FASTQ_MAX_READS) -> str:
    """Concatenate first N FASTQ read sequences (no qualities)."""
    lines = (text or "").splitlines()
    seqs: list[str] = []
    i = 0
    while i + 1 < len(lines) and len(seqs) < max_reads:
        if lines[i].startswith("@"):
            seqs.append(lines[i + 1].strip())
            i += 4
        else:
            i += 1
    return "".join(seqs)


def _vcf_assembly_hint(text: str) -> str | None:
    for line in (text or "").splitlines()[:80]:
        if line.startswith("##reference=") or "GRCh38" in line or "hg38" in line:
            if "37" in line or "hg19" in line.lower() or "GRCh37" in line:
                return "hg19"
            return "hg38"
        if "GRCh37" in line or "hg19" in line:
            return "hg19"
    return None


def process_upload(
    user_data: dict[str, Any],
    filename: str,
    data: bytes,
) -> tuple[str, list[CnvResult] | None, GateResult | None, str | None]:
    """Third intake: Telegram document → coords or SEQUENCE. Discord dark."""
    if load_card(user_data) is None:
        end_annotate(user_data)
        return MSG_NO_CARD, None, None, "no_card"

    kind = classify_upload_name(filename)
    if kind in ("bam", "cram"):
        end_annotate(user_data)
        return MSG_UPLOAD_REFUSE_BAM, None, None, "bam"
    if kind is None:
        user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
        return MSG_UPLOAD_BAD_TYPE, None, None, "bad_type"

    n = len(data or b"")
    if kind in ("fasta", "fastq") and n > ANNOTATE_MAX_FASTA_BYTES:
        user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
        return MSG_UPLOAD_OVERSIZE, None, None, "oversize"
    if kind in ("vcf", "bed") and n > ANNOTATE_MAX_VCF_BED_BYTES:
        user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
        return MSG_UPLOAD_OVERSIZE, None, None, "oversize"

    text = _decode_upload(data or b"")
    if kind == "fastq":
        blob = _fastq_to_sequence_blob(text)
        if not blob:
            user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
            return MSG_HELPER, None, None, "helper"
        return process_paste(user_data, blob)
    if kind == "fasta":
        return process_paste(user_data, text)
    if kind in ("vcf", "bed"):
        # Prefer header assembly; else default GRCh38 via process_paste
        hint = _vcf_assembly_hint(text) if kind == "vcf" else None
        if hint == "hg19" and "##assembly=" not in text.lower():
            text = "##assembly=GRCh37\n" + text
        return process_paste(user_data, text)
    user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
    return MSG_UPLOAD_BAD_TYPE, None, None, "bad_type"


def process_paste(
    user_data: dict[str, Any],
    text: str,
    *,
    genome_build: str = DEFAULT_GENOME_BUILD,
) -> tuple[str, list[CnvResult] | None, GateResult | None, str | None]:
    """Dual intake: coords → ClassifyCNV; raw sequence → secure card SEQUENCE.

    Returns (reply_or_brief, results|None, gate|None, status).
    status: helper|block|review|tool|ok|seq|no_card|fasta
    Coords path disarms on ok; seq path disarms on seq; helper re-arms.
    """
    if load_card(user_data) is None:
        end_annotate(user_data)
        return MSG_NO_CARD, None, None, "no_card"

    raw = (text or "").strip()
    if not raw:
        user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
        return MSG_HELPER, None, None, "helper"

    intervals = parse_cnv_lines(raw)
    if intervals:
        build = extract_assembly(raw) or DEFAULT_GENOME_BUILD

        gate_result = bioscreen_for_paste(raw)
        if gate_result.decision is Decision.BLOCK:
            end_annotate(user_data)
            return MSG_COMMEC_BLOCK, None, gate_result, "block"
        if gate_result.decision is Decision.REVIEW:
            end_annotate(user_data)
            from .bioscreen import refuse_message

            return refuse_message(gate_result), None, gate_result, "review"

        if not classifycnv_available():
            end_annotate(user_data)
            return MSG_TOOL_DOWN, None, gate_result, "tool"

        try:
            results = run_classifycnv(intervals, genome_build=build)
        except RuntimeError:
            end_annotate(user_data)
            return MSG_TOOL_DOWN, None, gate_result, "tool"

        brief = render_annotate_md(results, gate_result)
        _stash_results_on_card(user_data, results, brief)
        end_annotate(user_data)
        return brief, results, gate_result, "ok"

    # --- Raw sequence intake (no CNV invent) ---
    extracted = extract_raw_sequence(raw)
    if extracted is None:
        # FASTA-looking with no usable body, or prose
        if re.search(r"(?m)^>\S+", raw) and not normalize_sequence(
            re.sub(r"(?m)^>.*$", "", raw)
        ):
            user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
            return MSG_FASTA_REFUSE, None, None, "fasta"
        user_data[ANNOTATE_KEY] = {"armed_at": datetime.now(timezone.utc).isoformat()}
        return MSG_HELPER, None, None, "helper"

    seq, kind = extracted
    gate_result: GateResult | None = None
    if kind in ("dna", "rna"):
        gate_result = gate(seq)
        if gate_result.decision is Decision.BLOCK:
            end_annotate(user_data)
            return MSG_SEQ_BLOCK, None, gate_result, "block"
        if gate_result.decision is Decision.REVIEW:
            end_annotate(user_data)
            from .bioscreen import refuse_message

            return refuse_message(gate_result), None, gate_result, "review"
    # AA: store only — never reverse-translate, never invent CNVs
    kind_label, hash12 = store_sequence_on_card(user_data, seq, kind)
    end_annotate(user_data)
    msg = MSG_SEQ_STORED.format(kind=kind_label.upper(), n=len(seq), hash12=hash12)
    if kind in ("dna", "rna"):
        from .annotate_parts import MSG_HINT_AFTER_SEQ
        msg = f"{msg} {MSG_HINT_AFTER_SEQ}"
    return msg, None, gate_result, "seq"



def success_caption(n: int) -> str:
    return MSG_SAVED.format(n=n)
