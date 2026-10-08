"""企業の表の指標（FR-309）の計算：営業利益率と平均年間給与（src/lib/metrics.ts を、Node.js で直接動かす）。"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAS_NODE = shutil.which("node") is not None


def run(expression: str, data):
    """metrics.ts の関数を、JSONの引数で呼ぶ。expression は (m, data) => 結果 の形の式。"""
    script = ("const data = JSON.parse(process.argv[1]);"
              "import('./src/lib/metrics.ts').then((m) => console.log(JSON.stringify((" + expression + ")(m, data))))")
    done = subprocess.run(["node", "-e", script, json.dumps(data)], cwd=ROOT, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr[-800:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def fin(end, sales, profit, kind="annual", standard="JGAAP"):
    return {"fiscal_period_end": end, "period_type": kind, "accounting_standard": standard,
            "net_sales": {"value": sales}, "operating_income": {"value": profit}}


def emp(end, yen, consolidated=None):
    row = {"fiscal_period_end": end, "non_consolidated": {"average_annual_salary": {"value": yen}}}
    if consolidated is not None:
        row["consolidated"] = {"employees": {"value": consolidated}}
    return row


def margin(rows):
    return run("(m, d) => m.operatingMargin(d)", rows)


def salary(rows):
    return run("(m, d) => m.averageSalary(d)", rows)


@unittest.skipUnless(HAS_NODE, "node がない")
class OperatingMarginTest(unittest.TestCase):
    def test_operating_income_divided_by_net_sales_in_percent(self):
        self.assertEqual(margin([fin("2026-03", 100000, 12345)]), 12.3)  # 12.345 → 12.3（小数第1位まで）
        self.assertEqual(margin([fin("2026-03", 1000000, 250000)]), 25.0)

    def test_rounds_half_up_and_symmetric_for_losses(self):
        self.assertEqual(margin([fin("2026-03", 2000, 1)]), 0.1)  # 0.05 → 0.1
        self.assertEqual(margin([fin("2026-03", 2000, -1)]), -0.1)  # 負の値は、絶対値を丸めて、符号を戻す
        self.assertEqual(margin([fin("2026-03", 3000, 1)]), 0.0)  # 0.033 → 0.0
        self.assertEqual(margin([fin("2026-03", 3000, 5)]), 0.2)  # 0.1666 → 0.2

    def test_a_loss_is_shown_as_is_and_zero_is_not_negative(self):
        self.assertEqual(margin([fin("2026-03", 361700, -1900)]), -0.5)
        self.assertEqual(margin([fin("2026-03", 1000000, -1)]), 0)
        self.assertEqual(run("(m, d) => Object.is(m.operatingMargin(d), -0)", [fin("2026-03", 1000000, -1)]), False)  # -0 を出さない
        self.assertEqual(margin([fin("2026-03", 1000, 0)]), 0)

    def test_null_when_operating_income_or_net_sales_is_missing(self):
        self.assertIsNone(margin([fin("2026-03", 100000, None)]))
        self.assertIsNone(margin([fin("2026-03", None, 500)]))
        self.assertIsNone(margin([{"fiscal_period_end": "2026-03", "period_type": "annual", "net_sales": {"value": 100}, "operating_income": {}}]))
        self.assertIsNone(margin([{"fiscal_period_end": "2026-03", "period_type": "annual", "net_sales": {"value": 100}}]))
        self.assertIsNone(margin([]))

    def test_null_when_net_sales_is_zero_or_negative(self):
        self.assertIsNone(margin([fin("2026-03", 0, 500)]))
        self.assertIsNone(margin([fin("2026-03", -100, 500)]))
        self.assertIsNone(margin([fin("2026-03", 0, 0)]))

    def test_ifrs_company_uses_its_operating_income_row(self):
        self.assertEqual(margin([fin("2026-03", 500000, 62500, standard="IFRS")]), 12.5)
        self.assertIsNone(margin([fin("2026-03", 500000, None, standard="IFRS")]))  # 営業利益が表示されないIFRSの会社は、「—」

    def test_holding_company_uses_the_consolidated_row_as_is(self):
        # 営業利益率は、全社の連結の数値（持株会社でも、連結の営業利益÷連結の売上高）
        self.assertEqual(margin([fin("2026-03", 8000000, 960000)]), 12.0)

    def test_latest_annual_row_is_chosen_regardless_of_order_and_half_year_rows_are_ignored(self):
        rows = [fin("2025-03", 100, 10), fin("2026-03", 100, 20), fin("2024-03", 100, 5),
                fin("2026-09", 100, 90, kind="half")]  # 半期の行は、新しくても選ばない
        self.assertEqual(margin(rows), 20.0)
        self.assertEqual(margin(list(reversed(rows))), 20.0)
        self.assertIsNone(margin([fin("2026-09", 100, 90, kind="half")]))  # 通期の行がなければ null

    def test_the_latest_annual_row_is_used_even_when_its_income_is_missing(self):
        rows = [fin("2025-03", 100, 10), fin("2026-03", 100, None)]
        self.assertIsNone(margin(rows))  # 古い期に、さかのぼらない

    def test_integer_rounding_has_no_floating_point_drift(self):
        # 5.05% は、浮動小数点では 5.049999… になりやすい。四捨五入で 5.1
        self.assertEqual(margin([fin("2026-03", 2000000, 101000)]), 5.1)
        self.assertEqual(margin([fin("2026-03", 4000000, 1000000)]), 25.0)


@unittest.skipUnless(HAS_NODE, "node がない")
class AverageSalaryTest(unittest.TestCase):
    def test_yen_to_man_yen_rounded_to_an_integer(self):
        self.assertEqual(salary([emp("2026-03", 6412000)]), 641)
        self.assertEqual(salary([emp("2026-03", 6415000)]), 642)  # 641.5 → 642（0.5は切り上げ）
        self.assertEqual(salary([emp("2026-03", 6414999)]), 641)
        self.assertEqual(salary([emp("2026-03", 10000)]), 1)
        self.assertEqual(salary([emp("2026-03", 5000)]), 1)
        self.assertEqual(salary([emp("2026-03", 4999)]), 0)

    def test_null_when_the_value_is_missing(self):
        self.assertIsNone(salary([emp("2026-03", None)]))
        self.assertIsNone(salary([{"fiscal_period_end": "2026-03", "non_consolidated": {}}]))
        self.assertIsNone(salary([{"fiscal_period_end": "2026-03", "non_consolidated": {"average_annual_salary": {}}}]))
        self.assertIsNone(salary([]))

    def test_the_latest_period_row_is_chosen_regardless_of_order(self):
        rows = [emp("2025-03", 6000000), emp("2026-03", 7000000), emp("2024-03", 5000000)]
        self.assertEqual(salary(rows), 700)
        self.assertEqual(salary(list(reversed(rows))), 700)

    def test_the_latest_row_is_used_even_when_its_value_is_missing(self):
        self.assertIsNone(salary([emp("2025-03", 6000000), emp("2026-03", None)]))  # 古い期に、さかのぼらない

    def test_only_the_filing_company_figure_is_used_for_a_holding_company(self):
        # 提出会社（non_consolidated）の値を使う。連結の従業員数などの項目があっても、平均年間給与には使わない
        rows = [emp("2026-03", 9990000, consolidated=30000)]
        self.assertEqual(salary(rows), 999)
        self.assertIsNone(salary([{"fiscal_period_end": "2026-03", "consolidated": {"employees": {"value": 30000}},
                                   "non_consolidated": {"employees": {"value": 40}}}]))  # 提出会社の給与がなければ、連結の値で補わない


@unittest.skipUnless(HAS_NODE, "node がない")
class RoundingTest(unittest.TestCase):
    def test_round_half_up(self):
        self.assertEqual(run("(m) => [m.roundHalfUp(5, 10), m.roundHalfUp(4, 10), m.roundHalfUp(15, 10), m.roundHalfUp(0, 7)]", None), [1, 0, 2, 0])


if __name__ == "__main__":
    unittest.main()
