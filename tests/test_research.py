"""Unit tests for /research (Europe PMC). No live network required except optional smoke."""

from __future__ import annotations

import json
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError

from src.research_client import (
    RESULT_CAP,
    Author,
    Record,
    ResearchServiceError,
    build_query,
    parse_search_body,
    search_preprints,
)
from src.research_md import (
    CAPTION_HITS,
    CAPTION_ZERO,
    FINDINGS_ZERO,
    MSG_FAIL_CLOSED,
    MSG_MISSING_TOPIC,
    MSG_TOPIC_TOO_LONG,
    REFERENCES_ZERO,
    SOCIAL_SIGNAL_LINE,
    TOPIC_MAX_LEN,
    caption_for,
    harvard_reference,
    in_text_cite,
    render_research_md,
    topic_error,
)


def _author(family: str, initials: str) -> dict:
    return {
        "fullName": f"{family} {initials.replace('.', '')}",
        "lastName": family,
        "initials": initials.replace(".", ""),
    }


def _hit(
    *,
    title: str,
    year: str,
    date: str,
    doi: str,
    publisher: str = "bioRxiv",
    authors: list[dict] | None = None,
    abstract: str | None = None,
) -> dict:
    row = {
        "id": f"PPR{doi[-6:]}",
        "source": "PPR",
        "doi": doi,
        "title": title,
        "authorList": {"author": authors or [_author("Smith", "JA"), _author("Lee", "K")]},
        "pubYear": year,
        "firstPublicationDate": date,
        "bookOrReportDetails": {"publisher": publisher, "yearOfPublication": int(year) if year.isdigit() else year},
        "fullTextUrlList": {
            "fullTextUrl": [{"url": f"https://doi.org/{doi}", "documentStyle": "doi"}]
        },
    }
    if abstract:
        row["abstractText"] = abstract
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


class TestTopicValidation(unittest.TestCase):
    def test_missing_topic(self):
        self.assertEqual(topic_error(""), MSG_MISSING_TOPIC)
        self.assertEqual(topic_error("   "), MSG_MISSING_TOPIC)

    def test_overlong_topic(self):
        topic = "x" * (TOPIC_MAX_LEN + 1)
        self.assertEqual(topic_error(topic), MSG_TOPIC_TOO_LONG)
        self.assertEqual(topic_error("KRAS G12C"), None)


class TestParseAndCap(unittest.TestCase):
    def test_five_cap_and_recency(self):
        rows = []
        for i in range(8):
            rows.append(
                _hit(
                    title=f"Paper number {i} on KRAS",
                    year="2024",
                    date=f"2024-01-{i+1:02d}",
                    doi=f"10.1101/2024.01.{i+1:02d}.00000{i}",
                    authors=[_author("Smith", "JA")],
                )
            )
        records = parse_search_body(_payload(rows))
        self.assertEqual(len(records), RESULT_CAP)
        self.assertEqual(RESULT_CAP, 5)
        dates = [r.date for r in records]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(records[0].date, "2024-01-08")

    def test_empty_hits(self):
        records = parse_search_body(_payload([]))
        self.assertEqual(records, [])
        md = render_research_md("no such topic xyz", records)
        self.assertIn(FINDINGS_ZERO, md)
        self.assertIn(REFERENCES_ZERO, md)
        self.assertNotIn("10.1101", md)

    def test_empty_hitcount_zero_object(self):
        raw = json.dumps({"hitCount": 0, "resultList": {"result": []}}).encode()
        self.assertEqual(parse_search_body(raw), [])

    def test_filters_non_biorxiv(self):
        rows = [
            _hit(
                title="A Research Square preprint",
                year="2026",
                date="2026-06-11",
                doi="10.21203/rs.3.rs-1/v1",
                publisher="Research Square",
            ),
            _hit(
                title="A bioRxiv preprint on KRAS",
                year="2026",
                date="2026-06-23",
                doi="10.1101/2026.06.23.1",
                publisher="bioRxiv",
            ),
        ]
        records = parse_search_body(_payload(rows))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].server, "bioRxiv")

    def test_unparseable_fails_closed(self):
        with self.assertRaises(ResearchServiceError):
            parse_search_body(b"<!DOCTYPE html>")
        with self.assertRaises(ResearchServiceError):
            parse_search_body(b'{"unexpected": true}')


