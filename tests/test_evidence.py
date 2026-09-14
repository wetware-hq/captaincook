"""Unit tests for /evidence (peer-reviewed Europe PMC). DOI lock shared with /research."""

from __future__ import annotations

import json
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError

from src.evidence_client import (
    RESULT_CAP,
    EvidenceServiceError,
    QUERY_FILTER as EVIDENCE_QUERY_FILTER,
    build_query,
    parse_search_body,
    search_peer_reviewed,
)
from src.evidence_md import (
    CAPTION_HITS,
    CAPTION_ZERO,
    FINDINGS_ZERO,
    MSG_FAIL_CLOSED,
    MSG_MISSING_QUESTION,
    MSG_QUESTION_TOO_LONG,
    QUESTION_MAX_LEN,
    REFERENCES_ZERO,
    SOURCES_LINE,
    caption_for,
    question_error,
    render_evidence_md,
)
from src.research_client import (
    Author,
    QUERY_FILTER as RESEARCH_QUERY_FILTER,
    Record,
    parse_search_body as parse_research_body,
)
from src.research_md import harvard_reference, render_research_md


def _author(family: str, initials: str) -> dict:
    return {
        "fullName": f"{family} {initials.replace('.', '')}",
        "lastName": family,
        "initials": initials.replace(".", ""),
    }


def _med_hit(
    *,
    title: str,
    year: str,
    date: str,
    doi: str | None,
    journal: str = "Nature Medicine",
    source: str = "MED",
    authors: list[dict] | None = None,
    abstract: str | None = None,
    publisher: str | None = None,
) -> dict:
    row: dict = {
        "id": "12345678",
        "pmid": "12345678",
        "source": source,
        "title": title,
        "authorList": {
            "author": authors or [_author("Smith", "JA"), _author("Lee", "K")]
        },
        "pubYear": year,
        "firstPublicationDate": date,
        "journalInfo": {"journal": {"title": journal}},
    }
    if doi:
        row["doi"] = doi
        row["fullTextUrlList"] = {
            "fullTextUrl": [{"url": f"https://doi.org/{doi}", "documentStyle": "doi"}]
        }
    if abstract:
        row["abstractText"] = abstract
    if publisher:
        row["bookOrReportDetails"] = {"publisher": publisher}
    return row


def _payload(rows: list[dict]) -> bytes:
    body = {
        "version": "6.9",
        "hitCount": len(rows),
        "resultList": {"result": rows},
    }
    return json.dumps(body).encode("utf-8")


class FakeHTTP:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeHTTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _sample_rec(*, doi: str | None = "10.1000/example.1", year: str = "2024") -> Record:
    return Record(
        authors=(Author("Smith", "J.A"), Author("Lee", "K"), Author("Patel", "R")),
        year=year,
        title="KRAS G12C inhibitors in NSCLC",
        server="Nature Medicine",
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else "https://europepmc.org/article/MED/1",
        date=f"{year}-01-01",
        abstract="Sotorasib improves outcomes in KRAS G12C-mutant NSCLC in this trial.",
    )


class TestResearchFilterUnchanged(unittest.TestCase):
    def test_research_query_filter_still_ppr(self):
        self.assertIn("SRC:PPR", RESEARCH_QUERY_FILTER)
        self.assertIn('PUBLISHER:"bioRxiv"', RESEARCH_QUERY_FILTER)
        self.assertIn('PUBLISHER:"medRxiv"', RESEARCH_QUERY_FILTER)
        self.assertEqual(
            RESEARCH_QUERY_FILTER,
            'SRC:PPR AND (PUBLISHER:"bioRxiv" OR PUBLISHER:"medRxiv" '
            'OR JOURNAL:"bioRxiv" OR JOURNAL:"medRxiv")',
        )

    def test_evidence_filter_is_med_not_ppr(self):
        self.assertEqual(EVIDENCE_QUERY_FILTER, "SRC:MED NOT SRC:PPR")
        q = build_query("KRAS G12C inhibitors in NSCLC")
        self.assertEqual(
            q,
            "(KRAS G12C inhibitors in NSCLC) AND SRC:MED NOT SRC:PPR",
        )
        self.assertNotEqual(EVIDENCE_QUERY_FILTER, RESEARCH_QUERY_FILTER)


