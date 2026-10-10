"""固定ページ（content/pages/）の確認。形、フッターとの対応、リンク、運営者の記入の残り（下書きのうちだけ許す）。"""
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "content" / "pages"
AUTO_ROUTES = {"/corrections/", "/", "/news/", "/companies/", "/processes/", "/glossary/", "/search/"}  # 自動で作るページ・一覧


def load():
    out = {}
    for f in sorted(PAGES.glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", f.read_text(encoding="utf-8"), re.S)
        out[f.name] = (yaml.safe_load(m[1]), m[2])
    return out


class PagesTest(unittest.TestCase):
    def test_front_matter(self):
        for name, (front, _body) in load().items():
            for key in ("title", "description", "path", "updated_at"):
                self.assertTrue(front.get(key), f"{name}: {key}")
            self.assertRegex(front["path"], r"^/[a-z0-9/-]*/$", name)

    def test_every_footer_link_has_a_page(self):
        menu = yaml.safe_load((ROOT / "config" / "menu.yaml").read_text(encoding="utf-8"))
        paths = {front["path"] for front, _ in load().values()}
        for group in menu["footer"]:
            for link in group["links"]:
                self.assertTrue(link["path"] in paths or link["path"] in AUTO_ROUTES, f"フッターのリンク先がない: {link['path']}")  # FP-09

    def test_internal_links_point_to_existing_pages(self):
        paths = {front["path"] for front, _ in load().values()} | AUTO_ROUTES
        for name, (_front, body) in load().items():
            for target in re.findall(r"\]\((/[a-z0-9/#-]*)\)", body):
                self.assertIn(target.split("#")[0] or "/", paths, f"{name}: {target}")

    def test_operator_blanks_only_in_drafts(self):
        for name, (front, body) in load().items():
            if "【運営者が" in body:
                self.assertTrue(front.get("draft") is True, f"{name}: 運営者の記入欄が残ったまま、draft: true でない")

    def test_faq_questions_have_ids(self):
        _front, body = load()["faq.md"]
        questions = re.findall(r"^### (.+)$", body, re.M)
        self.assertGreaterEqual(len(questions), 8)
        for q in questions:
            self.assertRegex(q, r"\{#[a-z0-9-]+\}$", q)  # FP-10：固定の識別名

    def test_policy_states_the_correction_deadlines(self):
        _f, body = load()["policy.md"]
        for needle in ("1営業日以内", "5営業日以内", "14日以内", "休止"):
            self.assertIn(needle, body)  # 運用ルール書・要求定義書 6.10 と同じ値

    def test_contact_states_reply_guideline(self):
        _f, body = load()["contact.md"]
        self.assertIn("5営業日程度", body)  # FP-08、運用ルール書 11.2


class SiteConfigTest(unittest.TestCase):
    def test_contact_form_url_is_empty_or_google_forms(self):
        data = yaml.safe_load((ROOT / "config" / "site.yaml").read_text(encoding="utf-8"))
        url = data["contact_form_url"]
        self.assertTrue(url == "" or re.match(r"^https://(docs\.google\.com/forms|forms\.gle)/", url))


if __name__ == "__main__":
    unittest.main()