class TestHarvardAndMarkdown(unittest.TestCase):
    def _sample(self) -> Record:
        return Record(
            authors=(
                Author("Smith", "J.A"),
                Author("Lee", "K"),
                Author("Patel", "R"),
                Author("Zhang", "Q"),
            ),
            year="2024",
            title="A covalent inhibitor series for KRAS G12C",
            server="bioRxiv",
            doi="10.1101/2024.01.01.123456",
            url="https://doi.org/10.1101/2024.01.01.123456",
            date="2024-01-01",
            abstract="Covalent ligands occupy the GDP pocket of KRAS G12C in this preprint.",
        )

    def test_harvard_shape_et_al_after_three(self):
        ref = harvard_reference(self._sample())
        self.assertEqual(
            ref,
            "Smith, J.A., Lee, K., Patel, R., et al., 2024. "
            "A covalent inhibitor series for KRAS G12C. bioRxiv. "
            "https://doi.org/10.1101/2024.01.01.123456",
        )
        self.assertNotIn("Zhang", ref)

    def test_harvard_two_authors(self):
        rec = Record(
            authors=(Author("Smith", "J.A"), Author("Lee", "K")),
            year="2024",
            title="A covalent inhibitor series for KRAS G12C",
            server="bioRxiv",
            doi="10.1101/2024.01.01.123456",
            url="https://doi.org/10.1101/2024.01.01.123456",
            date="2024-01-01",
        )
        self.assertEqual(
            harvard_reference(rec),
            "Smith, J.A., Lee, K., 2024. "
            "A covalent inhibitor series for KRAS G12C. bioRxiv. "
            "https://doi.org/10.1101/2024.01.01.123456",
        )

    def test_x_omitted_line_exact(self):
        md = render_research_md("KRAS G12C", [self._sample()])
        self.assertIn(SOCIAL_SIGNAL_LINE, md)
        self.assertNotIn("highest signal", md.lower())
        self.assertIn("## Social signal", md)
        # exactly one social line
        self.assertEqual(md.count(SOCIAL_SIGNAL_LINE), 1)

    def test_document_locked_strings(self):
        md = render_research_md("KRAS G12C", [self._sample()])
        self.assertTrue(md.startswith("# Research brief: KRAS G12C\n"))
        self.assertIn(
            "This brief summarises up to five recent bioRxiv or medRxiv preprints "
            "retrieved for the topic above. It is for research use only and is not clinical advice.",
            md,
        )
        self.assertIn("(Smith et al., 2024)", md)
        self.assertEqual(in_text_cite(self._sample()), "(Smith et al., 2024)")

    def test_zero_hits_locked_strings(self):
        md = render_research_md("obscure topic", [])
        self.assertIn(FINDINGS_ZERO, md)
        self.assertIn(f"## References\n\n{REFERENCES_ZERO}", md)
        self.assertEqual(
            caption_for("obscure topic", 0),
            CAPTION_ZERO.format(topic="obscure topic"),
        )
        self.assertEqual(
            caption_for("obscure topic", 0),
            "Research brief for “obscure topic”: no matching preprints found. "
            "Research use only; not clinical advice.",
        )

    def test_caption_with_hits(self):
        self.assertEqual(
            caption_for("KRAS G12C", 3),
            "Research brief for “KRAS G12C”: 3 recent preprint(s). "
            "Research use only; not clinical advice.",
        )
        self.assertEqual(caption_for("KRAS G12C", 3), CAPTION_HITS.format(topic="KRAS G12C", n=3))


class TestHttpFailClosed(unittest.TestCase):
    def test_http_error(self):
        err = HTTPError("https://example.test", 503, "down", hdrs=None, fp=BytesIO(b""))
        with patch("src.research_client.urlopen", side_effect=err):
            with self.assertRaises(ResearchServiceError):
                search_preprints("KRAS G12C")

    def test_timeout(self):
        with patch("src.research_client.urlopen", side_effect=TimeoutError("slow")):
            with self.assertRaises(ResearchServiceError):
                search_preprints("KRAS G12C")

    def test_urlerror(self):
        with patch("src.research_client.urlopen", side_effect=URLError("dns")):
            with self.assertRaises(ResearchServiceError):
                search_preprints("KRAS G12C")

    def test_unparseable_http_body(self):
        with patch("src.research_client.urlopen", return_value=FakeHTTP(b"not-json")):
            with self.assertRaises(ResearchServiceError):
                search_preprints("KRAS G12C")

    def test_empty_hits_via_http(self):
        with patch(
            "src.research_client.urlopen",
            return_value=FakeHTTP(_payload([])),
        ):
            records = search_preprints("no hits expected")
        self.assertEqual(records, [])

    def test_query_uses_europe_pmc_filter(self):
        q = build_query("KRAS G12C")
        self.assertIn("SRC:PPR", q)
        self.assertIn('PUBLISHER:"bioRxiv"', q)
        self.assertIn('PUBLISHER:"medRxiv"', q)
        self.assertIn("KRAS G12C", q)