class TestPeerFilterExcludesPPR(unittest.TestCase):
    def test_drops_source_ppr_even_if_present(self):
        rows = [
            _med_hit(
                title="A slipped preprint",
                year="2026",
                date="2026-01-01",
                doi="10.1101/2026.01.01.1",
                source="PPR",
                publisher="bioRxiv",
                journal="bioRxiv",
            ),
            _med_hit(
                title="A real MEDLINE article on KRAS",
                year="2025",
                date="2025-06-01",
                doi="10.1000/nm.2025.1",
                source="MED",
                journal="Nature Medicine",
            ),
        ]
        records = parse_search_body(_payload(rows))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].server, "Nature Medicine")
        self.assertNotIn("bioRxiv", records[0].server.lower())
        self.assertNotIn("medrxiv", records[0].server.lower())


class TestDoiLock(unittest.TestCase):
    def test_drops_no_doi_when_doi_alternatives_exist(self):
        rows = [
            _med_hit(
                title="No DOI article",
                year="2026",
                date="2026-08-01",
                doi=None,
                journal="Some Journal",
            ),
            _med_hit(
                title="DOI article A",
                year="2025",
                date="2025-01-01",
                doi="10.1000/a.1",
            ),
            _med_hit(
                title="DOI article B",
                year="2024",
                date="2024-01-01",
                doi="10.1000/b.1",
            ),
        ]
        records = parse_search_body(_payload(rows))
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r.doi for r in records))
        md = render_evidence_md("KRAS", records)
        # Every reference line under ## References has doi.org
        refs = md.split("## References", 1)[1].strip().splitlines()
        refs = [ln for ln in refs if ln.strip() and ln.strip() != "None."]
        self.assertGreaterEqual(len(refs), 1)
        for ln in refs:
            self.assertIn("https://doi.org/", ln)
        self.assertNotIn("No DOI article", md)

    def test_render_drops_no_doi_even_if_passed_in(self):
        with_doi = _sample_rec(doi="10.1000/keep.1")
        without = _sample_rec(doi=None)
        without = Record(
            authors=without.authors,
            year="2026",
            title="Should be dropped",
            server="Journal",
            doi=None,
            url="https://europepmc.org/article/MED/9",
            date="2026-01-01",
        )
        md = render_evidence_md("q", [without, with_doi])
        self.assertIn("https://doi.org/10.1000/keep.1", md)
        self.assertNotIn("Should be dropped", md)
        refs = md.split("## References", 1)[1].strip().splitlines()
        for ln in refs:
            if ln.strip() and ln.strip() != "None.":
                self.assertIn("https://doi.org/", ln)

    def test_research_render_also_requires_doi_lines(self):
        with_doi = Record(
            authors=(Author("Smith", "J.A"),),
            year="2024",
            title="A covalent inhibitor series for KRAS G12C",
            server="bioRxiv",
            doi="10.1101/2024.01.01.123456",
            url="https://doi.org/10.1101/2024.01.01.123456",
            date="2024-01-01",
        )
        without = Record(
            authors=(Author("Anon", "A"),),
            year="2025",
            title="No DOI preprint",
            server="bioRxiv",
            doi=None,
            url="https://europepmc.org/article/PPR/1",
            date="2025-01-01",
        )
        md = render_research_md("KRAS", [without, with_doi])
        self.assertIn("https://doi.org/10.1101/2024.01.01.123456", md)
        self.assertNotIn("No DOI preprint", md)
        refs = md.split("## References", 1)[1].strip().splitlines()
        for ln in refs:
            if ln.strip() and ln.strip() != "None.":
                self.assertIn("https://doi.org/", ln)
        ref = harvard_reference(with_doi)
        self.assertIn("https://doi.org/", ref)

    def test_never_invents_doi(self):
        md = render_evidence_md("empty", [])
        self.assertIn(REFERENCES_ZERO, md)
        self.assertNotIn("https://doi.org/", md)


