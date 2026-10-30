"""Vietnam time only: nothing the bot writes, parses or logs is UTC (docs/03 · Thời gian)."""
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from domain.clock import VN_TZ, now_vn, to_vn
from domain.models import run_id_of
from infrastructure.timeutil import iso, parse_ts

ROOT = Path(__file__).resolve().parents[1]


class ClockTest(unittest.TestCase):
    def test_offset_is_plus_seven(self):
        self.assertEqual(VN_TZ.utcoffset(None), timedelta(hours=7))
        self.assertEqual(now_vn().utcoffset(), timedelta(hours=7))

    def test_to_vn_keeps_the_instant(self):
        utc = datetime(2026, 10, 28, 0, 17, 12, tzinfo=timezone.utc)
        vn = to_vn(utc)
        self.assertEqual(vn, utc)
        self.assertEqual((vn.day, vn.hour, vn.minute), (28, 7, 17))

    def test_to_vn_crosses_midnight(self):
        utc = datetime(2026, 10, 27, 19, 0, tzinfo=timezone.utc)
        self.assertEqual(to_vn(utc).isoformat(), "2026-10-28T02:00:00+07:00")

    def test_naive_values_are_taken_as_vietnam_time(self):
        self.assertEqual(to_vn(datetime(2026, 10, 28, 7, 17)).isoformat(), "2026-10-28T07:17:00+07:00")


class SerialisationTest(unittest.TestCase):
    def test_iso_is_plus_seven(self):
        utc = datetime(2026, 10, 28, 0, 17, 12, tzinfo=timezone.utc)
        self.assertEqual(iso(utc), "2026-10-28T07:17:12+07:00")

    def test_parse_accepts_z_offsets_and_odd_fractions_and_returns_vn(self):
        cases = {
            "2026-10-27T19:00:00Z": "2026-10-28T02:00:00+07:00",
            "2026-10-28T00:17:12.12345+00:00": "2026-10-28T07:17:12.123450+07:00",
            "2026-10-28 07:17:12+07:00": "2026-10-28T07:17:12+07:00",
            "2026-10-28T00:17:12.1+00:00": "2026-10-28T07:17:12.100000+07:00",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_ts(raw).isoformat(), expected)
                self.assertEqual(parse_ts(raw).utcoffset(), timedelta(hours=7))

    def test_round_trip(self):
        t = datetime(2026, 10, 28, 7, 17, 12, tzinfo=VN_TZ)
        self.assertEqual(parse_ts(iso(t)), t)


class RunIdTest(unittest.TestCase):
    def test_run_id_is_vietnam_time_without_z(self):
        self.assertEqual(run_id_of(datetime(2026, 10, 28, 7, 17, 2, tzinfo=VN_TZ)), "run_20261028T071702")

    def test_run_id_from_a_utc_instant_is_still_vietnam_time(self):
        utc = datetime(2026, 10, 28, 0, 17, 2, tzinfo=timezone.utc)
        self.assertEqual(run_id_of(utc), "run_20261028T071702")

    def test_run_ids_sort_chronologically(self):
        a = run_id_of(datetime(2026, 10, 28, 7, 17, tzinfo=VN_TZ))
        b = run_id_of(datetime(2026, 10, 28, 18, 17, tzinfo=VN_TZ))
        self.assertLess(a, b)


class NoUtcInCodeTest(unittest.TestCase):
    def test_python_sources_never_build_utc_datetimes(self):
        offenders = []
        for layer in ("domain", "application", "infrastructure", "presentation"):
            for path in (ROOT / layer).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if re.search(r"timezone\.utc|utcnow|utcfromtimestamp", text):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
