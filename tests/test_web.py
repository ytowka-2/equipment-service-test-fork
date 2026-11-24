import pytest
from fastapi.testclient import TestClient


def test_empty_list_and_creation_form(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Пока нет заявок" in response.text
    assert 'href="/tickets/new"' in response.text
    assert client.get("/tickets/new").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_browser_lifecycle(client: TestClient, ticket_data: dict[str, str]) -> None:
    response = client.post("/tickets", data=ticket_data, follow_redirects=False)
    assert response.status_code == 303
    url = response.headers["location"]
    detail = client.get(url)
    assert detail.status_code == 200
    assert "Заявка создана." in detail.text
    assert ticket_data["equipment"] in detail.text
    assert ticket_data["description"] in detail.text
    assert "Обычный" in detail.text
    assert ticket_data["equipment"] in client.get("/").text

    ticket = client.get("/api/tickets").json()[0]
    response = client.post(
        f"/tickets/{ticket['id']}/status", data={"status": "closed"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "Статус сохранён." in client.get(response.headers["location"]).text
    assert client.get(f"/api/tickets/{ticket['id']}").json()["status"] == "closed"
    # Обновление страницы после POST не должно создавать ещё одну заявку.
    client.get(url)
    assert len(client.get("/api/tickets").json()) == 1


def test_priority_is_set_on_creation_and_changed_in_detail(
    client: TestClient, ticket_data: dict[str, str]
) -> None:
    response = client.post(
        "/tickets", data={**ticket_data, "priority": "high"}, follow_redirects=False
    )
    assert response.status_code == 303
    url = response.headers["location"]
    detail = client.get(url)
    assert "Высокий" in detail.text
    ticket = client.get("/api/tickets").json()[0]
    assert ticket["priority"] == "high"

    response = client.post(
        f"/tickets/{ticket['id']}/priority", data={"priority": "low"}, follow_redirects=False
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert "Приоритет сохранён." in detail.text
    assert "Низкий" in detail.text
    assert client.get(f"/api/tickets/{ticket['id']}").json()["priority"] == "low"


@pytest.mark.parametrize("priority", ["unknown", ""])
def test_invalid_priority_is_explained(
    client: TestClient, ticket_data: dict[str, str], priority: str
) -> None:
    ticket = client.post("/api/tickets", json=ticket_data).json()
    response = client.post(f"/tickets/{ticket['id']}/priority", data={"priority": priority})
    assert response.status_code == 422
    assert "Выберите приоритет из списка." in response.text
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket


def test_invalid_priority_on_creation_is_explained(
    client: TestClient, ticket_data: dict[str, str]
) -> None:
    response = client.post("/tickets", data={**ticket_data, "priority": "unknown"})
    assert response.status_code == 422
    assert "Выберите приоритет из списка." in response.text
    assert ticket_data["equipment"] in response.text
    assert client.get("/api/tickets").json() == []


@pytest.mark.parametrize(
    "payload, expected_error",
    [
        ({"equipment": "   ", "description": "Проблема"}, "Заполните это поле"),
        ({"equipment": "Прибор", "description": ""}, "Заполните это поле"),
        ({"equipment": "x" * 121, "description": "Проблема"}, "120 символов"),
        ({"equipment": "Прибор", "description": "я" * 2001}, "2000 символов"),
    ],
)
def test_form_errors_preserve_values(
    client: TestClient, payload: dict[str, str], expected_error: str
) -> None:
    response = client.post("/tickets", data=payload)
    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]
    assert expected_error in response.text
    assert payload["equipment"] in response.text
    assert payload["description"] in response.text
    assert client.get("/api/tickets").json() == []


def test_missing_form_fields_are_explained(client: TestClient) -> None:
    response = client.post("/tickets", data={})
    assert response.status_code == 422
    assert response.text.count("Заполните это поле") == 2


@pytest.mark.parametrize("status", ["unknown", ""])
def test_invalid_status_is_explained(
    client: TestClient, ticket_data: dict[str, str], status: str
) -> None:
    ticket = client.post("/api/tickets", json=ticket_data).json()
    response = client.post(f"/tickets/{ticket['id']}/status", data={"status": status})
    assert response.status_code == 422
    assert "Выберите статус из списка." in response.text
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket


@pytest.mark.parametrize("url", ["/tickets/999", "/unknown"])
def test_html_not_found(client: TestClient, url: str) -> None:
    response = client.get(url)
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert 'href="/"' in response.text


def test_bad_ticket_number_has_html_error(client: TestClient) -> None:
    response = client.get("/tickets/not-a-number")
    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]


def test_user_text_is_escaped(client: TestClient) -> None:
    payload = {"equipment": '<script>alert("x")</script>', "description": "<b>Не HTML</b>"}
    ticket = client.post("/api/tickets", json=payload).json()
    for url in ("/", f"/tickets/{ticket['id']}"):
        response = client.get(url)
        assert "<script>" not in response.text
        assert "&lt;script&gt;" in response.text
        assert "<b>Не HTML</b>" not in response.text


def test_form_error_also_escapes_text(client: TestClient) -> None:
    response = client.post(
        "/tickets", data={"equipment": '"><script>alert(1)</script>', "description": ""}
    )
    assert response.status_code == 422
    assert "<script>" not in response.text


def test_foreign_origin_cannot_create_ticket(
    client: TestClient, ticket_data: dict[str, str]
) -> None:
    response = client.post(
        "/tickets", data=ticket_data, headers={"Origin": "https://another.example"}
    )
    assert response.status_code == 403
    assert client.get("/api/tickets").json() == []


def test_same_origin_form_is_accepted(client: TestClient, ticket_data: dict[str, str]) -> None:
    response = client.post(
        "/tickets",
        data=ticket_data,
        headers={"Origin": "http://127.0.0.1"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_unknown_host_is_rejected(client: TestClient) -> None:
    response = client.get("/", headers={"Host": "another.example"})
    assert response.status_code == 400
