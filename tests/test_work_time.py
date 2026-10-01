from datetime import datetime, timedelta
from unittest.mock import patch
import unittest

import test_watch_integration as integration
from operations_api import storage


class WorkTimeTest(unittest.TestCase):
    setUp = integration.WatchIntegrationTest.setUp
    tearDown = integration.WatchIntegrationTest.tearDown
    post = integration.WatchIntegrationTest.post
    workers = integration.WatchIntegrationTest.workers
    def event(self, action, timestamp):
        self.post('attendance', {'worker_id': 'worker-1', 'action': action,
                                 'occurred_at': timestamp})

    def at(self, timestamp):
        return storage.get_work_time_today('worker-1', datetime.fromisoformat(timestamp))

    def test_live_break_resume_and_closed_session(self):
        self.event('CLOCK_IN', '2026-09-30T08:00:00+09:00')
        self.assertEqual(self.at('2026-09-30T09:00:00+09:00')['worked_minutes_today'], 60)
        self.assertEqual(self.at('2026-09-30T10:00:00+09:00')['worked_minutes_today'], 120)
        self.event('BREAK_START', '2026-09-30T10:00:00+09:00')
        self.assertEqual(self.at('2026-09-30T10:30:00+09:00')['worked_minutes_today'], 120)
        self.assertEqual(self.at('2026-09-30T11:00:00+09:00')['worked_minutes_today'], 120)
        self.event('BREAK_END', '2026-09-30T11:00:00+09:00')
        self.assertEqual(self.at('2026-09-30T12:00:00+09:00')['worked_minutes_today'], 180)
        self.event('CLOCK_OUT', '2026-09-30T12:00:00+09:00')
        self.assertEqual(self.at('2026-09-30T18:00:00+09:00')['worked_minutes_today'], 180)

    def test_multiple_sessions_and_threshold_boundaries(self):
        self.event('CLOCK_IN', '2026-09-30T00:00:00+09:00')
        self.event('CLOCK_OUT', '2026-09-30T01:00:00+09:00')
        self.event('CLOCK_IN', '2026-09-30T02:00:00+09:00')
        for minutes, expected in [(479, 'NORMAL'), (480, 'WARNING'), (539, 'WARNING'), (540, 'EXCEEDED')]:
            now = datetime.fromisoformat('2026-09-30T02:00:00+09:00') + timedelta(minutes=minutes - 60)
            result = storage.get_work_time_today('worker-1', now)
            self.assertEqual(result['worked_minutes_today'], minutes)
            self.assertEqual(result['work_time_status'], expected)

    def test_overnight_breaks_and_korean_day_boundary(self):
        self.event('CLOCK_IN', '2026-09-29T22:00:00+09:00')
        self.event('BREAK_START', '2026-09-29T23:30:00+09:00')
        self.assertEqual(self.at('2026-09-30T00:15:00+09:00')['worked_minutes_today'], 0)
        self.event('BREAK_END', '2026-09-30T00:30:00+09:00')
        self.event('CLOCK_OUT', '2026-09-30T02:00:00+09:00')
        self.assertEqual(self.at('2026-09-30T03:00:00+09:00')['worked_minutes_today'], 90)
        self.assertEqual(self.at('2026-10-01T03:00:00+09:00')['worked_minutes_today'], 0)

    def test_clock_out_while_on_break(self):
        self.event('CLOCK_IN', '2026-09-30T08:00:00+09:00')
        self.event('BREAK_START', '2026-09-30T09:00:00+09:00')
        self.event('CLOCK_OUT', '2026-09-30T10:00:00+09:00')
        self.assertEqual(self.at('2026-09-30T12:00:00+09:00')['worked_minutes_today'], 60)

    def test_legacy_migration_preserves_rows_and_marks_unknown_overnight_breaks(self):
        with storage._connect() as db:
            db.execute('ALTER TABLE work_sessions DROP COLUMN break_intervals')
            db.execute("INSERT INTO work_sessions(worker_id, clock_in, clock_out, total_break_seconds) "
                       "VALUES ('worker-1', '2026-09-29T13:00:00Z', '2026-09-29T17:00:00Z', 3600)")
        db.close()
        storage.initialize_database()
        storage.initialize_database()  # idempotent migration
        row = self.at('2026-09-30T03:00:00+09:00')
        self.assertIsNone(row['worked_minutes_today'])
        self.assertFalse(row['work_time_complete'])
        self.assertEqual(row['work_time_status'], 'WARNING')
        self.assertEqual(storage.get_worker_status('worker-1')['worked_minutes'], 180)

    def test_dashboard_includes_today_and_keeps_existing_fields(self):
        self.event('CLOCK_IN', '2026-09-30T08:00:00+09:00')
        with patch('operations_api.storage.datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat('2026-09-30T16:42:00+09:00')
            row = self.workers()['worker-1']
        self.assertEqual(row['worked_minutes_today'], 522)
        self.assertEqual(row['work_time_status'], 'WARNING')
        self.assertEqual(row['work_state'], 'WORKING')
        self.assertIsNone(row['heart_rate'])

    def test_legacy_same_day_break_total_remains_usable(self):
        with storage._connect() as db:
            db.execute("INSERT INTO work_sessions(worker_id, clock_in, clock_out, total_break_seconds) "
                       "VALUES ('worker-1', '2026-09-30T00:00:00Z', '2026-09-30T03:00:00Z', 3600)")
        db.close()
        row = self.at('2026-09-30T18:00:00+09:00')
        self.assertEqual(row['worked_minutes_today'], 120)
        self.assertTrue(row['work_time_complete'])

    def test_seconds_snapshot_reentry_and_day_reset(self):
        self.event('CLOCK_IN', '2026-09-30T09:00:00+09:00')
        self.event('CLOCK_OUT', '2026-09-30T10:00:00+09:00')
        self.event('CLOCK_IN', '2026-09-30T13:00:00+09:00')
        row = self.at('2026-09-30T14:00:03+09:00')
        self.assertEqual(row['worked_seconds_today'], 7203)
        self.assertEqual(row['clock_in_at'], '2026-09-30T04:00:00Z')
        self.assertEqual(row['completed_work_seconds_today'], 3600)
        self.assertEqual(row['current_break_seconds_today'], 0)
        self.assertEqual(row['work_date'], '2026-09-30')
        self.assertEqual(row['work_time_calculated_at'], '2026-09-30T05:00:03Z')
        self.assertEqual(row['active_work_started_at'], '2026-09-30T04:00:00Z')
        row = self.at('2026-10-01T00:00:00+09:00')
        self.assertEqual(row['worked_seconds_today'], 0)
        self.assertEqual(row['active_work_started_at'], '2026-09-30T15:00:00Z')
        self.assertEqual(self.at('2026-10-01T00:00:07+09:00')['worked_seconds_today'], 7)
        self.event('CLOCK_OUT', '2026-10-01T00:00:10+09:00')
        row = self.at('2026-10-01T02:00:00+09:00')
        self.assertEqual(row['worked_seconds_today'], 10)
        self.assertIsNone(row['active_work_started_at'])
        self.assertIsNone(row['clock_in_at'])
        self.assertEqual(row['completed_work_seconds_today'], 10)

    def test_seconds_snapshot_paused_during_break(self):
        self.event('CLOCK_IN', '2026-09-30T09:00:00+09:00')
        self.event('BREAK_START', '2026-09-30T09:01:05+09:00')
        row = self.at('2026-09-30T10:00:00+09:00')
        self.assertEqual(row['worked_seconds_today'], 65)
        self.assertIsNone(row['active_work_started_at'])
        self.event('BREAK_END', '2026-09-30T10:00:00+09:00')
        row = self.at('2026-09-30T10:00:05+09:00')
        self.assertEqual(row['worked_seconds_today'], 70)
        self.assertEqual(row['current_break_seconds_today'], 3535)
