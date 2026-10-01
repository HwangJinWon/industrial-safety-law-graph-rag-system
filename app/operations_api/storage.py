"""Persistent SQLite storage used only by the operations API."""

from __future__ import annotations

import sqlite3
import os
import json
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(
    os.environ.get("WATCH_DATABASE_PATH") or str(PROJECT_ROOT / "data" / "watch_data.db")
).expanduser().resolve()

# Operational review triggers, not legal limits. Korea calendar day (UTC+09:00).
WORK_DAY_TIMEZONE = timezone(timedelta(hours=9))
WORK_TIME_WARNING_MINUTES = 480
WORK_TIME_EXCEEDED_MINUTES = 540


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def normalize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS heart_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id TEXT NOT NULL,
                heart_rate INTEGER NOT NULL,
                measured_at TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_heart_rates_worker_time
            ON heart_rates(worker_id, measured_at DESC);

            CREATE TABLE IF NOT EXISTS emergency_alerts (
                alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_emergency_alerts_time
            ON emergency_alerts(occurred_at DESC);

            CREATE TABLE IF NOT EXISTS alert_acknowledgements (
                alert_id INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                acknowledged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (alert_id, worker_id),
                FOREIGN KEY (alert_id) REFERENCES emergency_alerts(alert_id)
            );

            CREATE TABLE IF NOT EXISTS equipment_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id TEXT NOT NULL,
                status TEXT NOT NULL,
                production_count INTEGER NOT NULL,
                defect_rate REAL NOT NULL,
                measured_at TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_equipment_status_latest
            ON equipment_status(equipment_id, measured_at DESC);

            CREATE TABLE IF NOT EXISTS work_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id TEXT NOT NULL,
                clock_in TEXT NOT NULL,
                break_started_at TEXT,
                total_break_seconds INTEGER NOT NULL DEFAULT 0,
                clock_out TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_work_sessions_worker
            ON work_sessions(worker_id, session_id DESC);
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(work_sessions)")}
        if "break_intervals" not in columns:
            # NULL marks legacy sessions whose completed break intervals are unknown.
            connection.execute("ALTER TABLE work_sessions ADD COLUMN break_intervals TEXT")
        connection.commit()

def save_heart_rate(worker_id: str, heart_rate: int, measured_at: datetime) -> None:
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT INTO heart_rates(worker_id, heart_rate, measured_at) VALUES (?, ?, ?)",
            (worker_id, heart_rate, normalize_datetime(measured_at)),
        )
        connection.commit()


