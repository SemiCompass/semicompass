import unittest

import bundle_fakes as bf
import sections


class HtmlToTextTest(unittest.TestCase):
    def test_paragraphs_are_separated_by_newlines(self):
        self.assertEqual(sections.html_to_text("<p>あ</p><p>い</p>うえ<br/>お"), "あ\nい\nうえ\nお")

    def test_list_items_are_one_line_each(self):
        self.assertEqual(sections.html_to_text("<ul><li>一</li><li>二</li></ul>"), "一\n二")

    def test_table_rows_are_lines_and_cells_are_space_separated(self):
        html = "<table><tr><th>名前</th><th>値</th></tr><tr><td>甲</td><td>1,000</td></tr></table>"
        self.assertEqual(sections.html_to_text(html), "名前 値\n甲 1,000")

    def test_script_and_style_are_dropped(self):
        html = "<style>p{color:red}</style><p>本文</p><script>var x = '漏れ';</script>"
        self.assertEqual(sections.html_to_text(html), "本文")

    def test_text_after_unclosed_script_is_dropped_and_nested_depth_recovers(self):
        self.assertEqual(sections.html_to_text("<script>a</script>後<style>b</style>ろ"), "後ろ")

    def test_character_references_are_decoded(self):
        self.assertEqual(sections.html_to_text("<p>A&amp;B &lt;x&gt; &#12354; &nbsp;C</p>"), "A&B <x> あ C")

    def test_whitespace_is_collapsed_and_blank_lines_removed(self):
        self.assertEqual(sections.html_to_text("<p>  あ \n\t い  </p>\n\n<p> </p><div></div><p>う</p>"), "あ い\nう")

    def test_plain_text_and_empty_input(self):
        self.assertEqual(sections.html_to_text("ただの文"), "ただの文")
        self.assertEqual(sections.html_to_text(""), "")
        self.assertEqual(sections.html_to_text("<p> </p>"), "")

    def test_broken_html_does_not_raise(self):
        self.assertIn("本文", sections.html_to_text("<p>本文<b>太<i></p></div><td>"))

    def test_same_input_same_output(self):
        self.assertEqual(sections.html_to_text(bf.HTML_B), sections.html_to_text(bf.HTML_B))


class TextRowsTest(unittest.TestCase):
    def test_only_elements_ending_with_textblock(self):
        rows = sections.text_rows_from_csv(bf.csv_bytes())
        self.assertEqual([r.element_id for r in rows], [bf.ELEM_A, bf.ELEM_B])  # 数値、DEI、TextBlock以外、空は除く

    def test_row_fields(self):
        row = sections.text_rows_from_csv(bf.csv_bytes(), "x.csv")[0]
        self.assertEqual((row.label, row.context_id, row.file), ("節A（合成）", "FilingDateInstant", "x.csv"))
        self.assertEqual(row.text, f"{bf.WORD_A}　です。\n項目一\n項目二")
        self.assertEqual(row.chars, len(row.text))

    def test_missing_required_columns(self):
        data = bf.csv_bytes([["a", "b"]], header=["項目", "名前"])
        with self.assertRaises(ValueError):
            sections.text_rows_from_csv(data)

    def test_zip_reads_all_csvs_and_reports_unreadable_ones_without_text(self):
        import io
        import zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("a.csv", bf.csv_bytes())
            archive.writestr("b.csv", bf.csv_bytes([["x"]], header=["あ", "い"]))
            archive.writestr("c.txt", "not csv")
        rows, problems = sections.text_rows_from_zip(buffer.getvalue())
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.file for r in rows}, {"a.csv"})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("b.csv"))

    def test_bad_zip_is_value_error(self):
        with self.assertRaises(ValueError):
            sections.text_rows_from_zip(b"PKnot a zip")


if __name__ == "__main__":
    unittest.main()
