const seoulDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
});

export function workDate(now) {
  const parts = Object.fromEntries(seoulDate.formatToParts(new Date(now))
    .map(({ type, value }) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function workDateTitle(now) {
  const [year, month, day] = workDate(now).split("-");
  return `${year}년 ${month}월 ${day}일 근무시간 현황`;
}

export function workTimeNow(worker, now = Date.now()) {
  const calculated = Date.parse(worker?.work_time_calculated_at);
  return Number.isFinite(calculated) && Number.isFinite(worker?._received_at)
    ? calculated + Math.max(0, now - worker._received_at) : now;
}

export function workedSecondsToday(worker, now = Date.now()) {
  const current = workTimeNow(worker, now);
  const today = workDate(current);
  const midnight = Date.parse(`${today}T00:00:00+09:00`);
  const clockIn = Date.parse(worker.clock_in_at);
  if (worker.work_state === "WORKING" && Number.isFinite(clockIn)) {
    // Completed sessions are separate from this active session, including its breaks.
    // A clock-in-only response can still show the known current session elapsed time.
    const sameDay = !worker.work_date || worker.work_date === today;
    const completed = sameDay ? (worker.completed_work_seconds_today === undefined ? 0 : worker.completed_work_seconds_today) : 0;
    const breaks = sameDay ? (worker.current_break_seconds_today === undefined ? 0 : worker.current_break_seconds_today) : 0;
    if (!Number.isFinite(completed) || !Number.isFinite(breaks)) return null;
    const elapsed = Math.max(0, (current - Math.max(clockIn, midnight)) / 1000 - breaks);
    return Math.max(0, Math.floor(completed + elapsed));
  }
  const calculated = Date.parse(worker.work_time_calculated_at);
  if (!Number.isFinite(calculated) || !Number.isFinite(worker.worked_seconds_today)) return null;
  if (worker.work_date !== workDate(calculated)) return null;
  const started = Date.parse(worker.active_work_started_at);
  if (worker.work_state === "WORKING" && !Number.isFinite(started)) return null;
  // The API total includes the active session up to calculated_at already.
  // Add only elapsed time since that snapshot, never CLOCK_IN a second time.
  const baseline = worker.work_date === today ? worker.worked_seconds_today : 0;
  const elapsed = worker.work_state === "WORKING" && Number.isFinite(started)
    ? Math.max(0, (current - Math.max(calculated, midnight, started)) / 1000) : 0;
  return Math.max(0, Math.floor(baseline + elapsed));
}

export function formatWorkSeconds(seconds) {
  if (seconds == null) return "—";
  const value = Math.max(0, Math.floor(seconds));
  return [Math.floor(value / 3600), Math.floor(value / 60) % 60, value % 60]
    .map((part) => String(part).padStart(2, "0")).join(":");
}

export function workTimeQuestion(worker, now = Date.now()) {
  const seconds = workedSecondsToday(worker, now);
  const duration = seconds == null
    ? "현재 확인 가능한 근무시간 정보 없음"
    : `${formatWorkSeconds(seconds)}(시:분:초)`;
  return `작업자 ${worker.worker_id}의 ${workDate(workTimeNow(worker, now))}(한국시간 기준) 누적 근무시간 정보: ${duration}. 현재 근무 상태는 ${worker.work_state}입니다. 이 근무시간과 관련하여 확인해야 할 근로시간, 휴게시간, 연장근로 관련 법령 및 주의사항을 확인된 법령 근거를 중심으로 설명해줘. 현재 수치만으로 법 위반을 단정하지 말고 추가로 확인해야 할 조건도 함께 알려줘. 검색된 근거가 없으면 근거 부족을 명시해줘.`;
}
