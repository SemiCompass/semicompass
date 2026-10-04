"""inspect_document.py の --include-dei の確認（DEIは、要素IDが jpdei_cor: で始まる行）。"""

import contextlib
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

import edinet_fakes as fk
from edinet_fakes import KEY, Clock, FakeResponse
from test_client_document import DocServer
from test_inspect_document import (BASE_ROWS, CSV_NAME, CUR, ENCODERS, HEADER, Base, csv_text, make_zip, r,
                                   zip_response)

insp = __import__("inspect_document")

DEI_ROWS = [
    r("jpdei_cor:EDINETCodeDEI", "EDINETコード、DEI", "FilingDateInstant", "E01950", unit=""),
    r("jpdei_cor:AccountingStandardsDEI", "会計基準、DEI", "FilingDateInstant", "Japan GAAP", unit=""),
    r("jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI", "連結財務諸表の作成の有無、DEI",
      "FilingDateInstant", "true", unit=""),
    r("jpdei_cor:CurrentFiscalYearStartDateDEI", "当事業年度開始日、DEI", CUR, "2025-04-01", unit=""),
    r("jpdei_cor:NumberOfSubmissionDEI", "提出回数、DEI", "FilingDateInstant", "1", unit=""),   # 数値のDEI
]
# 既存のテスト用データ（BASE_ROWS）にあるDEIの行は除き、このファイルのDEI_ROWSだけをDEIとして数える
NON_DEI = [row for row in BASE_ROWS if not row[0].startswith("jpdei_cor:")]
ROWS = NON_DEI + DEI_ROWS


def many_dei(n, prefix="X"):
    return [r(f"jpdei_cor:{prefix}{i}DEI", f"項目{i}", "FilingDateInstant", f"v{i}", unit="") for i in range(n)]