class TestCmdResearch(unittest.IsolatedAsyncioTestCase):
    def _update(self, args: list[str]):
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.reply_document = AsyncMock()
        update = MagicMock()
        update.effective_message = message
        context = MagicMock()
        context.args = args
        return update, context, message

    async def test_overlong_topic_refuses_without_http(self):
        from src.bot import cmd_research

        update, context, message = self._update(["x" * (TOPIC_MAX_LEN + 1)])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch("src.bot.search_preprints") as search:
                await cmd_research(update, context)
        search.assert_not_called()
        message.reply_text.assert_awaited_once_with(MSG_TOPIC_TOO_LONG)
        message.reply_document.assert_not_called()

    async def test_missing_topic_usage(self):
        from src.bot import cmd_research

        update, context, message = self._update([])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            await cmd_research(update, context)
        message.reply_text.assert_awaited_once_with(MSG_MISSING_TOPIC)
        message.reply_document.assert_not_called()

    async def test_http_error_fail_closed_no_document(self):
        from src.bot import cmd_research

        update, context, message = self._update(["KRAS", "G12C"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch(
                "src.bot.search_preprints",
                side_effect=ResearchServiceError("down"),
            ):
                await cmd_research(update, context)
        message.reply_text.assert_awaited_once_with(MSG_FAIL_CLOSED)
        message.reply_document.assert_not_called()

    async def test_sends_markdown_document(self):
        from src.bot import cmd_research

        rec = Record(
            authors=(Author("Smith", "J.A"),),
            year="2024",
            title="A covalent inhibitor series for KRAS G12C",
            server="bioRxiv",
            doi="10.1101/2024.01.01.123456",
            url="https://doi.org/10.1101/2024.01.01.123456",
            date="2024-01-01",
        )
        update, context, message = self._update(["KRAS", "G12C"])
        with patch("src.bot._authorized", new=AsyncMock(return_value=True)):
            with patch("src.bot.search_preprints", return_value=[rec]):
                with patch("src.bot.asyncio.to_thread", new=AsyncMock(return_value=[rec])):
                    await cmd_research(update, context)
        message.reply_document.assert_awaited()
        kwargs = message.reply_document.await_args.kwargs
        self.assertEqual(kwargs["filename"], "research-brief.md")
        self.assertEqual(
            kwargs["caption"],
            "Research brief for “KRAS G12C”: 1 recent preprint(s). "
            "Research use only; not clinical advice.",
        )
        self.assertIsInstance(kwargs["document"], BytesIO)
        message.reply_text.assert_not_called()

    async def test_help_lists_research(self):
        from src.bot import HELP_TEXT

        self.assertIn("/research", HELP_TEXT)
        self.assertIn("bioRxiv or medRxiv", HELP_TEXT)



class TestFindingVoice(unittest.TestCase):
    def test_no_title_restatement_or_summary_prefix(self):
        rec = Record(
            authors=(Author(family="Parker", initials="K"),),
            year="2026",
            title="Dual inhibition of GTP-bound (ON) and GDP-bound (OFF) KRAS G12C suppresses PI3Kα",
            server="bioRxiv",
            doi="10.64898/example",
            url=None,
            date="2026-04-27",
            abstract=(
                "Summary Current approved KRAS G12C inhibitors covalently bind the inactive "
                "GDP-bound (OFF) form of KRAS G12C."
            ),
        )
        md = render_research_md("KRAS G12C covalent inhibitors", [rec])
        self.assertNotIn("This preprint is about", md)
        self.assertNotIn("Summary Current", md)
        self.assertIn("Current approved KRAS G12C inhibitors", md)
        self.assertIn("(Parker, 2026)", md)


class TestLiveSmokeOptional(unittest.TestCase):
    def test_live_europe_pmc_kras_g12c(self):
        """One real GET if the network works. Never fail the suite when it does not."""
        try:
            records = search_preprints("KRAS G12C")
        except Exception as exc:  # noqa: BLE001
            print(f"LIVE_SMOKE skipped: {type(exc).__name__}: {exc}")
            return
        print(f"LIVE_SMOKE topic='KRAS G12C' hit_count={len(records)}")
        for rec in records:
            print(f"LIVE_SMOKE rec year={rec.year} server={rec.server} title={rec.title[:80]!r}")
        self.assertLessEqual(len(records), 5)


if __name__ == "__main__":
    unittest.main()
