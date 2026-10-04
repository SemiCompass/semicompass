import codecs
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

import edinet_fakes as fk
from edinet_fakes import KEY, Clock, FakeResponse, http_error

insp = __import__("inspect_document")
from test_client_document import DocServer  # noqa: E402

HEADER = ["要素ID", "項目名", "コンテキストID", "相対年度", "連結・個別", "期間・時点", "ユニットID", "単位", "値"]
CUR = "CurrentYearDuration"
SEG = "CurrentYearDuration_jpcrp030000-asr_E01950-000SemiconductorMember"
REG = "CurrentYearDuration_jpcrp030000-asr_E01950-000JapanMember"
CSV_NAME = "XBRL_TO_CSV/jpcrp030000-asr-001_E01950-000_2026-03-31_01_2026-06-20.csv"


def r(element, label, context, value, cons="連結", unit="円"):
    return [element, label, context, "当期", cons, "期間", "JPY", unit, value]


BASE_ROWS = [
    r("jppfs_cor:NetSales", "売上高", CUR, "1234567000"),
    r("jppfs_cor:OperatingIncome", "営業利益", CUR, "-5000000"),
    r("jppfs_cor:OrdinaryIncome", "経常利益", CUR + "_NonConsolidatedMember", "1,000", cons="個別"),
    r("jppfs_cor:ProfitLossAttributableToOwnersOfParent", "親会社株主に帰属する当期純利益", CUR, "12.5"),
    r("jpcrp_cor:NetSalesToExternalCustomers", "外部顧客への売上高", SEG, "800000000"),
    r("jpcrp_cor:NetSalesToExternalCustomers", "外部顧客への売上高", REG, "300000000"),
    r("jpcrp_cor:NumberOfEmployees", "従業員数", "CurrentYearInstant", "1234", unit="人"),
    r("jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees", "平均年齢（歳）", "CurrentYearInstant_NonConsolidatedMember", "41.5", unit="年"),
    r("jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees", "平均勤続年数（年）", "CurrentYearInstant_NonConsolidatedMember", "15.3", unit="年"),
    r("jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees", "平均年間給与", "CurrentYearInstant_NonConsolidatedMember", "7500000"),
    # 数値でない行（除く）
    r("jpcrp_cor:DescriptionOfBusinessTextBlock", "事業の内容", CUR, "<p>文章の行</p>", unit=""),
    r("jpcrp_cor:SomeComment", "コメント", CUR, "あいう"),
    r("jpcrp_cor:NetSalesTextBlock", "売上の説明", CUR, "12345", unit=""),  # TextBlock は、値が数字でも除く
    r("jpdei_cor:CurrentFiscalYearStartDateDEI", "当事業年度開始日", CUR, "2025-04-01", unit=""),
]


def csv_text(rows=BASE_ROWS, header=HEADER, delimiter="\t"):
    def line(cells):
        return delimiter.join('"' + c.replace('"', '""') + '"' for c in cells)
    return "\r\n".join(line(c) for c in [header, *rows]) + "\r\n"


ENCODERS = {
    "UTF-16LE（BOMあり）": lambda t: codecs.BOM_UTF16_LE + t.encode("utf-16-le"),
    "UTF-16BE（BOMあり）": lambda t: codecs.BOM_UTF16_BE + t.encode("utf-16-be"),
    "UTF-16LE（BOMなし）": lambda t: t.encode("utf-16-le"),
    "UTF-16BE（BOMなし）": lambda t: t.encode("utf-16-be"),
    "UTF-8（BOM付き、またはBOMなし）": lambda t: t.encode("utf-8-sig"),
    "CP932": lambda t: t.encode("cp932"),
}


def make_zip(csv_bytes, name=CSV_NAME, extra=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, csv_bytes)
        archive.writestr("XBRL_TO_CSV/note.txt", "メモ")
        for extra_name, data in extra:
            archive.writestr(extra_name, data)
    return buffer.getvalue()


