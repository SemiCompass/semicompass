import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import bundle_fakes as bf
import make_bundle as mb
from bundle_fakes import KEY, R2_ACCESS, R2_ACCOUNT, R2_ENV, R2_SECRET, Clock, FakeR2

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
SECRETS = (KEY, R2_ACCOUNT, R2_ACCESS, R2_SECRET)
SECTION_ARGS = ["--sections", bf.ELEM_A, bf.ELEM_B]
# 本文の特定の語と、取り込みの処理が出してはいけないもの
BODY_FRAGMENTS = (bf.WORD_A, bf.WORD_B, "項目一", "見出し", "記号")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.auto = Path(self.tmp.name) / "auto"
        self.auto.mkdir()
        bf.write_auto(self.auto)
        self.config = Path(self.tmp.name) / "sections.yaml"
        self.config.write_text("sections: []\n", encoding="utf-8")

    def run_main(self, argv, *, server=None, r2=None, env=None, r2_factory=None):
        server = server or bf.DocServer()
        clock = Clock()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mb.main(argv, env=R2_ENV if env is None else env, open_url=server, sleep=clock.sleep,
                           monotonic=clock.monotonic, now=NOW, r2_factory=r2_factory or (lambda creds: r2),
                           auto_dir=self.auto, sections_config=self.config)
        self.server = server
        return code, out.getvalue(), err.getvalue()


class SelectFilingTest(unittest.TestCase):
    def test_latest_ingested_annual_report(self):
        filings = [
            bf.filing("S100AAA1", period="2024-03", submitted="2024-06-20T00:00:00+09:00"),
            bf.filing("S100AAA3", period="2026-03", submitted="2026-06-20T00:00:00+09:00"),
            bf.filing("S100AAA2", period="2025-03", submitted="2025-06-20T00:00:00+09:00"),
            bf.filing("S100AAA4", doc_type="semiannual_report", period="2026-03", submitted="2026-12-01T00:00:00+09:00"),
        ]
        self.assertEqual(mb.latest_annual_report(filings)["doc_id"], "S100AAA3")

    def test_ignores_non_ingested_and_amended(self):
        filings = [
            bf.filing("S100AAA1", period="2025-03"),
            bf.filing("S100AAA2", period="2025-03", status="failed", submitted="2025-07-01T00:00:00+09:00"),
        ]
        self.assertEqual(mb.latest_annual_report(filings)["doc_id"], "S100AAA1")

    def test_same_period_picks_later_submission(self):
        filings = [bf.filing("S100AAA1", submitted="2026-06-20T00:00:00+09:00"),
                   bf.filing("S100AAA2", submitted="2026-06-21T00:00:00+09:00")]
        self.assertEqual(mb.latest_annual_report(filings)["doc_id"], "S100AAA2")

    def test_stops_when_newer_period_exists_only_as_non_annual_report(self):
        filings = [bf.filing("S100AAA1", period="2025-03"),
                   bf.filing("S100AAA2", period="2026-03", status="superseded"),
                   bf.filing("S100AAA3", doc_type="amended_annual_report", period="2026-03")]
        with self.assertRaises(mb.BundleError) as raised:
            mb.latest_annual_report(filings)
        self.assertIn("S100AAA3", str(raised.exception))

    def test_no_candidate(self):
        with self.assertRaises(mb.BundleError):
            mb.latest_annual_report([bf.filing("S100AAA1", status="failed")])


