import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/factcheck"))
import factcheck as fc  # noqa: E402
import run_pr  # noqa: E402

FRONT = "---\ntitle: t\nsources:\n- id: S1\n  title: x\n  url: https://example.com/a\n---\n"
SRC = "架空製作所は2026年3月期の売上高を1,200億円と発表した。"


def sh(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / "config/operations.yaml").write_text("factcheck_paths:\n  - content/\n", encoding="utf-8")
        (self.root / "content").mkdir()
        sh(self.root, "init", "-q", "-b", "main")
        sh(self.root, "config", "user.email", "a@b.c")
        sh(self.root, "config", "user.name", "t")
        (self.root / "content/a.md").write_text(FRONT + "## 何が起きたか\n\n旧い行である。\n", encoding="utf-8")
        sh(self.root, "add", "-A")
        sh(self.root, "commit", "-qm", "base")
        self.base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, body):
        (self.root / "content/a.md").write_text(FRONT + body, encoding="utf-8")
        sh(self.root, "add", "-A")
        sh(self.root, "commit", "-qm", "head")
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()

    def go(self, head, fetch):
        return run_pr.run(self.base, head, root=self.root, fetch=fetch)


class RunTest(RepoCase):
    def test_grounded_passes(self):
        head = self.commit("## 何が起きたか\n\n旧い行である。\n\n売上高は1,200億円だった [S1]。\n")
        body, code, summary = self.go(head, lambda url: SRC)
        self.assertEqual(code, 0, body)
        self.assertEqual(summary["failures"], 0)

    def test_changed_number_fails_and_unchanged_lines_are_skipped(self):
        head = self.commit("## 何が起きたか\n\n旧い行である。\n\n売上高は1,500億円だった [S1]。\n")
        body, code, summary = self.go(head, lambda url: SRC)
        self.assertEqual(code, 1)
        self.assertIn("1,500億円", body)
        self.assertNotIn(SRC, body)  # 原資料の本文を出さない

    def test_fetch_failure_is_unverifiable_not_unsupported(self):
        head = self.commit("## 何が起きたか\n\n旧い行である。\n\n売上高は1,500億円だった [S1]。\n")

        def boom(url):
            raise OSError("x")
        body, code, _ = self.go(head, boom)
        self.assertEqual(code, 1)
        self.assertIn("確認不能", body)
        self.assertNotIn("根拠なし | ", body)
        self.assertIn("取得できなかった資料：S1（OSError）", body)

    def test_ack_clears_failure(self):
        head = self.commit("## 何が起きたか\n\n旧い行である。\n\n売上高は1,500億円だった [S1]。\n")
        _, _, _ = self.go(head, lambda url: SRC)
        front, _ = fc.split_front_matter((self.root / "content/a.md").read_text(encoding="utf-8"))
        results = fc.check_claims("売上高は1,500億円だった。", [fc.make_source("S1", SRC)], set(), set())
        acks = {fc.fingerprint(r.claim) for r in results}
        p = self.root / "acks.json"
        p.write_text(json.dumps({"acks": [{"fingerprint": a, "file": "content/a.md"} for a in acks]}), encoding="utf-8")
        body, code, _ = run_pr.run(self.base, head, acks_path=p, root=self.root, fetch=lambda url: SRC)
        self.assertEqual(code, 0, body)

    def test_no_body_change(self):
        (self.root / "content/a.md").write_text(FRONT.replace("title: t", "title: u") + "## 何が起きたか\n\n旧い行である。\n", encoding="utf-8")
        sh(self.root, "add", "-A")
        sh(self.root, "commit", "-qm", "h")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        body, code, _ = self.go(head, lambda url: SRC)
        self.assertEqual(code, 0)
        self.assertIn("対象なし", body)


class FetchTest(unittest.TestCase):
    def test_private_and_odd_urls_are_refused(self):
        for url in ("http://example.com/", "https://127.0.0.1/", "https://user:p@example.com/", "https://example.com:8443/", "file:///etc/passwd"):
            with self.assertRaises(ValueError, msg=url):
                run_pr.check_url_allowed(url)

    def test_private_resolution_is_refused(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 0))]):
            with self.assertRaises(ValueError):
                run_pr.check_url_allowed("https://example.com/")

    def test_html_text(self):
        text = run_pr.to_text("<html><script>var a=1200</script><p>売上高は1,200億円</p></html>".encode(), "text/html; charset=utf-8")
        self.assertIn("1,200億円", text)
        self.assertNotIn("var a", text)

    def test_sources_of_news(self):
        self.assertEqual(run_pr.sources_of({"source_article": {"url": "https://x.example/a"}}), [("S1", "https://x.example/a")])


if __name__ == "__main__":
    unittest.main()