def zip_response(csv_text_value=None, encoder="UTF-16LE（BOMあり）", **kwargs):
    return FakeResponse(make_zip(ENCODERS[encoder](csv_text_value or csv_text()), **kwargs))


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)

    def run_main(self, argv, server, *, env=None, clock=None):
        clock = clock or Clock()
        out, err = io.StringIO(), io.StringIO()
        environ = {insp.ENV_KEY: KEY} if env is None else env
        with mock.patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = insp.main(argv, open_url=server, sleep=clock.sleep, monotonic=clock.monotonic)
        return code, out.getvalue(), err.getvalue(), clock


class DecodeTest(unittest.TestCase):
    def test_three_encodings_are_detected_and_japanese_is_intact(self):
        text = csv_text()
        for name, encode in ENCODERS.items():
            decoded, detected = insp.decode_csv(encode(text))
            self.assertEqual(decoded, text, msg=name)
            self.assertEqual(detected, name)

    def test_utf8_without_bom_and_cp932_are_not_mistaken_for_utf16(self):
        text = csv_text()
        for raw in (text.encode("utf-8"), text.encode("cp932")):
            self.assertEqual(len(raw) % 2, len(raw) % 2)
            decoded, detected = insp.decode_csv(raw)
            self.assertEqual(decoded, text)
            self.assertNotIn("UTF-16", detected)

    def test_undecodable_bytes_fail(self):
        with self.assertRaises(ValueError):
            insp.decode_csv(b"\xff\xfe\xfd\x81\x00\x80binary")
        with self.assertRaises(ValueError):
            insp.decode_csv(b"")
        with self.assertRaises(ValueError):
            insp.decode_csv("区切りのない一行".encode("utf-8"))


class ParseTest(unittest.TestCase):
    def test_header_row_is_used_for_column_names(self):
        header, rows = insp.parse_csv(csv_text())
        self.assertEqual(header, HEADER)
        self.assertEqual(len(rows), len(BASE_ROWS))

    def test_comma_delimited_csv_is_read_too(self):
        header, rows = insp.parse_csv(csv_text(delimiter=","))
        self.assertEqual(header, HEADER)
        self.assertEqual(rows[0][0], "jppfs_cor:NetSales")

    def test_quoted_field_with_newline_and_quotes(self):
        text = csv_text([r("jpcrp_cor:DescriptionOfBusinessTextBlock", "事業", CUR, '1行目\n"2行目"'),
                         r("jppfs_cor:NetSales", "売上高", CUR, "10")])
        header, rows = insp.parse_csv(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][-1], '1行目\n"2行目"')

    def test_numeric_rows_only(self):
        header, rows = insp.parse_csv(csv_text())
        numeric, positions = insp.extract_numeric_rows(header, rows)
        values = [row["値"] for row in numeric]
        self.assertEqual(values, ["1234567000", "-5000000", "1,000", "12.5", "800000000", "300000000",
                                  "1234", "41.5", "15.3", "7500000"])
        elements = {row["要素ID"] for row in numeric}
        self.assertNotIn("jpcrp_cor:DescriptionOfBusinessTextBlock", elements)   # 文章の行
        self.assertNotIn("jpcrp_cor:SomeComment", elements)                      # 数値でない行
        self.assertNotIn("jpcrp_cor:NetSalesTextBlock", elements)                # TextBlock（値が数字でも）
        self.assertNotIn("jpdei_cor:CurrentFiscalYearStartDateDEI", elements)    # 日付
        self.assertEqual(list(numeric[0]), HEADER)  # 列名のまま
        self.assertEqual(positions["value"], 8)

    def test_is_numeric(self):
        for ok in ("1", "-1", "+1.5", "1,234,567", ".5", "0", " 12 "):
            self.assertTrue(insp.is_numeric(ok), ok)
        for bad in ("", "abc", "1-2", "2025-04-01", "1e5", "－", "1.2.3", "NaN"):
            self.assertFalse(insp.is_numeric(bad), bad)

    def test_unexpected_header_reports_actual_columns(self):
        header, rows = insp.parse_csv(csv_text(header=["A", "B", "C"], rows=[["1", "2", "3"]]))
        with self.assertRaises(ValueError) as raised:
            insp.extract_numeric_rows(header, rows)
        self.assertIn("実際の列名: A, B, C", str(raised.exception))

    def test_header_with_bom_char_and_spaces_and_duplicates(self):
        header = ["﻿要素ID", "項目名", "コンテキストID", "連結・個別", "単位", " 値 ", "値"]
        positions = insp.map_columns(header)
        self.assertEqual((positions["element"], positions["value"]), (0, 5))
        self.assertEqual(insp.unique_headers(header)[-2:], [" 値 ", "値"])
        self.assertEqual(insp.unique_headers(["値", "値"]), ["値", "値_2"])

    def test_short_rows_are_padded(self):
        numeric, _ = insp.extract_numeric_rows(HEADER, [["jppfs_cor:NetSales", "売上高", CUR, "当期", "連結", "期間", "JPY", "円", "5"],
                                                         ["jppfs_cor:X", "x"]])
        self.assertEqual(len(numeric), 1)