class TestHarvardAtBottom(unittest.TestCase):
    def test_references_after_findings(self):
        md = render_evidence_md("KRAS G12C", [_sample_rec()])
        self.assertLess(md.find("## Findings"), md.find("## References"))
        self.assertTrue(md.strip().endswith(harvard_reference(_sample_rec())) or
                        md.rstrip().endswith(harvard_reference(_sample_rec())))
        # Sources line exact
        self.assertIn(SOURCES_LINE, md)
        self.assertTrue(md.startswith("# Evidence brief: KRAS G12C\n"))


class TestFailClosedAndEmpty(unittest.TestCase):
    def test_empty_hits(self):
        records = parse_search_body(_payload([]))
        self.assertEqual(records, [])
        md = render_evidence_md("no such question", records)
        self.assertIn(FINDINGS_ZERO, md)
        self.assertIn(REFERENCES_ZERO, md)
        self.assertNotIn("https://doi.org/", md)

    def test_unparseable_fails_closed(self):
        with self.assertRaises(EvidenceServiceError):
            parse_search_body(b"<!DOCTYPE html>")
        with self.assertRaises(EvidenceServiceError):
            parse_search_body(b'{"unexpected": true}')

    def test_http_error(self):
        err = HTTPError("https://example.test", 503, "down", hdrs=None, fp=BytesIO(b""))
        with patch("src.evidence_client.urlopen", side_effect=err):
            with self.assertRaises(EvidenceServiceError):
                search_peer_reviewed("KRAS G12C")

    def test_timeout(self):
        with patch("src.evidence_client.urlopen", side_effect=TimeoutError("slow")):
            with self.assertRaises(EvidenceServiceError):
                search_peer_reviewed("KRAS G12C")

    def test_urlerror(self):
        with patch("src.evidence_client.urlopen", side_effect=URLError("dns")):
            with self.assertRaises(EvidenceServiceError):
                search_peer_reviewed("KRAS G12C")

    def test_five_cap(self):
        rows = [
            _med_hit(
                title=f"Paper {i}",
                year="2024",
                date=f"2024-01-{i+1:02d}",
                doi=f"10.1000/paper.{i}",
            )
            for i in range(8)
        ]
        records = parse_search_body(_payload(rows))
        self.assertEqual(len(records), RESULT_CAP)
        self.assertEqual(RESULT_CAP, 5)


