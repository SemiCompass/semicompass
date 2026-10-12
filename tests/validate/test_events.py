"""技術系のイベント（data/events.yaml。データ定義書 4.6、V-22、V-23）の検査のテスト。"""
import sys
import unittest
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_validate_data import Base, vd  # noqa: E402


def event(**kw):
    base = {"id": "semicon-japan-2099", "name": "SEMICON Japan", "kind": "exhibition", "start_date": "2099-12-09",
            "end_date": "2099-12-11", "venue": "東京ビッグサイト", "city": "東京都江東区", "organizer": "SEMI",
            "url": "https://semiconjapan.org/", "source": "S1", "checked_on": "2099-01-10"}
    return {**base, **kw}


class EventsTest(Base):
    def write(self, *events):
        data = {"schema_version": 1, "sources": [{"id": "S1", "title": "公式", "publisher": "SEMI", "url": "https://semiconjapan.org/",
                                                   "accessed_on": "2099-01-10"}], "events": list(events)}
        (self.root / "data" / "events.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def problems(self, today="2099-01-15"):
        return [p for p in self.check(today=date.fromisoformat(today)) if p.file == "data/events.yaml"]

    def test_valid(self):
        self.write(event())
        self.assertEqual([p for p in self.problems() if p.severity == "error"], [])

    def test_end_before_start_duplicate_id_and_http(self):
        self.write(event(end_date="2099-12-01"), event(), event(id="other", url="http://example.org/"))
        problems = self.problems()
        self.has(problems, "V-22", "end_date")
        self.has(problems, "V-22", "重複")
        self.has(problems, "V-01", file="data/events.yaml")

    def test_recheck_warning_after_ninety_days_before(self):
        self.write(event())
        self.assertFalse([p for p in self.problems("2099-08-01") if p.rule == "V-23"])  # まだ90日前より前
        self.has(self.problems("2099-10-01"), "V-23", "90日前")

    def test_unknown_source(self):
        self.write(event(source="S9"))
        self.has(self.problems(), "V-07", "S9")


if __name__ == "__main__":
    unittest.main()
