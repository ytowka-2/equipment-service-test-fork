from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_demo_is_idempotent_and_sorted(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite3"
    with TestClient(create_app(path, demo=True), base_url="http://127.0.0.1") as first:
        tickets = first.get("/api/tickets").json()
        assert len(tickets) == 5
        assert {ticket["status"] for ticket in tickets} == {"new", "in_progress", "closed"}
        assert [ticket["priority"] for ticket in tickets] == [
            "high",
            "high",
            "normal",
            "normal",
            "low",
        ]
        for priority in ("high", "normal", "low"):
            dates = [ticket["created_at"] for ticket in tickets if ticket["priority"] == priority]
            assert dates == sorted(dates, reverse=True)
        ticket_id = tickets[0]["id"]
        first.patch(f"/api/tickets/{ticket_id}/status", json={"status": "closed"})
        saved = first.get("/api/tickets").json()
    with TestClient(create_app(path, demo=True), base_url="http://127.0.0.1") as second:
        assert second.get("/api/tickets").json() == saved


def test_demo_does_not_mix_with_user_data(tmp_path: Path) -> None:
    path = tmp_path / "tickets.sqlite3"
    with TestClient(create_app(path), base_url="http://127.0.0.1") as first:
        ticket = first.post(
            "/api/tickets", json={"equipment": "Мой прибор", "description": "Моя проблема"}
        ).json()
    with TestClient(create_app(path, demo=True), base_url="http://127.0.0.1") as second:
        assert second.get("/api/tickets").json() == [ticket]