class TestQuestionValidation(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(question_error(""), MSG_MISSING_QUESTION)
        self.assertEqual(question_error("   "), MSG_MISSING_QUESTION)

    def test_overlong(self):
        q = "x" * (QUESTION_MAX_LEN + 1)
        self.assertEqual(question_error(q), MSG_QUESTION_TOO_LONG)
        self.assertIsNone(question_error("KRAS G12C inhibitors in NSCLC"))

    def test_captions(self):
        self.assertEqual(
            caption_for("KRAS", 2),
            CAPTION_HITS.format(question="KRAS", n=2),
        )
        self.assertEqual(
            caption_for("KRAS", 0),
            CAPTION_ZERO.format(question="KRAS"),
        )


class TestCmdEvidence(unittest.IsolatedAsyncioTestCase):
    def _update(self, args: list[str]):
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.reply_document = AsyncMock()
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.args = args
        context.user_data = {
            "context_card": {
                "patient": {"age_years": 55, "secret": True},
                "patient_files": [{"text": "private note"}],
            }
        }
        return update, context, message

    async def test_overlong_refuses_without_http(self):
        from src.bot import cmd_evidence

        update, context, message = self._update(["x" * (QUESTION_MAX_LEN + 1)])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch("src.bot.search_peer_reviewed") as search:
                await cmd_evidence(update, context)
        search.assert_not_called()
        message.reply_text.assert_awaited_once_with(MSG_QUESTION_TOO_LONG)

    async def test_missing_usage(self):
        from src.bot import cmd_evidence

        update, context, message = self._update([])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_evidence(update, context)
        message.reply_text.assert_awaited_once_with(MSG_MISSING_QUESTION)

    async def test_fail_closed_no_document(self):
        from src.bot import cmd_evidence

        update, context, message = self._update(["KRAS", "G12C"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.search_peer_reviewed",
                side_effect=EvidenceServiceError("down"),
            ):
                await cmd_evidence(update, context)
        message.reply_text.assert_awaited_once_with(MSG_FAIL_CLOSED)
        message.reply_document.assert_not_called()

    async def test_sends_markdown_document(self):
        from src.bot import cmd_evidence

        rec = _sample_rec()
        update, context, message = self._update(["KRAS", "G12C", "inhibitors", "in", "NSCLC"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch("src.bot.asyncio.to_thread", new=AsyncMock(return_value=[rec])):
                await cmd_evidence(update, context)
        message.reply_document.assert_awaited()
        kwargs = message.reply_document.await_args.kwargs
        self.assertEqual(kwargs["filename"], "evidence-brief.md")
        self.assertIn("peer-reviewed", kwargs["caption"])
        buf = kwargs["document"]
        self.assertIsInstance(buf, BytesIO)
        body = buf.getvalue().decode("utf-8")
        self.assertIn(SOURCES_LINE, body)
        self.assertIn("https://doi.org/", body)
        self.assertLess(body.find("## Findings"), body.find("## References"))

    async def test_privacy_guard_never_reads_patient_or_files(self):
        from src.bot import cmd_evidence

        update, context, message = self._update(["KRAS", "G12C"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.asyncio.to_thread", new=AsyncMock(return_value=[_sample_rec()])
            ) as to_thread:
                with patch("src.onboard.get_patient") as get_patient:
                    with patch("src.patient_files.get_patient_files") as get_files:
                        await cmd_evidence(update, context)
        # Question text only — never patient payloads
        to_thread.assert_awaited()
        args = to_thread.await_args.args
        # (fn, question)
        self.assertEqual(args[1], "KRAS G12C")
        self.assertNotIn("private note", args[1])
        self.assertNotIn("55", args[1])
        get_patient.assert_not_called()
        get_files.assert_not_called()
        body = message.reply_document.await_args.kwargs["document"].getvalue().decode()
        self.assertNotIn("private note", body)
        self.assertNotIn("age_years", body)

    async def test_help_lists_evidence(self):
        from src.bot import HELP_TEXT

        self.assertIn("/evidence", HELP_TEXT)
        self.assertIn("peer-reviewed", HELP_TEXT)
        self.assertIn("/research", HELP_TEXT)


class TestLiveSmokeOptional(unittest.TestCase):
    def test_live_europe_pmc_kras_g12c_not_preprint_servers(self):
        """Optional live GET. Assert servers are not bioRxiv/medRxiv when network works."""
        try:
            records = search_peer_reviewed("KRAS G12C inhibitors in NSCLC")
        except Exception as exc:  # noqa: BLE001
            print(f"LIVE_SMOKE_EVIDENCE skipped: {type(exc).__name__}: {exc}")
            return
        print(f"LIVE_SMOKE_EVIDENCE hit_count={len(records)}")
        for rec in records:
            print(
                f"LIVE_SMOKE_EVIDENCE year={rec.year} server={rec.server!r} "
                f"doi={rec.doi!r} title={rec.title[:70]!r}"
            )
            low = (rec.server or "").lower().replace(" ", "")
            self.assertNotIn("biorxiv", low)
            self.assertNotIn("medrxiv", low)
            self.assertTrue((rec.doi or "").strip())
            self.assertIn("https://doi.org/", harvard_reference(rec))
        self.assertLessEqual(len(records), 5)


if __name__ == "__main__":
    unittest.main()