class MakeBundleTest(Base):
    def test_writes_expected_key_and_json(self):
        r2 = FakeR2()
        code, out, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(r2.puts), 1)
        put = r2.puts[0]
        self.assertEqual(put["Bucket"], "semicompass-bundles")
        self.assertEqual(put["Key"], f"bundles/testco-{bf.DOC_ID}.json")
        data = json.loads(put["Body"].decode("utf-8"))
        self.assertEqual(data["bundle_id"], f"testco-{bf.DOC_ID}")
        self.assertEqual(data["document"], {
            "doc_id": bf.DOC_ID, "doc_type": "annual_report", "submitted_at": "2026-06-20T13:00:00+09:00",
            "fiscal_period_end": "2026-03", "edinet_code": bf.EDINET_CODE})
        self.assertEqual(data["extracted_at"], "2026-10-06T12:00:00+09:00")
        self.assertEqual([s["element_id"] for s in data["sections"]], [bf.ELEM_A, bf.ELEM_B])
        first = data["sections"][0]
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(first["key"], bf.ELEM_A)  # --sections では、key は要素IDのまま
        self.assertEqual(first["label"], "節A（合成）")
        self.assertEqual(first["chars"], len(first["text"]))
        self.assertIn(bf.WORD_A, first["text"])
        self.assertIn("項目一\n項目二", first["text"])
        self.assertIn("& 記号 <と>", data["sections"][1]["text"])

    def test_requested_order_is_kept(self):
        r2 = FakeR2()
        self.run_main(["--company", "testco", "--sections", bf.ELEM_B, bf.ELEM_A], r2=r2)
        data = json.loads(r2.puts[0]["Body"])
        self.assertEqual([s["element_id"] for s in data["sections"]], [bf.ELEM_B, bf.ELEM_A])

    def test_comma_separated_sections_and_defaults_from_config(self):
        r2 = FakeR2()
        self.run_main(["--company", "testco", "--sections", f"{bf.ELEM_A},{bf.ELEM_B}"], r2=r2)
        self.assertEqual(len(json.loads(r2.puts[0]["Body"])["sections"]), 2)
        self.config.write_text(f"sections:\n  - key: alpha\n    candidates:\n      - {bf.ELEM_A}\n", encoding="utf-8")
        r2 = FakeR2()
        self.assertEqual(self.run_main(["--company", "testco"], r2=r2)[0], 0)
        self.assertEqual(len(json.loads(r2.puts[0]["Body"])["sections"]), 1)

    def test_empty_default_without_sections_is_usage_error(self):
        r2 = FakeR2()
        code, _, err = self.run_main(["--company", "testco"], r2=r2)
        self.assertEqual(code, 2)
        self.assertEqual(r2.puts, [])
        self.assertEqual(self.server.requests, [])

    def test_shipped_default_config(self):
        specs = mb.load_default_sections()
        self.assertEqual([s.key for s in specs], ["business_description", "affiliated_entities", "segment_information"])
        self.assertEqual(specs[2].candidates, (
            "jpcrp_cor:NotesSegmentInformationEtcConsolidatedFinancialStatementsTextBlock",
            "jpigp_cor:NotesSegmentInformationConsolidatedFinancialStatementsIFRSTextBlock"))

    def test_missing_section_writes_nothing(self):
        r2 = FakeR2()
        code, _, err = self.run_main(["--company", "testco", "--sections", bf.ELEM_A, "test_cor:NoneTextBlock"], r2=r2)
        self.assertEqual(code, 1)
        self.assertIn("test_cor:NoneTextBlock", err)  # --sections の key は要素IDのまま
        self.assertEqual(r2.puts, [])

    def test_invalid_element_id(self):
        code, _, _ = self.run_main(["--company", "testco", "--sections", "jppfs_cor:NetSales"], r2=FakeR2())
        self.assertEqual(code, 2)

    def test_dry_run_writes_nothing_and_needs_no_r2_env(self):
        r2 = FakeR2()
        env = {"EDINET_API_KEY": KEY}
        code, out, err = self.run_main(["--company", "testco", *SECTION_ARGS, "--dry-run"], r2=r2, env=env,
                                       r2_factory=mock.Mock(side_effect=AssertionError("R2を作らない")))
        self.assertEqual(code, 0, err)
        self.assertEqual(r2.puts, [])
        self.assertIn(bf.ELEM_A, out)
        self.assertIn("文字", out)
        self.assertIn("dry-run", out)

    def test_same_input_same_result_and_same_key(self):
        r2 = FakeR2()
        self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)
        self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)
        self.assertEqual(len(r2.puts), 2)
        self.assertEqual(r2.puts[0]["Key"], r2.puts[1]["Key"])
        self.assertEqual(r2.puts[0]["Body"], r2.puts[1]["Body"])

    def test_doc_id_alone_finds_company(self):
        r2 = FakeR2()
        code, _, err = self.run_main(["--doc-id", bf.DOC_ID, *SECTION_ARGS], r2=r2)
        self.assertEqual(code, 0, err)
        self.assertEqual(r2.puts[0]["Key"], f"bundles/testco-{bf.DOC_ID}.json")

    def test_doc_id_not_in_auto_is_usage_error(self):
        code, _, _ = self.run_main(["--doc-id", "S100ZZZZ", *SECTION_ARGS], r2=FakeR2())
        self.assertEqual(code, 2)
        self.assertEqual(self.server.requests, [])

    def test_company_with_explicit_doc_id(self):
        bf.write_auto(self.auto, filings=[bf.filing(bf.DOC_ID), bf.filing("S100OLD1", period="2025-03")])
        r2 = FakeR2()
        self.run_main(["--company", "testco", "--doc-id", "S100OLD1", *SECTION_ARGS], r2=r2)
        self.assertEqual(self.server.requests[0][0].rsplit("/", 1)[1], "S100OLD1")

    def test_requires_company_or_doc_id(self):
        self.assertEqual(self.run_main(SECTION_ARGS, r2=FakeR2())[0], 2)

    def test_company_picks_latest_annual_report_and_requests_type5(self):
        bf.write_auto(self.auto, filings=[bf.filing("S100OLD1", period="2025-03"), bf.filing(bf.DOC_ID)])
        self.run_main(["--company", "testco", *SECTION_ARGS], r2=FakeR2())
        path, query = self.server.requests[0]
        self.assertTrue(path.endswith(bf.DOC_ID))
        self.assertEqual(query["type"], ["5"])

    def test_edinet_code_mismatch_writes_nothing(self):
        bf.write_auto(self.auto, edinet_code="E00001")
        r2 = FakeR2()
        code, _, _ = self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)
        self.assertEqual(code, 1)
        self.assertEqual(r2.puts, [])

    def test_summary_file_has_no_body(self):
        summary = Path(self.tmp.name) / "summary.md"
        r2 = FakeR2()
        self.run_main(["--company", "testco", *SECTION_ARGS, "--summary", str(summary)], r2=r2)
        text = summary.read_text(encoding="utf-8")
        self.assertIn(bf.ELEM_A, text)
        self.assertIn("bundles/testco-" + bf.DOC_ID + ".json", text)
        self.assertIn("semicompass-bundles", text)
        for fragment in BODY_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_stdout_and_stderr_have_no_body_or_credentials(self):
        r2 = FakeR2()
        _, out, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)
        self.assertIn("semicompass-bundles", out)
        self.assertIn(f"bundles/testco-{bf.DOC_ID}.json", out)
        for fragment in (*BODY_FRAGMENTS, *SECRETS):
            self.assertNotIn(fragment, out + err)

    def test_missing_r2_env_is_usage_error_before_any_request(self):
        env = {k: v for k, v in R2_ENV.items() if k != "R2_SECRET_ACCESS_KEY"}
        code, _, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=FakeR2(), env=env)
        self.assertEqual(code, 2)
        self.assertIn("R2_SECRET_ACCESS_KEY", err)
        self.assertEqual(self.server.requests, [])

    def test_r2_error_hides_credentials_and_body(self):
        leaking = RuntimeError(f"failed {R2_SECRET} {R2_ACCESS} {R2_ACCOUNT} {bf.WORD_A} {KEY}")
        code, out, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=FakeR2(error=leaking))
        self.assertEqual(code, 1)
        self.assertIn("RuntimeError", err)
        for fragment in (*BODY_FRAGMENTS, *SECRETS):
            self.assertNotIn(fragment, out + err)

    def test_client_error_shows_only_code(self):
        class ClientError(Exception):
            response = {"Error": {"Code": "AccessDenied", "Message": f"{R2_ACCESS} {bf.WORD_A}"}}
        _, out, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=FakeR2(error=ClientError(R2_SECRET)))
        self.assertIn("AccessDenied", err)
        for fragment in (*BODY_FRAGMENTS, *SECRETS):
            self.assertNotIn(fragment, out + err)

    def test_own_error_messages_mask_credentials(self):
        text = mb.describe_error(mb.BundleError(f"x {R2_SECRET} y {R2_ACCOUNT}"), list(SECRETS))
        self.assertNotIn(R2_SECRET, text)
        self.assertNotIn(R2_ACCOUNT, text)
        self.assertIn("***", text)

    def test_unexpected_error_in_parsing_hides_message(self):
        with mock.patch.object(mb, "text_rows_from_zip", side_effect=KeyError(bf.WORD_A)):
            code, out, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=FakeR2())
        self.assertEqual(code, 1)
        self.assertIn("KeyError", err)
        self.assertNotIn(bf.WORD_A, out + err)

    def test_non_200_put_response_is_failure(self):
        r2 = FakeR2(response={"ResponseMetadata": {"HTTPStatusCode": 500}})
        self.assertEqual(self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)[0], 1)

    def test_edinet_failure_hides_key(self):
        code, out, err = self.run_main(["--company", "testco", *SECTION_ARGS], r2=FakeR2(),
                                       server=bf.DocServer(b"<html>x</html>"))
        self.assertEqual(code, 1)
        self.assertNotIn(KEY, out + err)


