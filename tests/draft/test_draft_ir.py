"""IR重要ポイントの下書き（scripts/draft/draft_ir.py）と、決算発表の行の反映（scripts/edinet/add_announcement.py）のテスト。
AIとR2は模擬する。"""
import contextlib
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "llm"))
sys.path.insert(0, str(ROOT / "scripts" / "draft"))
sys.path.insert(0, str(ROOT / "scripts" / "edinet"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import add_announcement  # noqa: E402
import draft_ir  # noqa: E402
import llm_fakes as fk  # noqa: E402
from test_draft_company import ENV, FakeR2, NoSuchKey  # noqa: E402

SLUG = "advantest"
OUTPUT = {
    "performance_summary": {"text": "2027年3月期第2四半期累計の売上高は1,200.0億円で前年同期比＋10.0%、営業利益は150.0億円で＋5.0%だった。" + fk.OUTPUT_WORD,
                            "source_ids": ["S1"]},
    "outlook": {"text": "会社は、2027年3月期の通期の業績予想を据え置いた。", "source_ids": ["S1"]},
    "highlights": {"text": "新しい試験装置の出荷を始め、国内工場の生産能力を増やす。", "source_ids": ["S1", "S2"]},
    "uses_quarterly_figures": False,
}


def bundle(**over):
    data = {"schema_version": 1, "bundle_id": f"{SLUG}-2027-03-q2", "company": SLUG, "fiscal_period_end": "2027-03",
            "quarter": 2, "announced_on": "2026-10-28", "extracted_at": "2026-10-29T09:00:00+09:00",
            "documents": [
                {"id": "S1", "type": "tanshin", "title": "決算短信", "url": "https://www.release.tdnet.info/a.pdf",
                 "pages": 1, "chars": 40, "paragraphs": [{"page": 1, "text": fk.SOURCE_WORD + "売上高は増えた。" + fk.cjk(300)}]},
                {"id": "S2", "type": "presentation", "title": "決算説明資料", "url": "https://www.advantest.com/ir/b.pdf",
                 "pages": 1, "chars": 20, "paragraphs": [{"page": 1, "text": "新製品の出荷。" + fk.cjk(200, 0x5300)}]}]}
    data.update(over)
    return data


class DraftIrTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)
        self.root = self.tmp / "repo"
        self.out, self.ledger = self.tmp / "out", self.tmp / "ledger"
        self.ledger.mkdir()
        (self.root / "data" / "companies").mkdir(parents=True)
        (self.root / "data" / "segments").mkdir(parents=True)
        for rel in (f"data/companies/{SLUG}.yaml", f"data/segments/{SLUG}.yaml"):
            shutil.copy(ROOT / rel, self.root / rel)
        self.operations = self.tmp / "operations.yaml"
        self.operations.write_text("status: active\n", encoding="utf-8")

    def run_draft(self, client, r2=None):
        summary = self.tmp / "summary.md"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = draft_ir.main(["--company", SLUG, "--fiscal-period-end", "2027-03", "--quarter", "2",
                                  "--out-dir", str(self.out), "--ledger-dir", str(self.ledger), "--run-id", "run7",
                                  "--summary", str(summary)],
                                 env=ENV, now=lambda: fk.NOW, r2_factory=lambda creds: r2 or FakeR2(bundle()),
                                 client_factory=lambda: client, sleep=lambda s: None, root=self.root,
                                 budgets_path=ROOT / "config" / "budgets.yaml", operations_path=self.operations)
        self.logs = out.getvalue() + err.getvalue() + (summary.read_text(encoding="utf-8") if summary.exists() else "")
        return code

    def test_writes_draft_announcement_and_pr_body(self):
        code = self.run_draft(fk.FakeClient(fk.reply(OUTPUT)))
        self.assertEqual(code, 0, self.logs)
        rel = "content/ir-points/advantest/2027-03-q2.md"
        text = (self.out / rel).read_text(encoding="utf-8")
        front = yaml.safe_load(text.split("---\n", 2)[1])
        self.assertEqual((front["draft"], front["announced_on"], [s["id"] for s in front["sources"]]), (True, "2026-10-28", ["S1", "S2"]))
        row = json.loads((self.out / "announcement.json").read_text(encoding="utf-8"))
        self.assertEqual(add_announcement.announcement_validator().is_valid(row), True)
        body = (self.out / "pr-body.md").read_text(encoding="utf-8")
        self.assertIn("2027年3月期第2四半期", body)
        for word in (fk.SOURCE_WORD, fk.OUTPUT_WORD):
            self.assertNotIn(word, self.logs + body)

    def test_task_has_semiconductor_segments_and_materials_are_separate(self):
        client = fk.FakeClient(fk.reply(OUTPUT))
        self.assertEqual(self.run_draft(client), 0, self.logs)
        sent = json.dumps(client.calls[0], ensure_ascii=False)
        self.assertIn("semiconductor_segments", sent)
        self.assertIn('<文書 id=', sent)
        self.assertIn(fk.SOURCE_WORD, sent)  # 資料は、AIへの入力にだけ入る

    def test_investment_words_fail_and_nothing_written(self):
        bad = copy.deepcopy(OUTPUT)
        bad["highlights"]["text"] = "新製品は株価の買い材料になる。"
        code = self.run_draft(fk.FakeClient(fk.reply(bad)))
        self.assertEqual(code, 1)
        self.assertFalse((self.out / "content").exists())

    def test_reprint_rewrites_once(self):
        copied = copy.deepcopy(OUTPUT)
        copied["outlook"]["text"] = (fk.SOURCE_WORD + "売上高は増えた。" + fk.cjk(300))[:60]
        code = self.run_draft(fk.FakeClient(fk.reply(copied), fk.reply(OUTPUT)))
        self.assertEqual(code, 0, self.logs)
        self.assertIn("書き直させる", self.logs)
        self.assertNotIn(fk.SOURCE_WORD, self.logs)

    def test_bundle_mismatch_and_missing(self):
        self.assertEqual(self.run_draft(fk.FakeClient(fk.reply(OUTPUT)), r2=FakeR2(bundle(quarter=3))), 1)
        self.assertIn("違う", self.logs)
        self.assertEqual(self.run_draft(fk.FakeClient(fk.reply(OUTPUT)), r2=FakeR2(error=NoSuchKey())), 1)

    def test_existing_file_is_not_overwritten(self):
        path = self.root / "content" / "ir-points" / SLUG / "2027-03-q2.md"
        path.parent.mkdir(parents=True)
        path.write_text("x", encoding="utf-8")
        self.assertEqual(self.run_draft(fk.FakeClient(fk.reply(OUTPUT))), 1)

    def test_period_label(self):
        self.assertEqual(draft_ir.period_label("2027-03", 4), "2027年3月期")
        self.assertEqual(draft_ir.period_label("2026-12", 1), "2026年12月期第1四半期")


class AddAnnouncementTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "data" / "auto").mkdir(parents=True)
        self.path = self.root / "data" / "auto" / "testco.json"
        self.path.write_text(json.dumps({"schema_version": 1, "company": "testco", "announcements": []}), encoding="utf-8")
        self.row = draft_ir.build_announcement(bundle(company="testco"), "2026-10-29T09:00:00+09:00")
        self.file = self.root / "a.json"

    def apply(self, row):
        self.file.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return add_announcement.main(["--company", "testco", "--file", str(self.file)], root=self.root)

    def test_add_then_replace(self):
        self.assertEqual(self.apply(self.row), 0)
        changed = dict(self.row, announced_on="2026-10-27")
        self.assertEqual(self.apply(changed), 0)
        rows = json.loads(self.path.read_text(encoding="utf-8"))["announcements"]
        self.assertEqual([r["announced_on"] for r in rows], ["2026-10-27"])

    def test_sorted_by_date(self):
        self.apply(self.row)
        older = dict(self.row, fiscal_period_end="2026-03", quarter=4, announced_on="2026-04-28")
        self.apply(older)
        rows = json.loads(self.path.read_text(encoding="utf-8"))["announcements"]
        self.assertEqual([r["quarter"] for r in rows], [4, 2])

    def test_bad_row_is_refused(self):
        self.assertEqual(self.apply(dict(self.row, quarter=5)), 1)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["announcements"], [])


if __name__ == "__main__":
    unittest.main()
