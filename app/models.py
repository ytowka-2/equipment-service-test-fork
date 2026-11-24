"""Общие правила данных для браузера, API и хранилища."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

EQUIPMENT_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 2000
# SQLite хранит целочисленные ключи в знаковом 64-битном диапазоне.
TicketId = Annotated[int, Field(ge=1, le=2**63 - 1)]


class TicketStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"

    @property
    def label(self) -> str:
        return {
            self.NEW: "Новая",
            self.IN_PROGRESS: "В работе",
            self.CLOSED: "Закрыта",
        }[self]


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    @property
    def label(self) -> str:
        return {
            self.LOW: "Низкий",
            self.NORMAL: "Обычный",
            self.HIGH: "Высокий",
        }[self]


class TicketCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    equipment: str = Field(min_length=1, max_length=EQUIPMENT_MAX_LENGTH)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    priority: TicketPriority = TicketPriority.NORMAL


class TicketStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TicketStatus


class TicketPriorityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: TicketPriority


class Ticket(TicketCreate):
    id: TicketId
    status: TicketStatus
    created_at: datetime
