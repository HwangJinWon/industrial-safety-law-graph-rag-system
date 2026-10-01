"""Routes shared by equipment sources, Wear OS clients, and the dashboard."""

from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from .models import (
    AttendanceRequest,
    EmergencyRequest,
    EquipmentStatusRequest,
    HeartRateRequest,
    NotificationAckRequest,
)
from .storage import (
    acknowledge_alert,
    apply_attendance_action,
    get_worker_status,
    get_work_time_today,
    list_attendance,
    list_latest_equipment,
    list_latest_workers,
    list_recent_alerts,
    list_watch_notifications,
    save_emergency,
    save_equipment_status,
    save_heart_rate,
)


router = APIRouter(prefix="/api", tags=["watch"])
ModelType = TypeVar("ModelType", bound=BaseModel)


def _validate(model: type[ModelType], payload: dict[str, Any]) -> ModelType:
    try:
        if hasattr(model, "model_validate"):
            return model.model_validate(payload)
        return model.parse_obj(payload)
    except ValidationError as exc:
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(value) for value in first.get("loc", [])) or "request"
        message = first.get("msg", "invalid value")
        raise HTTPException(status_code=400, detail=f"Invalid request: {field} - {message}") from exc


@router.get("/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/watch/heart-rate")
def post_heart_rate(payload: dict[str, Any]) -> dict[str, Any]:
    request = _validate(HeartRateRequest, payload)
    save_heart_rate(request.worker_id, request.heart_rate, request.measured_at)
    return {"success": True, "worker_id": request.worker_id, "heart_rate": request.heart_rate}


@router.post("/watch/emergency")
def post_emergency(payload: dict[str, Any]) -> dict[str, Any]:
    request = _validate(EmergencyRequest, payload)
    alert_id = save_emergency(request.worker_id, request.type, request.message, request.occurred_at)
    return {"success": True, "alert_id": alert_id, "status": "broadcast"}


@router.post("/watch/attendance")
def post_attendance(payload: dict[str, Any]) -> dict[str, Any]:
    request = _validate(AttendanceRequest, payload)
    try:
        session = apply_attendance_action(request.worker_id, request.action, request.occurred_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "action": request.action, "session": session}


@router.get("/watch/work-status/{worker_id}")
def get_watch_work_status(worker_id: str) -> dict[str, Any]:
    return get_worker_status(worker_id)


@router.get("/watch/notifications")
def get_watch_notifications(worker_id: str, after_id: int = 0) -> dict[str, list[dict[str, Any]]]:
    return {"notifications": list_watch_notifications(worker_id, after_id)}


@router.post("/watch/notifications/{alert_id}/ack")
def post_notification_ack(alert_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    request = _validate(NotificationAckRequest, payload)
    try:
        acknowledge_alert(alert_id, request.worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "alert_id": alert_id, "status": "acknowledged"}


@router.post("/equipment/status")
def post_equipment_status(payload: dict[str, Any]) -> dict[str, Any]:
    request = _validate(EquipmentStatusRequest, payload)
    save_equipment_status(
        request.equipment_id,
        request.status,
        request.production_count,
        request.defect_rate,
        request.measured_at,
    )
    return {"success": True, "equipment_id": request.equipment_id, "status": request.status}


@router.get("/dashboard/workers")
def get_workers() -> dict[str, list[dict[str, Any]]]:
    workers = []
    for worker in list_latest_workers():
        status = get_worker_status(worker["worker_id"])
        workers.append({**worker, "work_state": status["state"], "worked_minutes": status["worked_minutes"],
                        **get_work_time_today(worker["worker_id"])})
    return {"workers": workers}


@router.get("/dashboard/alerts")
def get_alerts() -> dict[str, list[dict[str, Any]]]:
    return {"alerts": list_recent_alerts()}


@router.get("/dashboard/equipment")
def get_equipment() -> dict[str, list[dict[str, Any]]]:
    return {"equipment": list_latest_equipment()}


@router.get("/dashboard/attendance")
def get_attendance() -> dict[str, list[dict[str, Any]]]:
    return {"attendance": list_attendance()}


@router.get("/dashboard/overview")
def get_dashboard_overview() -> dict[str, Any]:
    return {
        "equipment": list_latest_equipment(),
        "workers": get_workers()["workers"],
        "attendance": list_attendance(),
        "alerts": list_recent_alerts(),
    }
