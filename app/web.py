"""Страницы и обычные HTML-формы: JavaScript для работы приложения не нужен."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.models import (
    DESCRIPTION_MAX_LENGTH,
    EQUIPMENT_MAX_LENGTH,
    TicketCreate,
    TicketId,
    TicketPriority,
    TicketPriorityUpdate,
    TicketStatus,
    TicketStatusUpdate,
)
from app.repository import TicketRepository


def _field_errors(error: ValidationError) -> dict[str, str]:
    messages = {}
    for item in error.errors():
        field = str(item["loc"][0])
        if field == "priority":
            messages[field] = "Выберите приоритет из списка."
        elif item["type"] == "string_too_long":
            limit = item["ctx"]["max_length"]
            messages[field] = f"Сократите текст до {limit} символов."
        else:
            messages[field] = "Заполните это поле — пробелы не считаются текстом."
    return messages


def create_web_router(repository: TicketRepository, templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        tickets = repository.list_all()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"tickets": tickets, "counts": Counter(ticket.status for ticket in tickets)},
        )

    @router.get("/tickets/new", response_class=HTMLResponse)
    def new_ticket(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request, name="new.html", context={"values": {}, "errors": {}}
        )

    @router.post("/tickets", response_model=None)
    def create_ticket(
        request: Request,
        equipment: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
        priority: Annotated[str | None, Form()] = None,
    ) -> HTMLResponse | RedirectResponse:
        values = {
            "equipment": equipment,
            "description": description,
            "priority": priority if priority is not None else TicketPriority.NORMAL.value,
        }
        try:
            data = TicketCreate.model_validate(values)
        except ValidationError as error:
            return templates.TemplateResponse(
                request=request,
                name="new.html",
                context={"values": values, "errors": _field_errors(error)},
                status_code=422,
            )
        ticket = repository.create(data)
        return RedirectResponse(f"/tickets/{ticket.id}?notice=created", status_code=303)

    @router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
    def ticket_detail(request: Request, ticket_id: TicketId) -> HTMLResponse:
        notices = {
            "created": "Заявка создана.",
            "updated": "Статус сохранён.",
            "priority_updated": "Приоритет сохранён.",
        }
        return templates.TemplateResponse(
            request=request,
            name="detail.html",
            context={
                "ticket": repository.get(ticket_id),
                "notice": notices.get(request.query_params.get("notice", "")),
            },
        )

    @router.post("/tickets/{ticket_id}/status", response_model=None)
    def update_status(
        request: Request, ticket_id: TicketId, status: Annotated[str, Form()] = ""
    ) -> HTMLResponse | RedirectResponse:
        ticket = repository.get(ticket_id)
        try:
            data = TicketStatusUpdate(status=status)
        except ValidationError:
            return templates.TemplateResponse(
                request=request,
                name="detail.html",
                context={"ticket": ticket, "error": "Выберите статус из списка."},
                status_code=422,
            )
        repository.update_status(ticket_id, data.status)
        return RedirectResponse(f"/tickets/{ticket_id}?notice=updated", status_code=303)

    @router.post("/tickets/{ticket_id}/priority", response_model=None)
    def update_priority(
        request: Request, ticket_id: TicketId, priority: Annotated[str, Form()] = ""
    ) -> HTMLResponse | RedirectResponse:
        ticket = repository.get(ticket_id)
        try:
            data = TicketPriorityUpdate(priority=priority)
        except ValidationError:
            return templates.TemplateResponse(
                request=request,
                name="detail.html",
                context={"ticket": ticket, "priority_error": "Выберите приоритет из списка."},
                status_code=422,
            )
        repository.update_priority(ticket_id, data.priority)
        return RedirectResponse(f"/tickets/{ticket_id}?notice=priority_updated", status_code=303)

    templates.env.globals.update(
        statuses=list(TicketStatus),
        priorities=list(TicketPriority),
        equipment_max_length=EQUIPMENT_MAX_LENGTH,
        description_max_length=DESCRIPTION_MAX_LENGTH,
    )
    return router