def save_emergency(worker_id: str, alert_type: str, message: str, occurred_at: datetime) -> int:
    with closing(_connect()) as connection:
        cursor = connection.execute(
            "INSERT INTO emergency_alerts(worker_id, type, message, occurred_at) VALUES (?, ?, ?, ?)",
            (worker_id, alert_type, message, normalize_datetime(occurred_at)),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_latest_workers() -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            WITH workers AS (
                SELECT worker_id FROM heart_rates
                UNION
                SELECT worker_id FROM work_sessions
            ), latest_rates AS (
                SELECT worker_id, heart_rate, measured_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY worker_id ORDER BY measured_at DESC, id DESC
                       ) AS row_number
                FROM heart_rates
            )
            SELECT workers.worker_id, latest_rates.heart_rate, latest_rates.measured_at
            FROM workers
            LEFT JOIN latest_rates
              ON latest_rates.worker_id = workers.worker_id AND latest_rates.row_number = 1
            ORDER BY workers.worker_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_recent_alerts(limit: int = 100) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT alert_id, worker_id, type, message, occurred_at
            FROM emergency_alerts
            ORDER BY occurred_at DESC, alert_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_equipment_status(
    equipment_id: str,
    status: str,
    production_count: int,
    defect_rate: float,
    measured_at: datetime,
) -> None:
    with closing(_connect()) as connection:
        connection.execute(
            """
            INSERT INTO equipment_status(
                equipment_id, status, production_count, defect_rate, measured_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (equipment_id, status, production_count, defect_rate, normalize_datetime(measured_at)),
        )
        connection.commit()


def list_latest_equipment() -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT equipment_id, status, production_count, defect_rate, measured_at
            FROM (
                SELECT equipment_id, status, production_count, defect_rate, measured_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY equipment_id ORDER BY measured_at DESC, id DESC
                       ) AS row_number
                FROM equipment_status
            )
            WHERE row_number = 1
            ORDER BY equipment_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _session_result(row: sqlite3.Row, now: datetime | None = None) -> dict[str, Any]:
    data = dict(row)
    clock_in = _parse_datetime(data["clock_in"])
    end = _parse_datetime(data["clock_out"]) if data["clock_out"] else (now or datetime.now(timezone.utc))
    break_seconds = int(data["total_break_seconds"])
    if data["break_started_at"] and not data["clock_out"]:
        break_seconds += max(0, int((end - _parse_datetime(data["break_started_at"])).total_seconds()))
    work_seconds = max(0, int((end - clock_in).total_seconds()) - break_seconds)
    state = "OFF_WORK" if data["clock_out"] else ("ON_BREAK" if data["break_started_at"] else "WORKING")
    return {
        "session_id": data["session_id"],
        "worker_id": data["worker_id"],
        "state": state,
        "clock_in": data["clock_in"],
        "clock_out": data["clock_out"],
        "break_started_at": data["break_started_at"],
        "total_break_seconds": break_seconds,
        "worked_seconds": work_seconds,
        "worked_minutes": work_seconds // 60,
    }


def apply_attendance_action(worker_id: str, action: str, occurred_at: datetime) -> dict[str, Any]:
    event_time = normalize_datetime(occurred_at)
    with closing(_connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM work_sessions WHERE worker_id = ? ORDER BY session_id DESC LIMIT 1",
            (worker_id,),
        ).fetchone()
        if action == "CLOCK_IN":
            if row and not row["clock_out"]:
                raise ValueError("The worker already has an active work session.")
            cursor = connection.execute(
                "INSERT INTO work_sessions(worker_id, clock_in, break_intervals) VALUES (?, ?, '[]')",
                (worker_id, event_time),
            )
            session_id = int(cursor.lastrowid)
        else:
            if not row or row["clock_out"]:
                raise ValueError("Clock in before changing the work state.")
            session_id = int(row["session_id"])
            if _parse_datetime(event_time) < _parse_datetime(row["clock_in"]):
                raise ValueError("The event time cannot be earlier than clock-in time.")
            if action == "BREAK_START":
                if row["break_started_at"]:
                    raise ValueError("The worker is already on a break.")
                connection.execute(
                    "UPDATE work_sessions SET break_started_at = ? WHERE session_id = ?",
                    (event_time, session_id),
                )
            elif action == "BREAK_END":
                if not row["break_started_at"]:
                    raise ValueError("Start a break before ending it.")
                added = max(0, int((_parse_datetime(event_time) - _parse_datetime(row["break_started_at"])).total_seconds()))
                intervals = _append_break(row, event_time)
                connection.execute(
                    """
                    UPDATE work_sessions
                    SET total_break_seconds = total_break_seconds + ?, break_started_at = NULL,
                        break_intervals = ?
                    WHERE session_id = ?
                    """,
                    (added, intervals, session_id),
                )
            elif action == "CLOCK_OUT":
                total_break = int(row["total_break_seconds"])
                if row["break_started_at"]:
                    total_break += max(0, int((_parse_datetime(event_time) - _parse_datetime(row["break_started_at"])).total_seconds()))
                connection.execute(
                    """
                    UPDATE work_sessions
                    SET clock_out = ?, break_started_at = NULL, total_break_seconds = ?,
                        break_intervals = ?
                    WHERE session_id = ?
                    """,
                    (event_time, total_break, _append_break(row, event_time), session_id),
                )
        connection.commit()
        result = connection.execute(
            "SELECT * FROM work_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return _session_result(result, _parse_datetime(event_time))


def _append_break(row: sqlite3.Row, end: str) -> str | None:
    if row["break_intervals"] is None:
        return None
    intervals = json.loads(row["break_intervals"])
    if row["break_started_at"]:
        intervals.append([row["break_started_at"], end])
    return json.dumps(intervals)


def get_work_time_today(worker_id: str, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(WORK_DAY_TIMEZONE)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM work_sessions WHERE worker_id = ? AND "
            "(clock_out IS NULL OR clock_out >= ?)",
            (worker_id, normalize_datetime(midnight)),
        ).fetchall()
    seconds = 0.0
    complete = True
    active_work_started_at = None
    clock_in_at = None
    completed_work_seconds_today = 0.0
    current_break_seconds_today = 0.0
    for row in rows:
        start = _parse_datetime(row["clock_in"])
        if not row["clock_out"]:
            clock_in_at = row["clock_in"]
        if not row["clock_out"] and not row["break_started_at"]:
            active_work_started_at = normalize_datetime(max(start, midnight))
        end = min(_parse_datetime(row["clock_out"]) if row["clock_out"] else now, now)
        lower = max(start, midnight)
        if end <= lower:
            continue
        elapsed = (end - lower).total_seconds()
        if row["break_intervals"] is None:
            if start < midnight and row["total_break_seconds"]:
                # Never invent a daily allocation for historical overnight breaks.
                complete = False
            else:
                elapsed -= row["total_break_seconds"]
        else:
            for break_start, break_end in json.loads(row["break_intervals"]):
                elapsed -= max(0, (min(end, _parse_datetime(break_end)) -
                                   max(lower, _parse_datetime(break_start))).total_seconds())
        if row["break_started_at"]:
            elapsed -= max(0, (end - max(lower, _parse_datetime(row["break_started_at"]))).total_seconds())
        worked = max(0, elapsed)
        seconds += worked
        if row["clock_out"]:
            completed_work_seconds_today += worked
        else:
            current_break_seconds_today = max(0, (end - lower).total_seconds() - worked)
    minutes = int(seconds // 60) if complete else None
    status = ("WARNING" if minutes is None else
              "EXCEEDED" if minutes >= WORK_TIME_EXCEEDED_MINUTES else
              "WARNING" if minutes >= WORK_TIME_WARNING_MINUTES else "NORMAL")
    return {"worked_minutes_today": minutes, "work_time_status": status,
            "work_time_complete": complete,
            "worked_seconds_today": int(seconds) if complete else None,
            "work_date": now.date().isoformat(),
            "work_time_calculated_at": normalize_datetime(now),
            "active_work_started_at": active_work_started_at,
            "clock_in_at": clock_in_at,
            "completed_work_seconds_today": int(completed_work_seconds_today) if complete else None,
            "current_break_seconds_today": int(current_break_seconds_today) if complete else None}


def get_worker_status(worker_id: str) -> dict[str, Any]:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM work_sessions WHERE worker_id = ? ORDER BY session_id DESC LIMIT 1",
            (worker_id,),
        ).fetchone()
    if not row:
        return {"worker_id": worker_id, "state": "BEFORE_WORK", "worked_seconds": 0, "worked_minutes": 0}
    return _session_result(row)


def list_attendance() -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY worker_id ORDER BY session_id DESC
                ) AS row_number
                FROM work_sessions
            ) WHERE row_number = 1 ORDER BY worker_id
            """
        ).fetchall()
    return [_session_result(row) for row in rows]


def list_watch_notifications(worker_id: str, after_id: int = 0) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT a.alert_id, a.worker_id AS sender_worker_id, a.type, a.message,
                   a.occurred_at,
                   CASE WHEN ack.alert_id IS NULL THEN 0 ELSE 1 END AS acknowledged
            FROM emergency_alerts a
            LEFT JOIN alert_acknowledgements ack
              ON ack.alert_id = a.alert_id AND ack.worker_id = ?
            WHERE a.alert_id > ? AND a.worker_id <> ?
            ORDER BY a.alert_id ASC
            """,
            (worker_id, after_id, worker_id),
        ).fetchall()
    return [{**dict(row), "acknowledged": bool(row["acknowledged"])} for row in rows]


def acknowledge_alert(alert_id: int, worker_id: str) -> None:
    with closing(_connect()) as connection:
        exists = connection.execute(
            "SELECT 1 FROM emergency_alerts WHERE alert_id = ?", (alert_id,)
        ).fetchone()
        if not exists:
            raise ValueError("Alert not found.")
        connection.execute(
            "INSERT OR IGNORE INTO alert_acknowledgements(alert_id, worker_id) VALUES (?, ?)",
            (alert_id, worker_id),
        )
        connection.commit()
