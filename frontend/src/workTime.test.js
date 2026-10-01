import test from "node:test";
import assert from "node:assert/strict";
import { workedSecondsToday, formatWorkSeconds, workDateTitle, workTimeQuestion } from "./workTime.js";

const received = Date.parse("2026-09-30T05:00:00Z");
const worker = {
  worker_id: "worker-001", work_state: "WORKING", worked_seconds_today: 7200,
  work_date: "2026-09-30", work_time_calculated_at: "2026-09-30T05:00:00Z",
  active_work_started_at: "2026-09-30T04:00:00Z", _received_at: received,
};

test("adds only time since snapshot, including after a delayed timer", () => {
  assert.equal(formatWorkSeconds(workedSecondsToday(worker, received)), "02:00:00");
  assert.equal(formatWorkSeconds(workedSecondsToday(worker, received + 1000)), "02:00:01");
  assert.equal(workedSecondsToday(worker, received + 65000), 7265);
});

test("clock-out and break snapshots stop interpolation", () => {
  for (const work_state of ["OFF_WORK", "ON_BREAK"]) {
    assert.equal(workedSecondsToday({ ...worker, work_state }, received + 60000), 7200);
  }
});

test("polling resynchronizes without double counting", () => {
  const next = { ...worker, worked_seconds_today: 7205,
    work_time_calculated_at: "2026-09-30T05:00:05Z", _received_at: received + 5000 };
  assert.equal(workedSecondsToday(next, received + 6000), 7206);
});

test("KST midnight discards yesterday and continues only current work", () => {
  const midnight = Date.parse("2026-09-30T15:00:00Z");
  assert.equal(workedSecondsToday(worker, midnight), 0);
  assert.equal(workedSecondsToday(worker, midnight + 2000), 2);
  assert.equal(workedSecondsToday({ ...worker, work_state: "OFF_WORK" }, midnight + 2000), 0);
  assert.equal(workedSecondsToday({ ...worker, work_state: "ON_BREAK" }, midnight + 2000), 0);
  assert.equal(workDateTitle(midnight), "2026년 10월 01일 근무시간 현황");
});

test("server snapshot avoids client clock offset and prompt uses live duration", () => {
  const shifted = { ...worker, _received_at: received + 3600000 };
  assert.equal(workedSecondsToday(shifted, received + 3601000), 7201);
  const question = workTimeQuestion(worker, received + 1000);
  for (const text of ["worker-001", "WORKING", "02:00:01", "2026-09-30"]) assert.ok(question.includes(text));
});

test("older API or incomplete historical data does not invent zero work", () => {
  assert.equal(workedSecondsToday({ worker_id: "legacy" }, received), null);
  assert.equal(formatWorkSeconds(null), "—");
});

test("missing time can still produce a QA question in either work state", () => {
  for (const work_state of ["WORKING", "OFF_WORK"]) {
    const question = workTimeQuestion({ worker_id: "demo-worker-001", work_state }, received);
    assert.ok(question.includes("현재 확인 가능한 근무시간 정보 없음"));
    assert.ok(question.includes(work_state));
    assert.ok(question.includes("demo-worker-001"));
    assert.ok(!question.includes("00:00:00"));
  }
});

test("partially deployed response never fabricates a daily baseline", () => {
  assert.equal(workedSecondsToday({ ...worker, work_date: undefined }, received), null);
  assert.equal(workedSecondsToday({ ...worker, active_work_started_at: undefined }, received), null);
});

test("clock-in alone starts a one-second timer without snapshot fields", () => {
  const row = { work_state: "WORKING", clock_in_at: "2026-09-30T05:00:00Z" };
  assert.equal(formatWorkSeconds(workedSecondsToday(row, received + 37000)), "00:00:37");
  assert.equal(formatWorkSeconds(workedSecondsToday(row, received + 38000)), "00:00:38");
});

test("clock-in contract adds completed sessions, excludes breaks and resets at midnight", () => {
  const row = { ...worker, clock_in_at: "2026-09-30T04:00:00Z",
    completed_work_seconds_today: 3600, current_break_seconds_today: 600 };
  assert.equal(workedSecondsToday(row, received), 6600);
  assert.equal(workedSecondsToday(row, received + 1000), 6601);
  assert.equal(workedSecondsToday(row, Date.parse("2026-09-30T15:00:03Z")), 3);
  assert.equal(workedSecondsToday({ ...row, completed_work_seconds_today: null }, received), null);
});
