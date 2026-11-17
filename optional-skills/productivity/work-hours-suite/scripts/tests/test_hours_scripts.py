#!/usr/bin/env python3
"""Regression tests for the worked-hours scripts.

Run with the Hermes venv:
  ~/.hermes/hermes-agent/venv/bin/python -m unittest discover \
      -s ~/.hermes/scripts/tests -v
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

SCRIPTS = os.path.expanduser("~/.hermes/scripts")
sys.path.insert(0, SCRIPTS)

import fill_hours as fh  # noqa: E402
import fill_hours_alert as alert  # noqa: E402


def _ms(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute,
                        tzinfo=fh.LOCAL_TZ).timestamp() * 1000)


class TopTrackerReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "TopTracker.db"
        self.user = "test@example.com"
        self.table = '"%s_activity"' % self.user
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE %s (id INTEGER PRIMARY KEY, startTime INTEGER, "
            "endTime INTEGER, projectId INTEGER)" % self.table
        )
        conn.commit()
        conn.close()
        self.patches = [
            mock.patch.object(fh, "TOPTRACKER_DB", self.db),
            mock.patch.object(fh, "TOPTRACKER_USER", self.user),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def add(self, start, end, project=1182888):
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO %s (startTime, endTime, projectId) VALUES (?,?,?)"
            % self.table, (start, end, project)
        )
        conn.commit()
        conn.close()

    def test_only_closed_mtmpro_counts(self):
        self.add(_ms(2026, 10, 28, 10), _ms(2026, 10, 28, 11), 1182888)
        self.add(_ms(2026, 10, 28, 12), _ms(2026, 10, 28, 14), 1183966)
        self.add(_ms(2026, 10, 28, 15), None, 1182888)
        self.assertEqual(fh.read_toptracker_hours(date(2026, 10, 28)), 1.0)

    def test_broadcasting_only_is_unknown(self):
        self.add(_ms(2026, 10, 28, 12), _ms(2026, 10, 28, 14), 1183966)
        self.assertIsNone(fh.read_toptracker_hours(date(2026, 10, 28)))

    def test_running_only_is_unknown(self):
        self.add(_ms(2026, 10, 28, 15), None, 1182888)
        self.assertIsNone(fh.read_toptracker_hours(date(2026, 10, 28)))

    def test_cross_midnight_start_day(self):
        self.add(_ms(2026, 10, 28, 23, 30), _ms(2026, 10, 29, 1, 53), 1182888)
        self.assertEqual(fh.read_toptracker_hours(date(2026, 10, 28)), 2.38)
        self.assertIsNone(fh.read_toptracker_hours(date(2026, 10, 29)))

    def test_after_midnight_belongs_to_next_day(self):
        self.add(_ms(2026, 10, 29, 0, 30), _ms(2026, 10, 29, 1, 0), 1182888)
        self.assertIsNone(fh.read_toptracker_hours(date(2026, 10, 28)))
        self.assertEqual(fh.read_toptracker_hours(date(2026, 10, 29)), 0.5)


class KimaiSplitTests(unittest.TestCase):
    def test_same_day_and_cross_midnight(self):
        entries = [
            {"begin": "2026-10-28T10:00:00+0500",
             "end": "2026-10-28T12:00:00+0500", "duration": 7200},
            {"begin": "2026-10-28T23:30:00+0500",
             "end": "2026-10-29T01:53:00+0500", "duration": 8580},
        ]
        with mock.patch.object(fh, "_kimai_entries", return_value=entries):
            self.assertEqual(fh.expected_gmi(date(2026, 10, 28)), 2.5)
            self.assertEqual(fh.expected_gmi(date(2026, 10, 29)), 1.88)

    def test_running_entry_is_unknown_and_excluded(self):
        entries = [
            {"begin": "2026-10-28T10:00:00+0500", "end": None, "duration": 0},
        ]
        with mock.patch.object(fh, "_kimai_entries", return_value=entries):
            self.assertEqual(fh.expected_gmi(date(2026, 10, 28)), 0.0)

    def test_empty_day_is_zero(self):
        with mock.patch.object(fh, "_kimai_entries", return_value=[]):
            self.assertEqual(fh.expected_gmi(date(2026, 10, 28)), 0.0)

    def test_timestamp_offsets_are_converted_to_pkt(self):
        self.assertEqual(fh._parse_local("2026-10-28T23:30:00+0500"),
                         datetime(2026, 10, 28, 23, 30))
        self.assertEqual(fh._parse_local("2026-10-28T18:30:00+0000"),
                         datetime(2026, 10, 28, 23, 30))
        self.assertEqual(fh._parse_local("2026-10-28T18:30:00Z"),
                         datetime(2026, 10, 28, 23, 30))


class AlertTests(unittest.TestCase):
    def base(self):
        return {
            "date": "2026-10-28",
            "toptracker": 2.38,
            "verified": True,
            "notes": [],
            "summary": {"verified": True, "refreshed": True},
        }

    def test_clean_result_is_silent(self):
        self.assertEqual(alert.collect_problems(self.base()), [])

    def test_c_stale_alerts(self):
        d = self.base()
        d["notes"] = ["C: STALE 0.42 vs tracker 2.38 (1.96h missing) - pass --force or confirm"]
        self.assertTrue(alert.collect_problems(d))

    def test_c_zero_read_alerts(self):
        d = self.base()
        d["notes"] = ["C: tracker reads 0 but cell holds 2.38 - kept (never clear on a zero read)"]
        self.assertTrue(alert.collect_problems(d))

    def test_h_stale_is_not_alerted_because_it_auto_repairs(self):
        d = self.base()
        d["notes"] = ["H: STALE 6.20 -> 6.93 (closed Kimai entries added; 0.73h missing)"]
        self.assertEqual(alert.collect_problems(d), [])

    def test_verification_failure_alerts(self):
        d = self.base()
        d["verified"] = False
        d["verification_errors"] = ["H: planned 6.93, read back 6.20"]
        self.assertTrue(alert.collect_problems(d))

    def test_skipped_alerts(self):
        d = self.base()
        d["skipped"] = True
        d["reason"] = "date is in the future"
        self.assertTrue(alert.collect_problems(d))

    def test_summary_refresh_failure_alerts(self):
        d = self.base()
        d["summary"] = {"refreshed": False, "reason": "weekly block not found"}
        self.assertTrue(alert.collect_problems(d))


if __name__ == "__main__":
    unittest.main()
