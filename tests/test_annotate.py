"""Tests for /annotate CNV v1a (FEATURE-annotate-cnv + TEMPLATE-annotate-cnv)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import annotate as annotate_mod
from src import history, sorter, store
from src.bioscreen import Decision, GateResult
from src.context_card import ContextCard, store_card


class TestParseCnv(unittest.TestCase):
    def test_interval_dup_del(self):
        text = "chr12:25205246-25250929 DUP\nchr17:43044295-43125483 DEL"
        ivs = annotate_mod.parse_cnv_lines(text)
        self.assertEqual(len(ivs), 2)
        self.assertEqual(ivs[0].svtype, "DUP")
        self.assertEqual(ivs[0].chrom, "chr12")
        self.assertEqual(ivs[1].svtype, "DEL")
        self.assertIn("kb", ivs[0].span_label)

    def test_bed(self):
        ivs = annotate_mod.parse_cnv_lines("chr12\t25200000\t25300000\tDUP")
        self.assertEqual(len(ivs), 1)
        self.assertEqual(ivs[0].source, "bed")

    def test_vcf_sv(self):
        line = "chr12 25205246 . N <DUP> . . SVTYPE=DUP;END=25250929"
        ivs = annotate_mod.parse_cnv_lines(line)
        self.assertEqual(len(ivs), 1)
        self.assertEqual(ivs[0].svtype, "DUP")
        self.assertEqual(ivs[0].source, "vcf")

    def test_prose_empty(self):
        self.assertEqual(
            annotate_mod.parse_cnv_lines(
                "The patient may have a duplication of clinical interest near KRAS."
            ),
            [],
        )

    def test_aa_only(self):
        aa = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVKLD"
        self.assertTrue(annotate_mod.looks_aa_only(aa))
        self.assertFalse(
            annotate_mod.looks_aa_only("chr12:25205246-25250929 DUP")
        )


class TestCopyLocked(unittest.TestCase):
    def test_helper_verbatim(self):
        self.assertIn("I could not read that as CNV intervals", annotate_mod.MSG_HELPER)
        self.assertIn("chr12:25205246-25250929 DUP", annotate_mod.MSG_HELPER)

    def test_aa_refuse(self):
        self.assertIn("amino-acid sequence", annotate_mod.MSG_AA_ONLY)

    def test_help_one_liner(self):
        self.assertTrue(annotate_mod.HELP_ONE_LINER.startswith("/annotate —"))


class TestBioscreenOrthogonal(unittest.TestCase):
    def test_interval_only_pass(self):
        g = annotate_mod.bioscreen_for_paste("chr12:25205246-25250929 DUP")
        self.assertEqual(g.decision, Decision.PASS)
        self.assertEqual(g.screen, "cnv_interval_no_seq")
        stamp = annotate_mod.bioscreen_stamp_sentence(g)
        self.assertIn("PASS", stamp)
        self.assertIn("separate from the ACMG", stamp)

    def test_block_message(self):
        self.assertIn("biosecurity screen blocked", annotate_mod.MSG_COMMEC_BLOCK)


class TestArmHelper(unittest.TestCase):
    def test_no_card(self):
        ud: dict = {}
        self.assertEqual(annotate_mod.start_annotate(ud), annotate_mod.MSG_NO_CARD)

    def test_helper_rearm(self):
        ud: dict = {}
        store_card(ud, ContextCard(raw_text="test", sequence="MKTAYIAKQR"))
        reply, results, gate, status = annotate_mod.process_paste(
            ud, "This is pure prose about a possible duplication."
        )
        self.assertEqual(status, "helper")
        self.assertEqual(reply, annotate_mod.MSG_HELPER)
        self.assertTrue(annotate_mod.is_armed(ud))
        self.assertIsNone(results)

    def test_aa_refuse_path(self):
        ud: dict = {}
        store_card(ud, ContextCard(raw_text="test", sequence="MKTAYIAKQR"))
        aa = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVKLD"
        reply, results, gate, status = annotate_mod.process_paste(ud, aa)
        self.assertEqual(status, "aa")
        self.assertEqual(reply, annotate_mod.MSG_AA_ONLY)


@unittest.skipUnless(annotate_mod.classifycnv_available(), "ClassifyCNV/bedtools missing")
class TestClassifyCnvSmoke(unittest.TestCase):
    def test_kras_region_dup(self):
        ivs = annotate_mod.parse_cnv_lines("chr12:25205246-25250929 DUP")
        results = annotate_mod.run_classifycnv(ivs, genome_build="hg38")
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertTrue(r.classification)
        genes = set(r.dosage_genes) | set(r.coding_genes)
        self.assertIn("KRAS", genes)
        brief = annotate_mod.render_annotate_md(
            results,
            GateResult(Decision.PASS, None, "cnv_interval_no_seq"),
        )
        self.assertIn("# Chromosomal annotation", brief)
        self.assertIn("## Biosecurity screen", brief)
        self.assertIn("## Criteria breakdown", brief)
        self.assertIn("not a diagnosis", brief.lower())
        self.assertIn("KRAS", brief)


class TestSorterAnnotate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="annotate-store-"))
        self.user_id = 909090
        self.patient_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.root_patch = mock.patch.object(store, "STORE_ROOT", self.tmp)
        self.root_patch.start()
        store.ensure_patient_files(self.user_id, self.patient_id)

    def tearDown(self) -> None:
        self.root_patch.stop()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clinic_and_search(self):
        sorter.apply_annotate(
            self.user_id,
            self.patient_id,
            {
                "cnv_ids": ["abc123def456"],
                "n_intervals": 1,
                "classifications": ["Uncertain significance"],
                "brief_md": "# Chromosomal annotation\n\n## Findings\n\n- Interval: chr12:1-2 DUP\n",
                "bioscreen_decision": "PASS",
            },
        )
        clinic = store.clinic_path(self.user_id, self.patient_id).read_text(encoding="utf-8")
        self.assertIn("## Chromosomal", clinic)
        self.assertIn("cnv:abc123def456", clinic)
        self.assertNotIn("lab.ipynb", clinic)
        import json
        search = json.loads(store.search_path(self.user_id, self.patient_id).read_text(encoding='utf-8'))
        titles = [e.get("title") for e in search.get("entries") or []]
        self.assertIn("cnv:abc123def456", titles)


class TestAppStrip(unittest.TestCase):
    def test_empty_none_yet(self):
        html = annotate_mod  # silence
        from src import app_html

        out = app_html.chromosomal_strip_html({})
        self.assertIn("None yet", out)

    def test_strip_has_filters_and_panel(self):
        from src import app_html
        from src.context_card import ContextCard, store_card

        ud: dict = {}
        card = ContextCard(raw_text="t", sequence="MKTAYIAKQR")
        card.last_run = {
            "kind": "annotate_cnv",
            "cnv": [
                {
                    "id": "testhash12ab",
                    "chrom": "chr12",
                    "start": 25205246,
                    "end": 25250929,
                    "svtype": "DUP",
                    "span": "45.7 kb",
                    "classification": "Uncertain significance",
                    "total_score": 0.0,
                    "criteria": {"2A": 0.0},
                    "dosage_genes": [],
                    "coding_genes": ["KRAS"],
                    "label": "chr12:25205246-25250929 DUP",
                }
            ],
        }
        store_card(ud, card)
        out = app_html.chromosomal_strip_html(ud)
        self.assertIn("cnv-filter-chr", out)
        self.assertIn("cnv-filter-sv", out)
        self.assertIn("cnv-panel", out)
        self.assertIn("cnv-bar", out)
        self.assertIn("Research use only", out)
        js = app_html.chromosomal_strip_js()
        self.assertIn("/evidence", js)
        self.assertIn("/variant", js)
        self.assertIn("not a diagnosis", js)


if __name__ == "__main__":
    unittest.main()
