"""Tests for history_sorter — clinic.md / lab.ipynb / search.json single-writer rules."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import history, sorter, store


DOI_A = "10.1101/2024.01.01.123456"
DOI_B = "10.1038/s41586-024-00001-2"

EVIDENCE_BRIEF_A = f"""\
# Evidence brief: KRAS

Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded.

## Findings

- KRAS G12C covalent inhibitors show activity (Smith et al., 2024).

## References

Smith, J.A., 2024. KRAS paper. Nature. https://doi.org/{DOI_A}
"""

EVIDENCE_BRIEF_A2 = f"""\
# Evidence brief: KRAS updated

Sources: peer-reviewed (Europe PMC / MEDLINE); preprints excluded.

## Findings

- Updated claim on KRAS G12C (Smith et al., 2024).

## References

Smith, J.A., 2024. KRAS paper revised. Nature. https://doi.org/{DOI_A}
"""

RESEARCH_BRIEF = f"""\
# Research brief: KRAS preprints

## Findings

- Preprint explores KRAS pocket dynamics (Lee et al., 2024).

## References

Lee, K., 2024. KRAS dynamics. bioRxiv. https://doi.org/{DOI_B}
"""

HARVARD_LINE = f"Smith, J.A., 2024. KRAS paper. Nature. https://doi.org/{DOI_A}"


class SorterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patient-store-"))
        self.user_id = 424242
        self.patient_id = "11111111-2222-3333-4444-555555555555"
        self.root_patch = mock.patch.object(store, "STORE_ROOT", self.tmp)
        self.root_patch.start()
        store.ensure_patient_files(self.user_id, self.patient_id)

    def tearDown(self) -> None:
        self.root_patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _clinic(self) -> str:
        return store.clinic_path(self.user_id, self.patient_id).read_text(encoding="utf-8")

    def _lab(self) -> dict:
        return json.loads(store.lab_path(self.user_id, self.patient_id).read_text(encoding="utf-8"))

    def _search(self) -> dict:
        return json.loads(store.search_path(self.user_id, self.patient_id).read_text(encoding="utf-8"))

    def _apply(self, kind: str, payload: dict) -> None:
        event = {
            "id": __import__("uuid").uuid4().hex,
            "ts": "2026-09-14T12:00:00+00:00",
            "kind": kind,
            "payload": {**payload, "patient_id": self.patient_id},
        }
        sorter.apply_event(self.user_id, event)

    def test_research_goes_to_lab_not_clinic_evidence(self) -> None:
        self._apply(
            history.KIND_RESEARCH,
            {"brief_md": RESEARCH_BRIEF, "dois": [DOI_B]},
        )
        clinic = self._clinic()
        self.assertNotIn(DOI_B, clinic)
        self.assertNotIn("## Literature (preprint)", clinic)
        # Must not land under Evidence
        evidence = sorter._get_section_body(clinic, "Evidence")
        self.assertIsNotNone(evidence)
        self.assertNotIn(DOI_B, evidence[0])

        lab = self._lab()
        cells = lab.get("cells") or []
        self.assertTrue(cells)
        tags = (cells[-1].get("metadata") or {}).get("tags") or []
        self.assertIn("literature-preprint", tags)
        src = "".join(cells[-1].get("source") or [])
        self.assertIn(DOI_B, src)
        self.assertIn("## Literature (preprint)", src)
        # Tone fence marker present; not peer-reviewed Evidence header misuse
        self.assertIn("preprint", src.lower())

        search = self._search()
        files = {e.get("file") for e in search.get("entries") or []}
        self.assertIn(store.LAB_NAME, files)
        self.assertNotIn(
            store.CLINIC_NAME,
            {
                e.get("file")
                for e in search.get("entries") or []
                if e.get("doi", "").lower() == DOI_B.lower()
            },
        )

    def test_evidence_doi_upsert_replaces_not_duplicates(self) -> None:
        self._apply(
            history.KIND_EVIDENCE,
            {"brief_md": EVIDENCE_BRIEF_A, "dois": [DOI_A]},
        )
        clinic1 = self._clinic()
        self.assertIn(DOI_A, clinic1)
        self.assertIn("#### References", clinic1)
        self.assertIn(HARVARD_LINE.split("https://")[0].strip()[:20], clinic1)
        count1 = clinic1.lower().count(DOI_A.lower())

        self._apply(
            history.KIND_EVIDENCE,
            {"brief_md": EVIDENCE_BRIEF_A2, "dois": [DOI_A]},
        )
        clinic2 = self._clinic()
        # Still one evidence unit for this DOI (may appear in findings + refs)
        units = []
        found = sorter._get_section_body(clinic2, "Evidence")
        assert found is not None
        _header, unit_list = sorter._split_h3_units(found[0])
        for u in unit_list:
            if DOI_A.lower() in u.lower():
                units.append(u)
        self.assertEqual(len(units), 1, msg="DOI upsert must replace, not duplicate units")
        self.assertIn("Updated claim", clinic2)
        self.assertIn("#### References", clinic2)
        self.assertIn(f"https://doi.org/{DOI_A}", clinic2)
        # Harvard bottom preserved (never stripped)
        self.assertRegex(clinic2, r"#### References[\s\S]*https://doi.org/" + __import__("re").escape(DOI_A))

    def test_harvard_still_present_after_upsert(self) -> None:
        self._apply(
            history.KIND_EVIDENCE,
            {"brief_md": EVIDENCE_BRIEF_A, "dois": [DOI_A]},
        )
        self._apply(
            history.KIND_EVIDENCE,
            {"brief_md": EVIDENCE_BRIEF_A2, "dois": [DOI_A]},
        )
        clinic = self._clinic()
        self.assertIn("#### References", clinic)
        self.assertIn(f"https://doi.org/{DOI_A}", clinic)

    def test_onboard_demographics_no_age_digits(self) -> None:
        self._apply(history.KIND_ONBOARD, {})
        clinic = self._clinic()
        self.assertIn("Demographics: on file.", clinic)
        self.assertNotIn("Demographics: not on file.", clinic)
        # No biometric digits / raw values leaked
        import re as _re
        self.assertIsNone(_re.search(r"\bage\b.*\d", clinic, flags=_re.I))
        self.assertNotIn("75", clinic)
        self.assertNotIn("weight", clinic.lower())
        self.assertNotIn("height", clinic.lower())
        self.assertNotIn("bmi", clinic.lower())

    def test_note_line_without_body(self) -> None:
        secret_body = "Patient reports severe chest pain overnight confidential"
        self._apply(
            history.KIND_NOTE,
            {"note_id": "abc123deadbeef", "ts": "2026-09-14T12:00:00+00:00"},
        )
        clinic = self._clinic()
        self.assertIn("abc123deadbeef", clinic)
        self.assertIn("note on file", clinic)
        self.assertNotIn(secret_body, clinic)
        self.assertNotIn("chest pain", clinic)

    def test_scribe_unlinked_to_inbox_not_clinic_minutes(self) -> None:
        minutes = "# Meeting minutes\n\n## Summary\n\nDiscussed KRAS program.\n"
        event = {
            "id": "scribeevent001",
            "ts": "2026-09-14T12:00:00+00:00",
            "kind": history.KIND_SCRIBE,
            "payload": {
                "minutes_md": minutes,
                "linked": False,
                "patient_id": self.patient_id,  # even with patient, v1 → inbox
            },
        }
        sorter.apply_event(self.user_id, event)
        clinic = self._clinic()
        minutes_sec = sorter._get_section_body(clinic, "Meeting minutes")
        if minutes_sec:
            self.assertNotIn("Discussed KRAS program", minutes_sec[0])
        self.assertNotIn("Discussed KRAS program", clinic)
        inbox = store.inbox_dir(self.user_id)
        files = list(inbox.glob("scribe-*.md"))
        self.assertTrue(files, msg="unlinked scribe must land in inbox/")
        body = files[0].read_text(encoding="utf-8")
        self.assertIn("Discussed KRAS program", body)

    def test_bioscreen_no_sequence_in_md(self) -> None:
        seq = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEY"
        self._apply(
            history.KIND_BIOSECURITY,
            {"decision": "BLOCK", "ts": "2026-09-14T12:00:00+00:00"},
        )
        clinic = self._clinic()
        self.assertIn("BLOCK", clinic)
        self.assertIn("## Biosecurity", clinic)
        self.assertNotIn(seq, clinic)
        self.assertIn("No sequence or score is recorded", clinic)

    def test_emit_scrub_blocks_sequence_and_biometrics(self) -> None:
        eid = history.emit(
            self.user_id,
            history.KIND_BIOSECURITY,
            {
                "decision": "REVIEW",
                "sequence": "ACDEFGHIKLMNPQRSTVWY" * 5,
                "age_years": 75,
                "patient_id": self.patient_id,
            },
        )
        pending = history.pending_events(self.user_id)
        match = [e for e in pending if e["id"] == eid][0]
        payload = match["payload"]
        self.assertEqual(payload.get("decision"), "REVIEW")
        self.assertNotIn("sequence", payload)
        self.assertNotIn("age_years", payload)

    def test_research_doi_upsert_in_lab(self) -> None:
        self._apply(
            history.KIND_RESEARCH,
            {"brief_md": RESEARCH_BRIEF, "dois": [DOI_B]},
        )
        brief2 = RESEARCH_BRIEF.replace("pocket dynamics", "UPDATED dynamics")
        self._apply(
            history.KIND_RESEARCH,
            {"brief_md": brief2, "dois": [DOI_B]},
        )
        lab = self._lab()
        preprint_cells = [
            c
            for c in lab.get("cells") or []
            if "literature-preprint" in ((c.get("metadata") or {}).get("tags") or [])
        ]
        # One cell for DOI_B after upsert
        matching = []
        for c in preprint_cells:
            src = "".join(c.get("source") or [])
            if DOI_B.lower() in src.lower():
                matching.append(c)
        self.assertEqual(len(matching), 1)
        src = "".join(matching[0].get("source") or [])
        self.assertIn("UPDATED dynamics", src)

    def test_corpus_bleed_research_not_in_evidence(self) -> None:
        """Corpus bleed: preprint research must never appear under clinic ## Evidence."""
        self._apply(
            history.KIND_RESEARCH,
            {"brief_md": RESEARCH_BRIEF, "dois": [DOI_B]},
        )
        self._apply(
            history.KIND_EVIDENCE,
            {"brief_md": EVIDENCE_BRIEF_A, "dois": [DOI_A]},
        )
        clinic = self._clinic()
        evidence = sorter._get_section_body(clinic, "Evidence")
        assert evidence is not None
        self.assertIn(DOI_A, evidence[0])
        self.assertNotIn(DOI_B, evidence[0])
        self.assertNotIn("bioRxiv", evidence[0])
        self.assertNotIn("Preprint brief", clinic)

    def test_file_names_are_clinic_lab_search(self) -> None:
        pdir = store.patient_dir(self.user_id, self.patient_id)
        names = {p.name for p in pdir.iterdir()}
        self.assertIn("clinic.md", names)
        self.assertIn("lab.ipynb", names)
        self.assertIn("search.json", names)
        self.assertNotIn("clinical.md", names)
        self.assertNotIn("biological.ipynb", names)

    def test_process_user_idempotent(self) -> None:
        history.emit(
            self.user_id,
            history.KIND_NOTE,
            {
                "note_id": "idem001",
                "ts": "2026-09-14T12:00:00+00:00",
                "patient_id": self.patient_id,
            },
        )
        n1 = sorter.process_user(self.user_id)
        n2 = sorter.process_user(self.user_id)
        self.assertGreaterEqual(n1, 1)
        self.assertEqual(n2, 0)
        clinic = self._clinic()
        self.assertEqual(clinic.count("idem001"), 1)


if __name__ == "__main__":
    unittest.main()
