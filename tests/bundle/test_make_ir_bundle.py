"""IR重要ポイントの原資料束（scripts/bundle/make_ir_bundle.py）のテスト。通信とR2は模擬する。"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "bundle"))
sys.path.insert(0, str(ROOT / "tests" / "explainer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_explainer_bundle as web  # noqa: E402
import make_ir_bundle as mib  # noqa: E402
from bundle_fakes import R2_ENV, FakeR2  # noqa: E402
from explainer_fakes import make_pdf  # noqa: E402

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
SECRET_WORD = "ZetaSecretWord"
TANSHIN = "https://www.release.tdnet.info/inbs/140120261028000001.pdf"
DECK = "https://www.example-co.co.jp/ir/library/deck.pdf"


class FakeFetcher:
    def __init__(self, bodies):
        self.bodies = bodies
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        body = self.bodies.get(url)
        if body is None:
            raise web.FetchFailure("HTTP 404")
        return web.HttpResponse(status=200, body=body)


class IrBundleTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "data" / "companies").mkdir(parents=True)
        (self.root / "config").mkdir()
        shutil.copy(ROOT / "config" / "sources.yaml", self.root / "config" / "sources.yaml")
        self.write_master()

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_master(self, **extra):
        master = {"slug": "testco", "name": "テスト", "listing": "detailed", "type": "domestic_listed",
                  "ir_url": "https://www.example-co.co.jp/ir/", "website_url": "https://www.example-co.co.jp/", **extra}
        (self.root / "data" / "companies" / "testco.yaml").write_text(yaml.safe_dump(master, allow_unicode=True), encoding="utf-8")

    def run_main(self, extra=(), bodies=None, r2=None, env=R2_ENV):
        argv = ["--company", "testco", "--fiscal-period-end", "2027-03", "--quarter", "2", "--announced-on", "2026-10-28",
                "--tanshin-url", TANSHIN, *extra]
        fetcher = FakeFetcher(bodies if bodies is not None else {TANSHIN: make_pdf([f"Sales rose. {SECRET_WORD}."]),
                                                                  DECK: make_pdf(["New tool shipped."])})
        r2 = r2 or FakeR2()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mib.main(argv, env=env, now=lambda: NOW, fetcher=fetcher, r2_factory=lambda creds: r2, root=self.root)
        return code, out.getvalue(), err.getvalue(), r2, fetcher

    def test_saves_bundle_without_printing_text(self):
        code, out, err, r2, _ = self.run_main(["--presentation-url", DECK])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(r2.puts), 1)
        put = r2.puts[0]
        self.assertEqual(put["Key"], "bundles/ir/testco-2027-03-q2.json")
        bundle = json.loads(put["Body"])
        self.assertEqual([d["id"] for d in bundle["documents"]], ["S1", "S2"])
        self.assertEqual([d["type"] for d in bundle["documents"]], ["tanshin", "presentation"])
        self.assertIn(SECRET_WORD, json.dumps(bundle))
        self.assertNotIn(SECRET_WORD, out + err)

    def test_dry_run_needs_no_r2(self):
        code, out, err, r2, _ = self.run_main(["--dry-run"], env={})
        self.assertEqual(code, 0, err)
        self.assertEqual(r2.puts, [])

    def test_domain_not_allowed(self):
        code, _, err, r2, fetcher = self.run_main(["--presentation-url", "https://kabutan.example.jp/a.pdf"])
        self.assertEqual(code, 2)
        self.assertIn("許可", err)
        self.assertEqual((r2.puts, fetcher.urls), ([], []))

    def test_http_url_refused(self):
        code, _, err, _, _ = self.run_main(["--presentation-url", "http://www.example-co.co.jp/a.pdf"])
        self.assertEqual(code, 2)

    def test_only_detailed_companies(self):
        self.write_master(listing="coming_soon")
        code, _, err, _, _ = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("詳細掲載", err)

    def test_future_announcement_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = mib.main(["--company", "testco", "--fiscal-period-end", "2027-03", "--quarter", "2",
                             "--announced-on", "2026-11-30", "--tanshin-url", TANSHIN, "--dry-run"],
                            env={}, now=lambda: NOW, fetcher=FakeFetcher({}), root=self.root)
        self.assertEqual(code, 2)

    def test_not_pdf_and_fetch_failure(self):
        code, _, err, r2, _ = self.run_main(bodies={TANSHIN: b"<html>" + SECRET_WORD.encode() + b"</html>"})
        self.assertEqual(code, 1)
        self.assertIn("PDF", err)
        self.assertNotIn(SECRET_WORD, err)
        code, _, err, _, _ = self.run_main(bodies={})
        self.assertEqual(code, 1)
        self.assertIn("404", err)

    def test_allowed_domains_include_company_and_list(self):
        sources = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
        domains = mib.allowed_domains(sources, {"ir_url": "https://ir.example.com/ja/", "website_url": "https://www.example.com/"})
        self.assertTrue(mib.is_allowed(TANSHIN, domains))
        self.assertTrue(mib.is_allowed("https://ir.example.com/a.pdf", domains))
        self.assertFalse(mib.is_allowed("https://evil-example.com/a.pdf", domains))
        self.assertFalse(mib.is_allowed("https://www.release.tdnet.info.evil.jp/a.pdf", domains))


if __name__ == "__main__":
    unittest.main()
