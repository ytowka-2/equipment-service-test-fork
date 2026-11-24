"""SQLite без ORM: короткие соединения, транзакции, параметризованные запросы."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import Ticket, TicketCreate, TicketPriority, TicketStatus


class TicketNotFoundError(LookupError):
    """Заявки с таким номером нет в хранилище."""


class TicketRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            # Контекст соединения управляет транзакцией, но сам его не закрывает.
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY,
                    equipment TEXT NOT NULL
                        CHECK (length(trim(equipment)) BETWEEN 1 AND 120),
                    description TEXT NOT NULL
                        CHECK (length(trim(description)) BETWEEN 1 AND 2000),
                    status TEXT NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'in_progress', 'closed')),
                    priority TEXT NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low', 'normal', 'high')),
                    created_at TEXT NOT NULL
                )
            """)
            # Старая база создана без приоритета: добавляем колонку, не теряя заявки.
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tickets)").fetchall()
            }
            if "priority" not in columns:
                connection.execute("""
                    ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low', 'normal', 'high'))
                """)

    def list_all(self) -> list[Ticket]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT * FROM tickets
                ORDER BY
                    CASE priority
                        WHEN 'high' THEN 0
                        WHEN 'normal' THEN 1
                        ELSE 2
                    END,
                    created_at DESC,
                    id DESC
            """).fetchall()
        return [Ticket.model_validate(dict(row)) for row in rows]

    def get(self, ticket_id: int) -> Ticket:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            raise TicketNotFoundError(ticket_id)
        return Ticket.model_validate(dict(row))

    def create(self, data: TicketCreate) -> Ticket:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tickets (equipment, description, status, priority, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    data.equipment,
                    data.description,
                    TicketStatus.NEW.value,
                    data.priority.value,
                    datetime.now(UTC).isoformat(),
                ),
            )
            ticket_id = cursor.lastrowid
            assert ticket_id is not None
        return self.get(ticket_id)

    def update_status(self, ticket_id: int, status: TicketStatus) -> Ticket:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (status.value, ticket_id),
            )
            if cursor.rowcount == 0:
                raise TicketNotFoundError(ticket_id)
        return self.get(ticket_id)

    def update_priority(self, ticket_id: int, priority: TicketPriority) -> Ticket:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tickets SET priority = ? WHERE id = ?",
                (priority.value, ticket_id),
            )
            if cursor.rowcount == 0:
                raise TicketNotFoundError(ticket_id)
        return self.get(ticket_id)

    def seed_demo(self) -> None:
        """Добавляет примеры только в пустую базу, не меняя существующие заявки."""
        now = datetime.now(UTC)
        examples = [
            (
                "Осциллограф Rigol DS1054Z · Э-204",
                "После включения не отображается сигнал на втором канале. "
                "Кабель проверен на другом приборе — работает.",
                TicketStatus.NEW,
                TicketPriority.HIGH,
                now - timedelta(hours=2),
            ),
            (
                "3D-принтер Prusa MK4 · М-112",
                "Печать останавливается через 10–15 минут. "
                "На экране сообщение об ошибке нагрева стола.",
                TicketStatus.IN_PROGRESS,
                TicketPriority.NORMAL,
                now - timedelta(days=1),
            ),
            (
                "Испытательная машина · М-108",
                "При запуске испытания слышен посторонний шум. "
                "До осмотра оборудование выведено из эксплуатации.",
                TicketStatus.NEW,
                TicketPriority.HIGH,
                now - timedelta(days=4),
            ),
            (
                "Лабораторный блок питания · Э-204",
                "Не работает регулировка напряжения. "
                "Требуется проверить энкодер на передней панели.",
                TicketStatus.IN_PROGRESS,
                TicketPriority.NORMAL,
                now - timedelta(days=6),
            ),
            (
                "Аналитические весы · Х-301",
                "Показания нестабильны после переноса прибора. "
                "Выполнены установка по уровню и калибровка — проблема устранена.",
                TicketStatus.CLOSED,
                TicketPriority.LOW,
                now - timedelta(days=8),
            ),
        ]
        with self._connect() as connection:
            # Блокировка делает проверку и вставку единой операцией даже при двух запусках.
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM tickets LIMIT 1").fetchone():
                return
            connection.executemany(
                """
                INSERT INTO tickets (equipment, description, status, priority, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        equipment,
                        description,
                        status.value,
                        priority.value,
                        created_at.isoformat(),
                    )
                    for equipment, description, status, priority, created_at in examples
                ],
            )
