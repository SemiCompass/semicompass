import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "factcheck"))
import bundle_read as br  # noqa: E402
import factcheck as fc  # noqa: E402
import run_pr  # noqa: E402

BODY = """## 概要
x

## 原資料束
1. `advantest-S100ABCD`（有価証券報告書）
2. `tel-S100EFGH`
3. `not valid id`

## 確認項目
`other-S1` は拾わない
"""


class FakeClient:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}


def bundle(text):
    return json.dumps({"sections": [{"text": text}, {"text": "売上高は1,500億円であった。"}]}, ensure_ascii=False).encode("utf-8")


class IdsTest(unittest.TestCase):
    def test_ids_are_taken_only_from_the_bundle_section(self):
        self.assertEqual(br.bundle_ids_from_body(BODY), ["advantest-S100ABCD", "tel-S100EFGH"])

    def test_no_section_or_empty_body(self):
        self.assertEqual(br.bundle_ids_from_body("概要だけ"), [])
        self.assertEqual(br.bundle_ids_from_body(""), [])

    def test_env_needs_all_four(self):
        full = {n: "x" for n in br.ENV_NAMES}
        self.assertIsNotNone(br.r2_env(full))
        full.pop("R2_BUCKET")
        self.assertIsNone(br.r2_env(full))


class ReadTest(unittest.TestCase):
    def test_read_and_report_failures_without_secrets(self):
        client = FakeClient({"bundles/a-S1.json": bundle("事業の内容")})
        texts, failed = br.read_bundles(client, "bucket", ["a-S1", "b-S2", "bad id"])
        self.assertEqual(len(texts), 1)
        self.assertIn("事業の内容", texts[0][1])
        self.assertEqual(len(failed), 2)
        self.assertTrue(all("bucket" not in f for f in failed))

    def test_bundle_text_is_used_as_a_source(self):
        texts, _ = br.read_bundles(FakeClient({"bundles/a-S1.json": bundle("x")}), "b", ["a-S1"])
        sources, failed = run_pr.gather({}, bundles=texts)
        self.assertEqual([s.id for s in sources], ["a-S1"])
        results = fc.check_claims("売上高は1,500億円だった。", sources, set(), set())
        self.assertEqual([r.result for r in results], [fc.GROUNDED])

    def test_unreadable_bundle_downgrades_unsupported_to_unverifiable(self):
        sources, failed = run_pr.gather({}, bundles=[], bundle_failed=["a-S1（KeyError）"])
        results = run_pr.check_file({}, "売上高は1,500億円だった。", set(), sources, failed)
        self.assertEqual([r.result for r in results], [fc.UNVERIFIABLE])


if __name__ == "__main__":
    unittest.main()