class CandidatesTest(unittest.TestCase):
    def candidates(self, rows=BASE_ROWS):
        header, parsed = insp.parse_csv(csv_text(rows))
        numeric, positions = insp.extract_numeric_rows(header, parsed)
        return insp.find_candidates(numeric, header, positions)

    def test_each_concept_finds_its_rows(self):
        found = self.candidates()
        element = lambda key: [row["要素ID"] for row in found[key]]  # noqa: E731
        self.assertEqual(element("revenue"), ["jppfs_cor:NetSales"])
        self.assertEqual(element("operating_income"), ["jppfs_cor:OperatingIncome"])
        self.assertEqual(element("ordinary_income"), ["jppfs_cor:OrdinaryIncome"])  # 個別（NonConsolidatedMember）も含む
        self.assertEqual(element("net_income"), ["jppfs_cor:ProfitLossAttributableToOwnersOfParent"])
        self.assertEqual(len(found["segment_sales"]), 2)   # Member を含むもの
        self.assertEqual([row["コンテキストID"] for row in found["region_sales"]], [REG])
        self.assertEqual(element("employees"), ["jpcrp_cor:NumberOfEmployees"])
        self.assertEqual(len(found["average_age"]), 1)
        self.assertEqual(len(found["average_service"]), 1)
        self.assertEqual(len(found["average_salary"]), 1)

    def test_matches_by_element_id_alone_and_by_label_alone(self):
        rows = [r("jppfs_cor:NetSales", "名前が違う項目", CUR, "1"),          # 要素IDだけ一致
                r("jpcrp_cor:Unknown", "売上収益", CUR, "2"),                  # 項目名だけ一致
                r("jpigp_cor:RevenueIFRS", "売上収益", CUR, "3"),              # 両方
                r("jppfs_cor:CostOfSales", "売上原価", CUR, "4")]             # どちらも一致しない
        found = self.candidates(rows)["revenue"]
        self.assertEqual([row["値"] for row in found], ["1", "2", "3"])

    def test_id_match_is_case_insensitive_partial(self):
        found = self.candidates([r("jppfs_cor:xxnetsalesyy", "x", CUR, "1")])["revenue"]
        self.assertEqual(len(found), 1)

    def test_segment_rows_are_not_in_total_concepts(self):
        rows = [r("jppfs_cor:NetSales", "売上高", SEG, "9"), r("jppfs_cor:NetSales", "売上高", CUR, "1")]
        found = self.candidates(rows)
        self.assertEqual([row["値"] for row in found["revenue"]], ["1"])
        self.assertEqual([row["値"] for row in found["segment_sales"]], [])  # 外部顧客の語がない

    def test_at_most_30_rows_per_concept_and_current_year_first(self):
        rows = [r("jppfs_cor:NetSales", "売上高", "Prior1YearDuration", str(i)) for i in range(40)]
        rows.append(r("jppfs_cor:NetSales", "売上高", CUR, "999"))
        header, parsed = insp.parse_csv(csv_text(rows))
        numeric, positions = insp.extract_numeric_rows(header, parsed)
        found = insp.find_candidates(numeric, header, positions)["revenue"]
        self.assertEqual(len(found), 41)
        self.assertEqual(found[0]["値"], "999")  # 当期らしい行が先
        text = insp.render({"doc_id": "S100AAA1", "files": [], "errors": [], "numeric_rows": [],
                            "csv_files": [{"name": "a.csv", "encoding": "x", "columns": HEADER, "row_count": 41,
                                           "numeric_row_count": 41, "_candidates": {k[0]: [] for k in insp.CONCEPTS} | {"revenue": found},
                                           "_names": insp.unique_headers(HEADER), "_positions": positions}]})
        self.assertIn("候補 41行、表示 30", text)
        self.assertEqual(text.count("jppfs_cor:NetSales"), 30)


