"""Request validation models for operations data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HeartRateRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    heart_rate: int = Field(ge=20, le=250)
    measured_at: datetime


class EmergencyRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=1000)
    occurred_at: datetime


class EquipmentStatusRequest(BaseModel):
    equipment_id: str = Field(min_length=1, max_length=100)
    status: Literal["RUNNING", "IDLE", "WARNING", "STOPPED"]
    production_count: int = Field(ge=0)
    defect_rate: float = Field(ge=0, le=100)
    measured_at: datetime


class AttendanceRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
    action: Literal["CLOCK_IN", "BREAK_START", "BREAK_END", "CLOCK_OUT"]
    occurred_at: datetime


class NotificationAckRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=100)
