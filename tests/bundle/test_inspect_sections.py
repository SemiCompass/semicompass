import contextlib
import io
import os
import unittest
from unittest import mock

import bundle_fakes as bf
import inspect_sections as ins
from bundle_fakes import KEY, Clock


def run(argv, server, env_key=KEY):
    clock = Clock()
    out, err = io.StringIO(), io.StringIO()
    env = {"EDINET_API_KEY": env_key} if env_key else {}
    with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ins.main(argv, open_url=server, sleep=clock.sleep, monotonic=clock.monotonic)
    return code, out.getvalue(), err.getvalue()


class InspectSectionsTest(unittest.TestCase):
    def test_lists_element_ids_labels_and_char_counts(self):
        code, out, _ = run(["--doc-id", bf.DOC_ID], bf.DocServer())
        self.assertEqual(code, 0)
        for text in (bf.ELEM_A, bf.ELEM_B, "節A（合成）", "節B（合成）"):
            self.assertIn(text, out)
        self.assertNotIn(bf.ELEM_C, out)  # 空の節は出ない
        self.assertNotIn("NotTextBlockElement", out)
        self.assertIn("文章の行 2件", out)

    def test_never_prints_body_text(self):
        code, out, err = run(["--doc-id", bf.DOC_ID], bf.DocServer())
        for fragment in (bf.WORD_A, bf.WORD_B, "ゼータ", "イータ", "項目一", "見出し", "記号", "対象外の文章"):
            self.assertNotIn(fragment, out + err)

    def test_no_text_rows_is_not_a_failure(self):
        code, out, _ = run(["--doc-id", bf.DOC_ID], bf.DocServer(bf.make_zip([bf.BASE_ROWS[1]])))
        self.assertEqual(code, 0)
        self.assertIn("文章の行 0件", out)

    def test_unreadable_csv_is_reported_without_body(self):
        import io as _io
        import zipfile
        buffer = _io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("ok.csv", bf.csv_bytes())
            archive.writestr("bad.csv", bf.csv_bytes([["x", "y"]], header=["あ", "い"]))
        code, out, err = run(["--doc-id", bf.DOC_ID], bf.DocServer(buffer.getvalue()))
        self.assertEqual(code, 1)
        self.assertIn("bad.csv", out)
        self.assertNotIn(bf.WORD_A, out + err)

    def test_max_requests_exceeded_makes_no_request(self):
        server = bf.DocServer()
        code, _, err = run(["--doc-id", "S100AAAA", "--doc-id", "S100BBBB", "--doc-id", "S100CCCC",
                            "--max-requests", "2"], server)
        self.assertEqual(code, 2)
        self.assertEqual(server.requests, [])
        self.assertIn("--max-requests", err)

    def test_default_max_requests_is_10(self):
        self.assertEqual(ins.parse_args(["--doc-id", "S100AAAA"]).max_requests, 10)

    def test_invalid_doc_id_and_missing_key(self):
        server = bf.DocServer()
        self.assertEqual(run(["--doc-id", "bad"], server)[0], 2)
        self.assertEqual(run(["--doc-id", bf.DOC_ID], server, env_key="")[0], 2)
        self.assertEqual(server.requests, [])

    def test_key_is_not_printed(self):
        server = bf.DocServer(b"<html>x</html>")
        code, out, err = run(["--doc-id", bf.DOC_ID], server)
        self.assertEqual(code, 1)
        self.assertNotIn(KEY, out + err)

    def test_duplicate_doc_ids_are_fetched_once(self):
        server = bf.DocServer()
        run(["--doc-id", bf.DOC_ID, "--doc-id", bf.DOC_ID], server)
        self.assertEqual(len(server.requests), 1)

    def test_writes_no_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                run(["--doc-id", bf.DOC_ID], bf.DocServer())
                self.assertEqual(os.listdir(tmp), [])
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