class DeiTest(Base):
    def run_dei(self, rows=ROWS, flag=True, encoder="UTF-16LE（BOMあり）", out_name="o.json", extra=()):
        out_file = self.tmp / out_name
        argv = ["--doc-id", "S100AAA1", "--out", str(out_file), *extra] + (["--include-dei"] if flag else [])
        code, out, err, _ = self.run_main(argv, DocServer(zip_response(csv_text(rows), encoder=encoder)))
        data = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else None
        return code, out, err, data

    def test_parse_args_default_is_false(self):
        self.assertFalse(insp.parse_args(["--doc-id", "S100AAA1"]).include_dei)
        self.assertTrue(insp.parse_args(["--doc-id", "S100AAA1", "--include-dei"]).include_dei)

    def test_without_flag_nothing_changes(self):
        code, out, err, data = self.run_dei(flag=False)
        self.assertEqual(code, 0, msg=err)
        self.assertNotIn("DEI", out)
        self.assertNotIn("jpdei_cor", out)
        doc = data["documents"][0]
        self.assertNotIn("dei_rows", doc)
        self.assertNotIn("dei_row_total", doc)
        self.assertEqual(set(doc), {"doc_id", "files", "csv_files", "errors", "numeric_rows"})
        self.assertEqual(set(doc["csv_files"][0]), {"name", "encoding", "columns", "row_count", "numeric_row_count"})

    def test_with_flag_dei_rows_include_non_numeric_rows(self):
        code, out, err, data = self.run_dei()
        self.assertEqual(code, 0, msg=err)
        doc = data["documents"][0]
        self.assertEqual(doc["dei_row_total"], 5)
        self.assertEqual([x["values"]["要素ID"] for x in doc["dei_rows"]],
                         [row[0] for row in DEI_ROWS])
        first = doc["dei_rows"][1]
        self.assertEqual(first["doc_id"], "S100AAA1")
        self.assertEqual(first["file"], CSV_NAME)
        self.assertEqual(first["values"], dict(zip(HEADER, DEI_ROWS[1])))  # 列名のまま、すべての列
        self.assertEqual(first["values"]["値"], "Japan GAAP")  # 数値以外の行を含む

    def test_numeric_rows_are_not_changed_by_the_flag(self):
        _, _, _, without = self.run_dei(flag=False, out_name="a.json")
        _, _, _, with_flag = self.run_dei(flag=True, out_name="b.json")
        a, b = without["documents"][0], with_flag["documents"][0]
        self.assertEqual(a["numeric_rows"], b["numeric_rows"])
        # 数値のDEI（NumberOfSubmissionDEI）は numeric_rows にも dei_rows にもある。文章のDEIは numeric_rows にない
        elements = {x["values"]["要素ID"] for x in b["numeric_rows"]}
        self.assertIn("jpdei_cor:NumberOfSubmissionDEI", elements)
        self.assertNotIn("jpdei_cor:AccountingStandardsDEI", elements)
        self.assertEqual(a["csv_files"], b["csv_files"])

    def test_screen_shows_element_label_context_and_value(self):
        code, out, _, _ = self.run_dei()
        self.assertIn("【DEI（jpdei_cor:）】 5行", out)
        section = out.split("【DEI（jpdei_cor:）】")[1]
        header_line = section.splitlines()[1].split()
        self.assertEqual(header_line, ["要素ID", "項目名", "コンテキストID", "値"])
        for text in ("jpdei_cor:AccountingStandardsDEI", "会計基準、DEI", "FilingDateInstant", "Japan GAAP",
                     "jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI", "true", "E01950"):
            self.assertIn(text, section)
        self.assertNotIn("連結・個別", section)  # 4列だけ

    def test_only_jpdei_cor_prefix_is_taken(self):
        rows = [r("jppfs_cor:NetSales", "売上高", CUR, "1"),
                r("xjpdei_cor:Fake", "x", CUR, "1"), r("jpdei_corX:Fake", "x", CUR, "1"),
                r("jpcrp_cor:AccountingStandardsDEI", "x", CUR, "1"),
                r("jpdei_cor:AccountingStandardsDEI", "会計基準", "FilingDateInstant", "IFRS", unit="")]
        _, _, _, data = self.run_dei(rows)
        self.assertEqual([x["values"]["要素ID"] for x in data["documents"][0]["dei_rows"]],
                         ["jpdei_cor:AccountingStandardsDEI"])

    def test_limit_is_200_rows_per_document(self):
        _, out, _, data = self.run_dei(many_dei(250))
        doc = data["documents"][0]
        self.assertEqual(insp.MAX_DEI_ROWS, 200)
        self.assertEqual(len(doc["dei_rows"]), 200)
        self.assertEqual(doc["dei_row_total"], 250)
        self.assertEqual(doc["dei_rows"][-1]["values"]["要素ID"], "jpdei_cor:X199DEI")  # 先頭から200行
        self.assertIn("250行、表示 200（書類ごとの上限 200）", out)
        self.assertEqual(out.count("jpdei_cor:X"), 200)

    def test_exactly_200_rows_has_no_truncation_note(self):
        _, out, _, data = self.run_dei(many_dei(200))
        self.assertEqual(len(data["documents"][0]["dei_rows"]), 200)
        self.assertIn("【DEI（jpdei_cor:）】 200行\n", out)
        self.assertNotIn("書類ごとの上限", out)

    def test_limit_is_shared_across_csv_files_of_one_document(self):
        extra = [("XBRL_TO_CSV/jpcrp040300-ssr-001_E01950-000_2026-09-30_01_2026-11-13.csv",
                  ENCODERS["UTF-16LE（BOMあり）"](csv_text(many_dei(150, "B"))))]
        raw = make_zip(ENCODERS["UTF-16LE（BOMあり）"](csv_text(many_dei(150, "A"))), extra=extra)
        out_file = self.tmp / "o.json"
        code, out, _, _ = self.run_main(["--doc-id", "S100AAA1", "--include-dei", "--out", str(out_file)],
                                        DocServer(FakeResponse(raw)))
        doc = json.loads(out_file.read_text(encoding="utf-8"))["documents"][0]
        self.assertEqual(code, 0)
        self.assertEqual((len(doc["dei_rows"]), doc["dei_row_total"]), (200, 300))
        self.assertEqual(sum(1 for x in doc["dei_rows"] if x["values"]["要素ID"].startswith("jpdei_cor:B")), 50)

    def test_limit_is_per_document_not_global(self):
        server = DocServer(zip_response(csv_text(many_dei(150))))
        out_file = self.tmp / "o.json"
        code, _, _, _ = self.run_main(["--doc-id", "S100AAA1", "--doc-id", "S100AAA2", "--include-dei",
                                       "--out", str(out_file)], server)
        docs = json.loads(out_file.read_text(encoding="utf-8"))["documents"]
        self.assertEqual([len(d["dei_rows"]) for d in docs], [150, 150])

    def test_document_without_dei_rows(self):
        _, out, _, data = self.run_dei(NON_DEI)
        doc = data["documents"][0]
        self.assertEqual((doc["dei_rows"], doc["dei_row_total"]), ([], 0))
        self.assertIn("【DEI（jpdei_cor:）】 0行", out)

    def test_failed_document_has_empty_dei_rows_with_flag(self):
        out_file = self.tmp / "o.json"
        code, _, _, _ = self.run_main(["--doc-id", "S100AAA1", "--include-dei", "--out", str(out_file)],
                                      DocServer(FakeResponse({"metadata": {"status": "404", "message": "Not Found"}})))
        doc = json.loads(out_file.read_text(encoding="utf-8"))["documents"][0]
        self.assertEqual(code, 1)
        self.assertEqual((doc["dei_rows"], doc["dei_row_total"]), ([], 0))

    def test_each_encoding_with_dei(self):
        for name in ENCODERS:
            _, out, err, data = self.run_dei(encoder=name)
            self.assertEqual(len(data["documents"][0]["dei_rows"]), 5, msg=f"{name}: {err}")
            self.assertIn("会計基準、DEI", out)

    def test_dei_rows_are_not_in_the_file_when_csv_header_is_unexpected(self):
        bad = csv_text(header=["A", "B", "C"], rows=[["jpdei_cor:X", "2", "3"]])
        _, out, _, data = self.run_dei(bad and [], flag=True)  # 正しい形のCSV（行なし）
        self.assertEqual(data["documents"][0]["dei_rows"], [])
        code, out, _, _ = self.run_main(["--doc-id", "S100AAA1", "--include-dei"],
                                        DocServer(zip_response(bad)))
        self.assertEqual(code, 1)
        self.assertIn("実際の列名: A, B, C", out)

    def test_key_never_appears_with_the_flag(self):
        out_file = self.tmp / "o.json"
        url = f"https://api.edinet-fsa.go.jp/api/v2/documents/S100AAA1?type=5&Subscription-Key={KEY}"
        for error in (urllib.error.URLError(f"failed {url}"), RuntimeError(f"key={KEY}")):
            code, out, err, _ = self.run_main(["--doc-id", "S100AAA1", "--include-dei", "--out", str(out_file)],
                                              DocServer(error))
            self.assertEqual(code, 1)
            fk.assert_no_key(self, out, err, out_file.read_text(encoding="utf-8"))
            out_file.unlink()
        with mock.patch.object(insp, "extract_dei_rows", side_effect=RuntimeError(f"boom {KEY}")):
            code, out, err, _ = self.run_main(["--doc-id", "S100AAA1", "--include-dei"],
                                              DocServer(zip_response(csv_text(ROWS))))
        self.assertEqual(code, 1)
        fk.assert_no_key(self, out, err)

    def test_no_files_are_written_with_flag_but_without_out(self):
        work = self.tmp / "w"
        work.mkdir()
        cwd = os.getcwd()
        os.chdir(work)
        try:
            self.run_main(["--doc-id", "S100AAA1", "--include-dei"], DocServer(zip_response(csv_text(ROWS))))
            self.assertEqual(os.listdir(work), [])
        finally:
            os.chdir(cwd)

    def test_out_under_data_auto_is_still_refused(self):
        root = insp.check_out_path.__globals__["REPO_ROOT"]
        server = DocServer(zip_response())
        code, _, err, _ = self.run_main(["--doc-id", "S100AAA1", "--include-dei", "--out",
                                         str(root / "data" / "auto" / "x.json")], server)
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])


if __name__ == "__main__":
    unittest.main()
