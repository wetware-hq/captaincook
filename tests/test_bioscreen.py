"""Unit tests for pre-GPU biosecurity gate. No real commec install required."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from src.bioscreen import (
    REFUSE_BLOCK_SCREENED,
    REFUSE_BLOCK_TOOL,
    REFUSE_REVIEW_AMBIGUOUS,
    REFUSE_REVIEW_INCONCLUSIVE,
    Decision,
    classify_alphabet,
    gate,
    refuse_message,
)


def _write_fake_commec(tmpdir: Path, mode: str) -> Path:
    """Create a tiny fake COMMEC_BIN that prints a controllable token."""
    path = tmpdir / f"fake_commec_{mode}.sh"
    if mode == "CLEAR":
        body = "#!/bin/sh\necho CLEAR\nexit 0\n"
    elif mode == "SOC":
        body = "#!/bin/sh\necho SOC\nexit 0\n"
    elif mode == "PARTIAL":
        body = "#!/bin/sh\necho PARTIAL\nexit 0\n"
    elif mode == "hang":
        body = "#!/bin/sh\nsleep 30\necho CLEAR\nexit 0\n"
    elif mode == "crash":
        body = "#!/bin/sh\necho boom >&2\nexit 2\n"
    elif mode == "unknown":
        body = "#!/bin/sh\necho gibberish-no-token\nexit 0\n"
    else:
        raise ValueError(mode)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


DNA50 = "ACGT" * 13  # 52 bp
DNA49 = "ACGT" * 12 + "A"  # 49 bp
KRAS_LIKE = "MKTIIALSYIFCLVFA"


class TestClassifyAlphabet(unittest.TestCase):
    def test_dna_preferred_over_aa(self):
        self.assertEqual(classify_alphabet("acgtacgt"), "dna")
        self.assertEqual(classify_alphabet("AAAA"), "dna")

    def test_rna_requires_u(self):
        self.assertEqual(classify_alphabet("ACGUACGU"), "rna")
        self.assertEqual(classify_alphabet("UUUU"), "rna")

    def test_aa_needs_protein_defining(self):
        self.assertEqual(classify_alphabet(KRAS_LIKE), "aa")
        self.assertEqual(classify_alphabet("DEFHIK"), "aa")

    def test_mixed_tu_ambiguous(self):
        self.assertEqual(classify_alphabet("ACGTU"), "ambiguous")

    def test_outside_alphabet_ambiguous(self):
        # Characters outside DNA/RNA/AA → ambiguous (not a DNA guess).
        self.assertEqual(classify_alphabet("ACGT@#"), "ambiguous")
        self.assertEqual(classify_alphabet("ACGT123"), "ambiguous")

    def test_whitespace_stripped(self):
        self.assertEqual(classify_alphabet("  ac gt \n"), "dna")


class TestGateWithFakeCommec(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_soc_dna_blocks(self):
        fake = _write_fake_commec(self.tmpdir, "SOC")
        result = gate(DNA50, bin_name=str(fake), timeout_sec=5)
        self.assertEqual(result.decision, Decision.BLOCK)
        self.assertEqual(result.screen, "commec_soc")
        self.assertEqual(refuse_message(result), REFUSE_BLOCK_SCREENED)
        self.assertTrue(refuse_message(result).endswith("."))
        self.assertIn("Research use only", refuse_message(result))

    def test_short_clear_dna_review_no_commec_needed(self):
        # Length policy → REVIEW without requiring a working binary.
        result = gate(DNA49, bin_name="/nonexistent/commec-should-not-run", timeout_sec=5)
        self.assertEqual(result.decision, Decision.REVIEW)
        self.assertEqual(result.screen, "nt_too_short")
        self.assertEqual(refuse_message(result), REFUSE_REVIEW_INCONCLUSIVE)

    def test_benign_dna_pass(self):
        fake = _write_fake_commec(self.tmpdir, "CLEAR")
        result = gate(DNA50, bin_name=str(fake), timeout_sec=5)
        self.assertEqual(result.decision, Decision.PASS)
        self.assertEqual(result.screen, "commec_clear")
        self.assertTrue(result.allowed)

    def test_kras_aa_skipped_no_commec(self):
        # Point at missing binary; AA path must still PASS without calling it.
        result = gate(KRAS_LIKE, bin_name="/nonexistent/commec-must-not-run", timeout_sec=5)
        self.assertEqual(result.decision, Decision.PASS)
        self.assertEqual(result.alphabet, "aa")
        self.assertEqual(result.screen, "skipped_aa")

    def test_mixed_alphabet_review_no_commec(self):
        result = gate("ACGTU", bin_name="/nonexistent/commec-must-not-run", timeout_sec=5)
        self.assertEqual(result.decision, Decision.REVIEW)
        self.assertEqual(result.screen, "ambiguous_alphabet")
        self.assertEqual(refuse_message(result), REFUSE_REVIEW_AMBIGUOUS)

        result2 = gate("ACGT@XYZ", bin_name="/nonexistent/commec-must-not-run", timeout_sec=5)
        self.assertEqual(result2.decision, Decision.REVIEW)
        self.assertEqual(refuse_message(result2), REFUSE_REVIEW_AMBIGUOUS)

    def test_commec_missing_blocks(self):
        result = gate(DNA50, bin_name="/nonexistent/no-commec-here", timeout_sec=5)
        self.assertEqual(result.decision, Decision.BLOCK)
        self.assertEqual(result.screen, "commec_missing")
        self.assertEqual(refuse_message(result), REFUSE_BLOCK_TOOL)

    def test_commec_timeout_blocks(self):
        fake = _write_fake_commec(self.tmpdir, "hang")
        result = gate(DNA50, bin_name=str(fake), timeout_sec=1)
        self.assertEqual(result.decision, Decision.BLOCK)
        self.assertEqual(result.screen, "commec_timeout")
        self.assertEqual(refuse_message(result), REFUSE_BLOCK_TOOL)

    def test_partial_review(self):
        fake = _write_fake_commec(self.tmpdir, "PARTIAL")
        result = gate(DNA50, bin_name=str(fake), timeout_sec=5)
        self.assertEqual(result.decision, Decision.REVIEW)
        self.assertEqual(result.screen, "commec_review")
        self.assertEqual(refuse_message(result), REFUSE_REVIEW_INCONCLUSIVE)

    def test_no_hmm_clear_reviews_when_taxonomy_skipped(self):
        # exit 0 + no CLEAR/SOC: cannot taxonomically clear on --skip-tx → REVIEW
        fake = _write_fake_commec(self.tmpdir, "unknown")
        result = gate(DNA50, bin_name=str(fake), timeout_sec=5)
        self.assertEqual(result.decision, Decision.REVIEW)
        self.assertEqual(result.screen, "commec_no_tax_clear")
        self.assertEqual(refuse_message(result), REFUSE_REVIEW_INCONCLUSIVE)

    def test_skip_tx_flag_is_passed(self):
        path = self.tmpdir / "fake_commec_skip.sh"
        path.write_text(
            "#!/bin/sh\n"
            "echo \"$@\" > \"$(dirname \"$0\")/args.txt\"\n"
            "echo CLEAR\n"
            "exit 0\n",
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | 0o111)
        result = gate(DNA50, bin_name=str(path), timeout_sec=5)
        self.assertEqual(result.decision, Decision.PASS)
        args = (self.tmpdir / "args.txt").read_text()
        self.assertIn("--skip-tx", args)

    def test_refuse_strings_are_full_sentences(self):
        for s in (
            REFUSE_BLOCK_SCREENED,
            REFUSE_BLOCK_TOOL,
            REFUSE_REVIEW_AMBIGUOUS,
            REFUSE_REVIEW_INCONCLUSIVE,
        ):
            self.assertTrue(s[0].isupper(), s)
            self.assertTrue(s.endswith("."), s)
            self.assertNotIn("commec", s.lower())
            self.assertNotIn("SOC", s)
            self.assertNotIn("50", s)  # no bp cutoff dump


class TestEnvConfig(unittest.TestCase):
    def test_gate_reads_commec_bin_env(self):
        with tempfile.TemporaryDirectory() as td:
            fake = _write_fake_commec(Path(td), "CLEAR")
            old = os.environ.get("COMMEC_BIN")
            try:
                os.environ["COMMEC_BIN"] = str(fake)
                result = gate(DNA50, timeout_sec=5)
                self.assertEqual(result.decision, Decision.PASS)
            finally:
                if old is None:
                    os.environ.pop("COMMEC_BIN", None)
                else:
                    os.environ["COMMEC_BIN"] = old


if __name__ == "__main__":
    unittest.main()
