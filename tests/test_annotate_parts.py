"""Tests for /annotate parts v1a (FEATURE-annotate-parts) with mocked Bakta/GFF."""

from __future__ import annotations

import unittest
from unittest import mock

from src import annotate_parts as parts_mod
from src.bioscreen import Decision, GateResult
from src.context_card import ContextCard, load_card, store_card

SAMPLE_GFF = """\
##gff-version 3
##sequence-region query 1 1200
query\tbakta\tCDS\t100\t600\t.\t+\t0\tID=cds1;Name=lacZ;product=beta-galactosidase
query\tbakta\ttRNA\t700\t772\t.\t-\t.\tID=trna1;Name=tRNA-Ala
query\tbakta\trRNA\t800\t1300\t.\t+\t.\tID=rrna1;Name=16S
query\tbakta\tpromoter\t20\t80\t.\t+\t.\tID=p1;Name=pTac
query\tbakta\tterminator\t1400\t1450\t.\t+\t.\tID=term1;Name=T7te
query\tbakta\tCRISPR\t1500\t1700\t.\t+\t.\tID=crispr1;Name=CRISPR1
query\tbakta\tgene\t100\t600\t.\t+\t.\tID=gene1;Name=lacZ
query\tbakta\tregion\t1\t2000\t.\t+\t.\tID=region1
"""

DNA = "ATGC" * 80  # 320 nt
AA = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVKLD"


def _pass_gate() -> GateResult:
    return GateResult(
        decision=Decision.PASS,
        alphabet="dna",
        screen="mocked",
        detail="test pass",
    )


class TestParseGff3(unittest.TestCase):
    def test_maps_types_skips_gene_region(self):
        feats = parts_mod.parse_gff3(SAMPLE_GFF)
        types = [f["type"] for f in feats]
        self.assertIn("CDS", types)
        self.assertIn("tRNA", types)
        self.assertIn("rRNA", types)
        self.assertIn("promoter", types)
        self.assertIn("terminator", types)
        self.assertIn("CRISPR", types)
        self.assertNotIn("gene", types)
        self.assertTrue(all(f["id"].startswith("f") for f in feats))
        self.assertTrue(all(f["source"] == "bakta" for f in feats))


class TestProcessParts(unittest.TestCase):
    def test_no_card(self):
        msg, payload, gate, status = parts_mod.process_parts({})
        self.assertEqual(status, "no_card")
        self.assertIsNone(payload)

    def test_aa_refuse(self):
        ud: dict = {}
        store_card(ud, ContextCard(raw_text="t", sequence=AA))
        msg, payload, gate, status = parts_mod.process_parts(ud)
        self.assertEqual(status, "aa")
        self.assertIsNone(payload)
        self.assertIn("amino-acid", msg.lower())

    def test_bakta_missing_fail_closed(self):
        ud: dict = {}
        store_card(ud, ContextCard(raw_text="t", sequence=DNA))
        with mock.patch.object(parts_mod, "gate", return_value=_pass_gate()):
            with mock.patch.object(parts_mod, "bakta_available", return_value=False):
                msg, payload, gate, status = parts_mod.process_parts(ud)
        self.assertEqual(status, "tool")
        self.assertIsNone(payload)
        self.assertIn("Bakta", msg)

    def test_mocked_gff_success_schema(self):
        ud: dict = {}
        store_card(ud, ContextCard(raw_text="t", sequence=DNA))
        with mock.patch.object(parts_mod, "gate", return_value=_pass_gate()):
            msg, payload, gate, status = parts_mod.process_parts(
                ud, gff_override=SAMPLE_GFF
            )
        self.assertEqual(status, "ok")
        assert payload is not None
        self.assertIn("seq_meta", payload)
        self.assertEqual(payload["seq_meta"]["kind"], "dna")
        self.assertEqual(payload["seq_meta"]["length"], len(DNA))
        self.assertEqual(len(payload["seq_meta"]["sha256_12"]), 12)
        self.assertIn("features", payload)
        self.assertIn("counts", payload)
        self.assertNotIn("gff3", payload)
        self.assertNotIn(DNA, str(payload))
        self.assertIn("sha256", msg.lower())
        card = load_card(ud)
        assert card is not None and isinstance(card.last_run, dict)
        self.assertEqual(card.last_run.get("kind"), "annotate_parts")
        self.assertIn("parts", card.last_run)
        self.assertNotIn("gff3", card.last_run["parts"])
        pub = parts_mod.get_parts_public(ud)
        assert pub is not None
        self.assertNotIn("gff3", pub)
        for key in ("features", "counts", "seq_meta"):
            self.assertIn(key, pub)

    def test_cnv_untouched_on_card(self):
        ud: dict = {}
        store_card(
            ud,
            ContextCard(
                raw_text="t",
                sequence=DNA,
                last_run={"kind": "annotate_cnv", "cnv": [{"id": "x"}]},
            ),
        )
        with mock.patch.object(parts_mod, "gate", return_value=_pass_gate()):
            parts_mod.process_parts(ud, gff_override=SAMPLE_GFF)
        card = load_card(ud)
        assert card is not None and isinstance(card.last_run, dict)
        self.assertIn("cnv", card.last_run)
        self.assertEqual(card.last_run["cnv"], [{"id": "x"}])
        self.assertIn("parts", card.last_run)


class TestHintCopy(unittest.TestCase):
    def test_hint_string(self):
        self.assertIn("/annotate parts", parts_mod.MSG_HINT_AFTER_SEQ)
        self.assertIn("Bakta", parts_mod.MSG_HINT_AFTER_SEQ)


if __name__ == "__main__":
    unittest.main()
