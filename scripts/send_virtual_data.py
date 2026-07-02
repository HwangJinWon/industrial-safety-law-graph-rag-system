"""Send a complete set of virtual operations data to the local API server."""

from __future__ import annotations

import argparse
import json
import os
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
    args = parser.parse_args()
    API_KEY = args.api_key
    now = datetime.now(timezone.utc).replace(microsecond=0)
    suffix = int(time.time())
    worker = f"virtual-worker-{suffix}"

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