class ConfigSectionsTest(Base):
    # 日本基準と IFRS で、セグメント情報の要素IDが違う場合の、候補の優先順
    JP = "test_cor:SegmentJpTextBlock"
    IFRS = "test_ifrs:SegmentIfrsTextBlock"

    def write_config(self, text=None):
        self.config.write_text(text or f"""sections:
  - key: alpha_section
    candidates:
      - {bf.ELEM_A}
  - key: segment_information
    candidates:
      - {self.JP}
      - {self.IFRS}
""", encoding="utf-8")

    def zip_with(self, *elements):
        rows = [bf.BASE_ROWS[0], bf.BASE_ROWS[2]] + [bf.row(e, "セグメント（合成）", "CurrentYearDuration", f"<p>{bf.WORD_B}{e}</p>") for e in elements]
        return bf.DocServer(bf.make_zip(rows))

    def bundle(self, server):
        self.write_config()
        r2 = FakeR2()
        code, out, err = self.run_main(["--company", "testco"], r2=r2, server=server)
        return code, out, err, r2

    def test_first_candidate_is_used_for_japanese_standard(self):
        code, out, err, r2 = self.bundle(self.zip_with(self.JP))
        self.assertEqual(code, 0, err)
        data = json.loads(r2.puts[0]["Body"])
        self.assertEqual([(s["key"], s["element_id"]) for s in data["sections"]],
                         [("alpha_section", bf.ELEM_A), ("segment_information", self.JP)])
        self.assertIn("segment_information  " + self.JP, out)

    def test_second_candidate_is_used_for_ifrs(self):
        code, out, err, r2 = self.bundle(self.zip_with(self.IFRS))
        self.assertEqual(code, 0, err)
        data = json.loads(r2.puts[0]["Body"])
        self.assertEqual([(s["key"], s["element_id"]) for s in data["sections"]],
                         [("alpha_section", bf.ELEM_A), ("segment_information", self.IFRS)])
        self.assertIn("segment_information  " + self.IFRS, out)

    def test_first_found_candidate_wins_when_both_exist(self):
        _, _, _, r2 = self.bundle(self.zip_with(self.IFRS, self.JP))
        ids = [s["element_id"] for s in json.loads(r2.puts[0]["Body"])["sections"]]
        self.assertEqual(ids, [bf.ELEM_A, self.JP])

    def test_all_rows_of_the_chosen_element_are_kept_in_csv_order(self):
        rows = [bf.BASE_ROWS[0], bf.BASE_ROWS[2],
                bf.row(self.IFRS, "セグメント（合成）", "CtxTwo", "<p>二</p>"),
                bf.row(self.IFRS, "セグメント（合成）", "CtxOne", "<p>一</p>")]
        _, _, _, r2 = self.bundle(bf.DocServer(bf.make_zip(rows)))
        picked = [(s["element_id"], s["context_id"]) for s in json.loads(r2.puts[0]["Body"])["sections"]]
        self.assertEqual(picked[1:], [(self.IFRS, "CtxTwo"), (self.IFRS, "CtxOne")])

    def test_section_without_any_candidate_stops_and_saves_nothing(self):
        code, out, err, r2 = self.bundle(self.zip_with())
        self.assertEqual(code, 1)
        self.assertEqual(r2.puts, [])
        self.assertIn("segment_information", err)
        self.assertNotIn("alpha_section", err)
        for fragment in BODY_FRAGMENTS:
            self.assertNotIn(fragment, out + err)

    def test_dry_run_shows_key_and_used_element_id_without_body(self):
        self.write_config()
        r2 = FakeR2()
        code, out, err = self.run_main(["--company", "testco", "--dry-run"], r2=r2, server=self.zip_with(self.IFRS))
        self.assertEqual(code, 0, err)
        self.assertEqual(r2.puts, [])
        self.assertIn("segment_information  " + self.IFRS, out)
        self.assertNotIn(self.JP, out)
        for fragment in BODY_FRAGMENTS:
            self.assertNotIn(fragment, out + err)

    def test_summary_shows_key_and_used_element_id_without_body(self):
        self.write_config()
        summary = Path(self.tmp.name) / "summary.md"
        self.run_main(["--company", "testco", "--summary", str(summary)], r2=FakeR2(), server=self.zip_with(self.IFRS))
        text = summary.read_text(encoding="utf-8")
        self.assertIn(f"| segment_information | {self.IFRS} |", text)
        self.assertNotIn(self.JP, text)
        for fragment in BODY_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_bad_config_is_usage_error_and_makes_no_request(self):
        cand = f"candidates:\n      - {bf.ELEM_A}"
        bad = {
            "duplicate key": f"sections:\n  - key: a\n    {cand}\n  - key: a\n    {cand}\n",
            "upper case": f"sections:\n  - key: Alpha\n    {cand}\n",
            "digit": f"sections:\n  - key: a1\n    {cand}\n",
            "hyphen": f"sections:\n  - key: a-b\n    {cand}\n",
            "no candidates": "sections:\n  - key: a\n    candidates: []\n",
            "missing candidates": "sections:\n  - key: a\n",
            "bad element id": "sections:\n  - key: a\n    candidates:\n      - jppfs_cor:NetSales\n",
            "duplicate candidate": f"sections:\n  - key: a\n    candidates:\n      - {bf.ELEM_A}\n      - {bf.ELEM_A}\n",
            "extra field": f"sections:\n  - key: a\n    {cand}\n    note: x\n",
            "old flat list": f"sections:\n  - {bf.ELEM_A}\n",
            "not a list": "sections: {}\n",
            "broken yaml": "sections: [\n",
        }
        for name, text in bad.items():
            with self.subTest(name):
                self.config.write_text(text, encoding="utf-8")
                r2 = FakeR2()
                code, _, err = self.run_main(["--company", "testco"], r2=r2)
                self.assertEqual(code, 2, err)
                self.assertEqual((r2.puts, self.server.requests), ([], []))

    def test_sections_argument_overrides_config_even_if_config_is_bad(self):
        self.config.write_text("sections: [\n", encoding="utf-8")
        r2 = FakeR2()
        self.assertEqual(self.run_main(["--company", "testco", *SECTION_ARGS], r2=r2)[0], 0)


class R2ClientTest(unittest.TestCase):
    def test_endpoint_region_and_credentials(self):
        creds = {"R2_ACCOUNT_ID": R2_ACCOUNT, "R2_ACCESS_KEY_ID": R2_ACCESS, "R2_SECRET_ACCESS_KEY": R2_SECRET,
                 "R2_BUCKET": "semicompass-bundles"}
        try:
            import boto3  # noqa: F401
        except ImportError:
            self.skipTest("boto3 が入っていない")
        client = mb.make_r2_client(creds)
        self.assertEqual(client.meta.endpoint_url, f"https://{R2_ACCOUNT}.r2.cloudflarestorage.com")
        self.assertEqual(client.meta.region_name, "auto")

    def test_env_format_checks_do_not_echo_values(self):
        bad = dict(R2_ENV, R2_ACCOUNT_ID="not-hex-" + R2_SECRET)
        with self.assertRaises(mb.BundleError) as raised:
            mb.read_r2_env(bad)
        self.assertNotIn(R2_SECRET, str(raised.exception))
        with self.assertRaises(mb.BundleError):
            mb.read_r2_env(dict(R2_ENV, R2_BUCKET="Bad_Bucket"))


if __name__ == "__main__":
    unittest.main()
