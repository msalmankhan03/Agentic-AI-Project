from fastapi.testclient import TestClient

from app.main import app, client as ollama_client

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_conversation() -> None:
    response = client.post(
        "/api/conversations",
        json={"title": "Test chat", "system_prompt": "You are helpful", "model": "llama3.2"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data


def test_chat_stream_persists_assistant_reply(monkeypatch) -> None:
    async def fake_stream_chat(**_kwargs):
        yield {"delta": "Hello", "done": False}
        yield {"delta": " world", "done": False}
        yield {"delta": "", "done": True}

    monkeypatch.setattr(ollama_client, "stream_chat", fake_stream_chat)
    conversation_id = client.post("/api/conversations", json={"title": "Stream test"}).json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "Hi"},
    )

    response = client.post("/api/chat/stream", json={"conversation_id": conversation_id})

    assert response.status_code == 200
    assert '"delta": "Hello"' in response.text
    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert conversation["messages"][-1]["role"] == "assistant"
    assert conversation["messages"][-1]["content"] == "Hello world"


def test_conversation_update_rejects_unknown_fields() -> None:
    conversation_id = client.post("/api/conversations", json={"title": "Settings test"}).json()["id"]
    response = client.put(f"/api/conversations/{conversation_id}", json={"unknown": "value"})
    assert response.status_code == 400
