"""Run with: python -m unittest discover -s tests -v (requires httpx)."""
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from operations_api import storage
from operations_api.router import router


class WatchIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_path = storage.DATABASE_PATH
        storage.DATABASE_PATH = Path(self.temp.name) / 'watch.db'
        storage.initialize_database()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        storage.DATABASE_PATH = self.previous_path
        self.temp.cleanup()

    def post(self, path, payload):
        response = self.client.post('/api/watch/' + path, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def workers(self):
        response = self.client.get('/api/dashboard/workers')
        self.assertEqual(response.status_code, 200)
        return {row['worker_id']: row for row in response.json()['workers']}

    def attendance(self, action, minute):
        return self.post('attendance', {'worker_id': 'worker-1', 'action': action,
            'occurred_at': f'2026-09-30T01:{minute:02d}:00Z'})

    def heart_rate(self, worker, rate, minute):
        return self.post('heart-rate', {'worker_id': worker, 'heart_rate': rate,
            'measured_at': f'2026-09-30T01:{minute:02d}:00Z'})

    def test_clock_in_heart_rate_clock_out_and_persistence(self):
        self.assertEqual(self.workers(), {})
        self.attendance('CLOCK_IN', 0)
        row = self.workers()['worker-1']
        self.assertEqual(row['work_state'], 'WORKING')
        self.assertIsNone(row['heart_rate'])
        self.assertIsNone(row['measured_at'])
        self.heart_rate('worker-1', 92, 1)
        self.heart_rate('worker-1', 98, 2)
        self.heart_rate('worker-1', 80, 1)  # delayed older sample
        self.assertEqual(self.workers()['worker-1']['heart_rate'], 98)
        self.attendance('CLOCK_OUT', 3)
        row = self.workers()['worker-1']
        self.assertEqual(row['work_state'], 'OFF_WORK')
        self.assertEqual(row['heart_rate'], 98)
        self.assertEqual(row['measured_at'], '2026-09-30T01:02:00Z')
        with closing(sqlite3.connect(storage.DATABASE_PATH)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM heart_rates').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT clock_out FROM work_sessions').fetchone()[0],
                             '2026-09-30T01:03:00Z')

    def test_attendance_only_and_heart_rate_only_workers(self):
        self.attendance('CLOCK_IN', 0)
        self.attendance('CLOCK_OUT', 1)
        self.heart_rate('worker-2', 75, 2)
        rows = self.workers()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows['worker-1']['work_state'], 'OFF_WORK')
        self.assertIsNone(rows['worker-1']['heart_rate'])
        self.assertEqual(rows['worker-2']['work_state'], 'BEFORE_WORK')
        self.assertEqual(rows['worker-2']['heart_rate'], 75)

    def test_breaks_and_invalid_transitions_are_preserved(self):
        self.attendance('CLOCK_IN', 0)
        response = self.client.post('/api/watch/attendance', json={
            'worker_id': 'worker-1', 'action': 'CLOCK_IN', 'occurred_at': '2026-09-30T01:00:00Z'})
        self.assertEqual(response.status_code, 400)
        self.attendance('BREAK_START', 1)
        self.assertEqual(self.workers()['worker-1']['work_state'], 'ON_BREAK')
        self.attendance('BREAK_END', 2)
        self.assertEqual(self.workers()['worker-1']['work_state'], 'WORKING')
        self.attendance('CLOCK_OUT', 3)
        self.assertEqual(self.workers()['worker-1']['worked_minutes'], 2)


if __name__ == '__main__':
    unittest.main()
