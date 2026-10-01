"""Send a complete set of virtual operations data to the local API server."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.request
from datetime import datetime, timedelta, timezone


API_KEY = ""


def request(base_url: str, path: str, method: str = "GET", payload: dict | None = None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    request_object = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request_object, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    global API_KEY
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.environ.get("WORKFIT_API_KEY", ""))
    parser.add_argument("--scenario", choices=["all", "watch"], default="all")
    parser.add_argument("--worker-id", help="Use the same worker ID as the real Watch")
    parser.add_argument("--action", choices=["CLOCK_IN", "HEART_RATE", "BREAK_START", "BREAK_END", "CLOCK_OUT"],
                        help="Send one step in the watch scenario")
    parser.add_argument("--heart-rate", type=int, default=92)
    parser.add_argument("--interval", type=float, default=6,
                        help="Seconds between watch scenario steps (default: 6)")
    args = parser.parse_args()
    if not 20 <= args.heart_rate <= 250 or args.interval < 0:
        parser.error("heart-rate must be 20..250 and interval must be non-negative")
    if args.action and (args.scenario != "watch" or not args.worker_id):
        parser.error("--action requires --scenario watch and --worker-id")
    API_KEY = args.api_key
    now = datetime.now(timezone.utc).replace(microsecond=0)
    suffix = int(time.time())
    worker = args.worker_id or f"virtual-worker-{suffix}"
    if args.scenario == "watch":
        actions = [args.action] if args.action else ["CLOCK_IN", *(["HEART_RATE"] * 10), "CLOCK_OUT"]
        for index, action in enumerate(actions):
            timestamp = iso(datetime.now(timezone.utc))
            if action == "HEART_RATE":
                request(args.base_url, "/api/watch/heart-rate", "POST", {
                    "worker_id": worker,
                    "heart_rate": args.heart_rate if args.action else random.randint(70, 100),
                    "measured_at": timestamp,
                })
            else:
                request(args.base_url, "/api/watch/attendance", "POST", {
                    "worker_id": worker, "action": action, "occurred_at": timestamp,
                })
            dashboard = request(args.base_url, "/api/dashboard/workers")
            print(json.dumps({"action": action, "workers": [
                row for row in dashboard["workers"] if row["worker_id"] == worker
            ]}, ensure_ascii=False), flush=True)
            if index < len(actions) - 1:
                time.sleep(args.interval)
        return

    request(args.base_url, "/api/equipment/status", "POST", {
        "equipment_id": "press-01", "status": "RUNNING",
        "production_count": 750, "defect_rate": 5.2, "measured_at": iso(now),
    })
    request(args.base_url, "/api/watch/heart-rate", "POST", {
        "worker_id": worker, "heart_rate": 92, "measured_at": iso(now),
    })
    for action, offset in (("CLOCK_IN", -120), ("BREAK_START", -90), ("BREAK_END", -75), ("CLOCK_OUT", 0)):
        request(args.base_url, "/api/watch/attendance", "POST", {
            "worker_id": worker,
            "action": action,
            "occurred_at": iso(now + timedelta(minutes=offset)),
        })
    request(args.base_url, "/api/watch/emergency", "POST", {
        "worker_id": worker, "type": "EQUIPMENT_FAILURE",
        "message": "Virtual emergency test", "occurred_at": iso(now),
    })
    overview = request(args.base_url, "/api/dashboard/overview")
    print(json.dumps({"virtual_worker": worker, "overview": overview}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
