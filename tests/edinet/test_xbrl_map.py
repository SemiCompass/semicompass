import copy
import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "xbrl-map.yaml"
SCHEMA = ROOT / "schemas" / "config" / "xbrl-map.schema.json"

try:
    from jsonschema import Draft202012Validator
except ImportError:  # scripts/requirements.txt の jsonschema を入れていない環境
    Draft202012Validator = None


@unittest.skipIf(Draft202012Validator is None, "jsonschema がない（scripts/requirements.txt）")
class XbrlMapSchemaTest(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(self.schema)

    def errors(self, data):
        return list(self.validator.iter_errors(data))

    def test_schema_itself_is_valid(self):
        Draft202012Validator.check_schema(self.schema)

    def test_config_passes_the_schema(self):
        self.assertEqual([e.message for e in self.errors(self.data)], [])

    def test_doc_types_are_the_four_codes_as_strings(self):
        self.assertEqual(self.data["doc_types"], {
            "120": "annual_report", "130": "amended_annual_report",
            "160": "semiannual_report", "170": "amended_semiannual_report"})
        self.assertTrue(all(isinstance(k, str) for k in self.data["doc_types"]))

    def test_unconfirmed_notice_is_at_the_top_of_the_file(self):
        head = "\n".join(CONFIG.read_text(encoding="utf-8").splitlines()[:12])
        self.assertIn("未確認。段階2で実際の書類で確かめる", head)

    def test_ifrs_and_usgaap_have_no_ordinary_income(self):
        for standard in ("ifrs", "usgaap"):
            self.assertIn("ordinary_income", self.data["standards"][standard]["expected_absent"])
            self.assertNotIn("ordinary_income", self.data["standards"][standard]["items"])
        self.assertIn("ordinary_income", self.data["standards"]["jgaap"]["items"])

    def test_schema_rejects_bad_configs(self):
        bad = copy.deepcopy(self.data)
        bad["doc_types"]["999"] = "unknown"
        self.assertTrue(self.errors(bad))
        bad = copy.deepcopy(self.data)
        del bad["standards"]["ifrs"]
        self.assertTrue(self.errors(bad))
        bad = copy.deepcopy(self.data)
        bad["employees"]["average_age"] = []
        self.assertTrue(self.errors(bad))
        bad = copy.deepcopy(self.data)
        bad["unknown_key"] = 1
        self.assertTrue(self.errors(bad))


if __name__ == "__main__":
    unittest.main()
