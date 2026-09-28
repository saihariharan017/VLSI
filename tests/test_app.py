import os

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "false")

import app


def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"VLSI" in response.data
    assert b"GEMINI_API_KEY" not in response.data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_empty_input(client):
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "enter a question" in response.json["error"].lower()


def test_unrelated_first_question_is_rejected_without_gemini(client):
    response = client.post("/api/chat", json={"message": "Who won the football match yesterday?"})
    assert response.status_code == 200
    assert "focused only" in response.json["answer"].lower()


def test_greeting(client):
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert "vlsi" in response.json["answer"].lower()


def test_clear_isolated_session(client):
    with client.session_transaction() as sess:
        sess["chat_history"] = [{"role": "user", "text": "secret"}]
    assert client.get("/api/history").json["messages"][0]["text"] == "secret"
    assert client.post("/api/clear").status_code == 200
    assert client.get("/api/history").json["messages"] == []


class DummyClient:
    class Models:
        @staticmethod
        def generate_content(**kwargs):
            class Response:
                text = "Setup time is the time data must be stable before the active clock edge."
            return Response()

    models = Models()


def test_gemini_integration_with_mock(client, monkeypatch):
    monkeypatch.setattr(app, "gemini_client", DummyClient())
    response = client.post("/api/chat", json={"message": "Explain setup time in VLSI"})
    assert response.status_code == 200
    assert "Setup time" in response.json["answer"]
    history = client.get("/api/history").json["messages"]
    assert history[-2]["role"] == "user"
    assert history[-1]["role"] == "assistant"


# pytest fixture kept local to avoid adding pytest as a runtime dependency.
import pytest


@pytest.fixture
def client():
    app.app.config.update(TESTING=True)
    with app.app.test_client() as test_client:
        yield test_client