class MainTest(Base):
    def run_one(self, response=None, extra_argv=(), **kwargs):
        server = DocServer(response or zip_response())
        return (*self.run_main(["--doc-id", "S100AAA1", *extra_argv], server, **kwargs), server)

    def test_screen_output(self):
        code, out, err, _, server = self.run_one()
        self.assertEqual(code, 0, msg=err)
        self.assertIn("■ 書類 S100AAA1", out)
        self.assertIn(CSV_NAME, out)                       # ZIPの中のファイル
        self.assertIn("XBRL_TO_CSV/note.txt", out)
        self.assertIn("文字コード: UTF-16LE（BOMあり）", out)
        self.assertIn("行数: 14（数値の行 10）", out)
        self.assertIn("列名: 要素ID | 項目名 | コンテキストID | 相対年度 | 連結・個別 | 期間・時点 | ユニットID | 単位 | 値", out)
        for label in ("売上高（売上収益を含む）", "営業利益", "経常利益", "親会社株主（所有者）に帰属する当期純利益",
                      "セグメントの外部顧客への売上", "地域別の売上", "従業員数", "平均年齢", "平均勤続年数", "平均年間給与"):
            self.assertIn(f"【{label}】", out)
        self.assertIn("jppfs_cor:NetSales", out)
        self.assertIn("1234567000", out)
        self.assertNotIn("文章の行", out)
        self.assertNotIn("あいう", out)
        # 要素IDは、長くても切らずに全部出す（調べるための出力）
        self.assertIn("jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees", out)
        self.assertIn("E01950-000SemiconductorMember", out)
        self.assertEqual([p for _, p, *_ in server.requests], ["/api/v2/documents/S100AAA1"])

    def test_each_encoding_works_end_to_end(self):
        for name in ENCODERS:
            code, out, err, _, _ = self.run_one(zip_response(encoder=name))
            self.assertEqual(code, 0, msg=f"{name}: {err}")
            self.assertIn(f"文字コード: {name}", out)
            self.assertIn("1234567000", out)
            self.assertIn("親会社株主に帰属する当期純利益", out)

    def test_out_json_has_all_numeric_rows_with_column_names(self):
        out_file = self.tmp / "o.json"
        code, out, err, _, _ = self.run_one(extra_argv=["--out", str(out_file)])
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out_file.read_text(encoding="utf-8"))
        doc = data["documents"][0]
        self.assertEqual(doc["doc_id"], "S100AAA1")
        self.assertEqual(len(doc["numeric_rows"]), 10)
        first = doc["numeric_rows"][0]
        self.assertEqual(first["doc_id"], "S100AAA1")
        self.assertEqual(first["file"], CSV_NAME)
        self.assertEqual(first["values"], dict(zip(HEADER, BASE_ROWS[0])))  # 列名のまま
        self.assertEqual(doc["csv_files"][0]["columns"], HEADER)
        self.assertEqual(doc["csv_files"][0]["row_count"], 14)
        self.assertEqual([f["name"] for f in doc["files"]], [CSV_NAME, "XBRL_TO_CSV/note.txt"])
        self.assertEqual(data["parameters"], {"doc_ids": ["S100AAA1"], "api_requests": 1})
        self.assertNotIn("_candidates", json.dumps(data))
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("文章の行", text)  # 文章の行は、JSONにも入れない

    def test_multiple_docs_and_one_failure(self):
        server = DocServer(zip_response())
        server.steps = [zip_response(), FakeResponse({"metadata": {"status": "404", "message": "Not Found"}})]
        out_file = self.tmp / "o.json"
        code, out, err, _ = self.run_main(
            ["--doc-id", "S100AAA1", "--doc-id", "S100AAA2", "--doc-id", "S100AAA1", "--out", str(out_file)], server)
        self.assertEqual(code, 1)  # 1件でも問題があれば、0以外
        self.assertEqual(len(server.requests), 2)  # 重複は1回
        self.assertIn("取得に失敗した", out)
        self.assertIn("問題のあった書類 1件", out)
        data = json.loads(out_file.read_text(encoding="utf-8"))  # 失敗の記録も含めて書く
        self.assertEqual([d["doc_id"] for d in data["documents"]], ["S100AAA1", "S100AAA2"])
        self.assertTrue(data["documents"][1]["errors"])
        self.assertEqual(len(data["documents"][0]["numeric_rows"]), 10)

    def test_json_error_responses(self):
        for body in ({"metadata": {"status": "404", "message": "Not Found"}},
                     {"StatusCode": 401, "message": "Access denied due to invalid subscription key."},
                     {"metadata": {"status": "200", "message": "OK"}}):
            code, out, err, _, _ = self.run_one(FakeResponse(body))
            self.assertEqual(code, 1, msg=body)
            self.assertIn("取得に失敗した", out)
            fk.assert_no_key(self, out, err)

    def test_not_zip_data_in_zip_marker(self):
        code, out, _, _, _ = self.run_one(FakeResponse(b"PK\x03\x04broken"))
        self.assertEqual(code, 1)
        self.assertIn("ZIP", out)

    def test_csv_with_unknown_header_reports_columns_and_continues(self):
        bad = csv_text(header=["A", "B", "C"], rows=[["1", "2", "3"]])
        code, out, _, _, _ = self.run_one(zip_response(bad))
        self.assertEqual(code, 1)
        self.assertIn("実際の列名: A, B, C", out)

    def test_undecodable_csv(self):
        code, out, _, _, _ = self.run_one(FakeResponse(make_zip(b"\xff\xfe\xfd\x81\x00\x80binary")))
        self.assertEqual(code, 1)
        self.assertIn("文字コードを判定できない", out)

    def test_zip_without_csv(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("XBRL_TO_CSV/readme.txt", "x")
        code, out, _, _, _ = self.run_one(FakeResponse(buffer.getvalue()))
        self.assertEqual(code, 0)
        self.assertIn("readme.txt", out)


class LimitTest(Base):
    def test_total_uncompressed_size_limit(self):
        big = make_zip(ENCODERS["UTF-8（BOM付き、またはBOMなし）"](csv_text()), extra=[("XBRL_TO_CSV/big.bin", b"0" * 5000)])
        with mock.patch.object(insp, "MAX_UNCOMPRESSED_BYTES", 4000):
            with self.assertRaises(ValueError) as raised:
                insp.read_zip(big)
            self.assertIn("大きすぎる", str(raised.exception))
            code, out, err, _ = self.run_main(["--doc-id", "S100AAA1"], DocServer(FakeResponse(big)))
        self.assertEqual(code, 1)
        self.assertIn("展開後の合計が大きすぎる", out)
        self.assertEqual(insp.MAX_UNCOMPRESSED_BYTES, 200 * 1024 * 1024)

    def test_size_exactly_at_limit_is_allowed(self):
        data = make_zip(b"a,b\n1,2\n")
        total = sum(i.file_size for i in zipfile.ZipFile(io.BytesIO(data)).infolist())
        with mock.patch.object(insp, "MAX_UNCOMPRESSED_BYTES", total):
            self.assertEqual(len(insp.read_zip(data)), 2)

    def test_file_count_limit(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for i in range(6):
                archive.writestr(f"f{i}.txt", "x")
        with mock.patch.object(insp, "MAX_ZIP_FILES", 5):
            with self.assertRaises(ValueError) as raised:
                insp.read_zip(buffer.getvalue())
        self.assertIn("ファイルが多すぎる", str(raised.exception))
        self.assertEqual(insp.MAX_ZIP_FILES, 500)

    def test_decompression_bomb_is_stopped_by_declared_size(self):
        bomb = make_zip(b"0" * 3_000_000)  # 小さく圧縮されるが、展開後は大きい
        self.assertLess(len(bomb), 20_000)
        with mock.patch.object(insp, "MAX_UNCOMPRESSED_BYTES", 1_000_000):
            with self.assertRaises(ValueError):
                insp.read_zip(bomb)

    def test_download_size_limit_is_enforced_by_the_client(self):
        server = DocServer(FakeResponse(b"PK" + b"x" * 100))
        with mock.patch.object(fk.client, "MAX_DOWNLOAD_BYTES", 50):
            edinet = fk.client.EdinetClient(KEY, open_url=server)
            with self.assertRaises(fk.client.EdinetError):
                edinet.get_document("S100AAA1", max_bytes=fk.client.MAX_DOWNLOAD_BYTES)

    def test_zip_is_extracted_in_memory_only(self):
        work = self.tmp / "work"
        work.mkdir()
        tmpdir = self.tmp / "tmpdir"
        tmpdir.mkdir()
        cwd = os.getcwd()
        os.chdir(work)
        try:
            with mock.patch.object(tempfile, "tempdir", str(tmpdir)):
                self.run_main(["--doc-id", "S100AAA1"], DocServer(zip_response()))
            self.assertEqual(os.listdir(work), [])
            self.assertEqual(os.listdir(tmpdir), [])
        finally:
            os.chdir(cwd)

    def test_names_inside_zip_are_sanitized_and_never_used_as_paths(self):
        name = "../../evil\x1b[31m.csv"
        data = make_zip(ENCODERS["UTF-8（BOM付き、またはBOMなし）"](csv_text()), name=name)
        code, out, _, _ = self.run_main(["--doc-id", "S100AAA1"], DocServer(FakeResponse(data)))
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", out)
        self.assertFalse((self.tmp.parent / "evil.csv").exists())


class RequestsAndOutTest(Base):
    def test_max_requests_exceeded_before_any_request(self):
        server = DocServer(zip_response())
        argv = [a for i in range(3) for a in ("--doc-id", f"S100AAA{i}")] + ["--max-requests", "2"]
        code, _, err, _ = self.run_main(argv, server)
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])
        self.assertIn("--max-requests", err)

    def test_default_is_10_and_boundary(self):
        self.assertEqual(insp.parse_args(["--doc-id", "S100AAA1"]).max_requests, 10)
        server = DocServer(zip_response())
        argv = [a for i in range(10) for a in ("--doc-id", f"S100AAA{i}")]
        code, _, _, _ = self.run_main(argv, server)
        self.assertEqual(code, 0)
        self.assertEqual(len(server.requests), 10)
        argv = [a for i in range(11) for a in ("--doc-id", f"S100AA{i:02d}")]
        code, _, _, _ = self.run_main(argv, DocServer(zip_response()))
        self.assertEqual(code, 2)

    def test_retries_count_toward_the_limit(self):
        def limited(request):
            raise http_error(request, 429)
        server = DocServer(limited)
        code, out, _, _ = self.run_main(["--doc-id", "S100AAA1", "--max-requests", "1"], server)
        self.assertEqual(code, 1)
        self.assertEqual(len(server.requests), 1)
        self.assertIn("上限", out)

    def test_429_retry_then_success(self):
        def limited(request):
            raise http_error(request, 429)
        clock = Clock()
        server = DocServer(limited, zip_response(), clock=clock)
        code, out, _, clock = self.run_main(["--doc-id", "S100AAA1"], server, clock=clock)
        self.assertEqual(code, 0)
        self.assertEqual(clock.sleeps, [30])

    def test_calls_are_one_second_apart(self):
        clock = Clock()
        server = DocServer(zip_response(), clock=clock)
        argv = [a for i in range(3) for a in ("--doc-id", f"S100AAA{i}")]
        _, _, _, clock = self.run_main(argv, server, clock=clock)
        self.assertEqual(clock.sleeps, [1.0, 1.0])

    def test_invalid_doc_id_and_missing_key(self):
        for doc_id in ("../x", "bad", "S100AAA1/x"):
            server = DocServer(zip_response())
            code, _, err, _ = self.run_main(["--doc-id", doc_id], server)
            self.assertEqual(code, 2, msg=doc_id)
            self.assertEqual(server.requests, [])
        server = DocServer(zip_response())
        code, _, err, _ = self.run_main(["--doc-id", "S100AAA1"], server, env={})
        self.assertEqual(code, 2)
        self.assertIn("EDINET_API_KEY", err)
        self.assertEqual(server.requests, [])

    def test_out_under_data_auto_is_refused(self):
        root = insp.__dict__["check_out_path"].__globals__["REPO_ROOT"]
        target = root / "data" / "auto" / "x.json"
        server = DocServer(zip_response())
        code, _, err, _ = self.run_main(["--doc-id", "S100AAA1", "--out", str(target)], server)
        self.assertEqual(code, 2)
        self.assertIn("data/auto/", err)
        self.assertEqual(server.requests, [])
        self.assertFalse(target.exists())

    def test_out_with_missing_folder_is_refused(self):
        code, _, _, _ = self.run_main(["--doc-id", "S100AAA1", "--out", str(self.tmp / "no" / "o.json")],
                                      DocServer(zip_response()))
        self.assertEqual(code, 2)

    def test_no_file_is_written_without_out(self):
        work = self.tmp / "w"
        work.mkdir()
        cwd = os.getcwd()
        os.chdir(work)
        try:
            self.run_main(["--doc-id", "S100AAA1"], DocServer(zip_response()))
            self.assertEqual(os.listdir(work), [])
        finally:
            os.chdir(cwd)

    def test_key_cannot_be_passed_as_argument(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            insp.parse_args(["--doc-id", "S100AAA1", "--key", KEY])


class SecretTest(Base):
    def leaking_errors(self):
        url = f"https://api.edinet-fsa.go.jp/api/v2/documents/S100AAA1?type=5&Subscription-Key={KEY}"
        return [urllib.error.URLError(f"failed {url}"), OSError(f"cannot connect {url}"),
                ValueError(f"unexpected {url.replace(KEY, fk.ENCODED_KEY)}"), RuntimeError(f"key={KEY}")]

    def test_key_never_appears_in_output_or_json(self):
        out_file = self.tmp / "o.json"
        for error in self.leaking_errors():
            code, out, err, _ = self.run_main(["--doc-id", "S100AAA1", "--out", str(out_file)], DocServer(error))
            self.assertEqual(code, 1, msg=repr(error))
            fk.assert_no_key(self, out, err, out_file.read_text(encoding="utf-8"))
            self.assertNotIn("Traceback", err + out)
            out_file.unlink()
        code, out, err, _ = self.run_main(["--doc-id", "S100AAA1", "--out", str(out_file)], DocServer(zip_response()))
        self.assertEqual(code, 0)
        fk.assert_no_key(self, out, err, out_file.read_text(encoding="utf-8"))

    def test_server_message_with_key_is_masked(self):
        body = {"StatusCode": 400, "message": f"bad request Subscription-Key={KEY} and {KEY}"}
        code, out, err, _ = self.run_main(["--doc-id", "S100AAA1"], DocServer(FakeResponse(body)))
        self.assertEqual(code, 1)
        fk.assert_no_key(self, out, err)

    def test_unexpected_exception_in_processing_is_masked(self):
        with mock.patch.object(insp, "inspect_zip", side_effect=RuntimeError(f"boom {KEY}")):
            code, out, err, _ = self.run_main(["--doc-id", "S100AAA1"], DocServer(zip_response()))
        self.assertEqual(code, 1)
        fk.assert_no_key(self, out, err)
        self.assertIn("RuntimeError", err)


if __name__ == "__main__":
    unittest.main()
