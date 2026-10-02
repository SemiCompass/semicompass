import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "record_deploy.py"
spec = importlib.util.spec_from_file_location("record_deploy", MODULE_PATH)
record_deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(record_deploy)

COMMIT = "0123456789abcdef0123456789abcdef01234567"


class ReadVersionIdTest(unittest.TestCase):
    def write(self, lines):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "out.ndjson"
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        return path

    def test_reads_last_deploy_entry(self):
        path = self.write(
            [
                {"type": "wrangler-session", "version": 1},
                {"type": "deploy", "version": 1, "version_id": "old"},
                {"type": "deploy", "version": 1, "version_id": "new"},
            ]
        )
        self.assertEqual(record_deploy.read_version_id(path), "new")

    def test_ignores_other_entry_types(self):
        path = self.write(
            [{"type": "version-upload", "version_id": "x"}, {"type": "deploy", "version_id": "v1"}]
        )
        self.assertEqual(record_deploy.read_version_id(path), "v1")

    def test_missing_deploy_entry_fails(self):
        path = self.write([{"type": "wrangler-session"}])
        with self.assertRaises(ValueError):
            record_deploy.read_version_id(path)


class BuildRecordTest(unittest.TestCase):
    base = dict(
        at="2026-10-02T12:00:00+09:00",
        env="production",
        commit=COMMIT,
        deployment_id="v1",
        trigger="merge",
    )

    def test_key_order_follows_data_definition(self):
        record = record_deploy.build_record(**self.base, post_check="passed")
        self.assertEqual(
            list(record), ["at", "env", "commit", "deployment_id", "trigger", "post_check"]
        )

    def test_optional_fields_are_omitted(self):
        record = record_deploy.build_record(**self.base)
        self.assertNotIn("post_check", record)
        self.assertNotIn("rolled_back_to", record)

    def test_rollback_requires_rolled_back_to(self):
        with self.assertRaises(ValueError):
            record_deploy.build_record(**{**self.base, "trigger": "rollback"})
        record = record_deploy.build_record(
            **{**self.base, "trigger": "rollback"}, rolled_back_to="v0"
        )
        self.assertEqual(record["rolled_back_to"], "v0")

    def test_rejects_invalid_values(self):
        for override in (
            {"env": "preview"},
            {"commit": "abc"},
            {"trigger": "manual"},
        ):
            with self.assertRaises(ValueError):
                record_deploy.build_record(**{**self.base, **override})
        with self.assertRaises(ValueError):
            record_deploy.build_record(**self.base, post_check="unknown")


class MainTest(unittest.TestCase):
    def test_main_prints_one_json_line(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = record_deploy.main(
                ["--deployment-id", "v1", "--commit", COMMIT, "--trigger", "merge",
                 "--at", "2026-10-02T12:00:00+09:00"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())["deployment_id"], "v1")
        self.assertEqual(len(buffer.getvalue().splitlines()), 1)

    def test_main_fails_without_source(self):
        import contextlib
        import io

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                record_deploy.main(["--commit", COMMIT, "--trigger", "merge"]), 1
            )

    def test_now_jst_has_offset(self):
        self.assertTrue(record_deploy.now_jst().endswith("+09:00"))


if __name__ == "__main__":
    unittest.main()
