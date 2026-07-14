import os
import json
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.database import (
    add_message,
    create_conversation,
    delete_conversation,
    delete_message,
    get_conversation,
    get_conversations,
    get_message,
    get_messages,
    init_db,
    search_conversations,
    update_conversation,
    update_conversation_timestamp,
    update_message,
    touch_message_conversation,
)
from app.ollama_client import OllamaClient

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Local Ollama Chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
client = OllamaClient(os.getenv("OLLAMA_BASE_URL"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/models")
async def list_models() -> list[dict[str, Any]]:
    try:
        return await client.list_models()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Unable to reach Ollama: {exc}") from exc


@app.get("/api/conversations")
async def conversations() -> list[dict[str, Any]]:
    return get_conversations()


@app.get("/api/conversations/search")
async def search(query: str) -> list[dict[str, Any]]:
    return search_conversations(query)


@app.post("/api/conversations", status_code=201)
async def create_new_conversation(payload: dict[str, Any]) -> dict[str, Any]:
    conv_id = create_conversation(
        title=payload.get("title", "New conversation"),
        system_prompt=payload.get("system_prompt", os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful assistant")),
        model=payload.get("model", os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2")),
        temperature=float(payload.get("temperature", 0.7)),
        max_tokens=int(payload.get("max_tokens", payload.get("maxTokens", 512))),
        top_p=float(payload.get("top_p", payload.get("topP", 0.9))),
        top_k=int(payload.get("top_k", payload.get("topK", 40))),
    )
    return {"id": conv_id}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation_detail(conversation_id: int) -> dict[str, Any]:
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation["messages"] = get_messages(conversation_id)
    return conversation


@app.put("/api/conversations/{conversation_id}")
async def update_conversation_settings(conversation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    allowed_fields = {"title", "system_prompt", "model", "temperature", "max_tokens", "top_p", "top_k"}
    fields = {key: value for key, value in payload.items() if key in allowed_fields}
    if not fields:
        raise HTTPException(status_code=400, detail="No valid fields supplied")
    update_conversation(conversation_id, **fields)
    return {"status": "ok"}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation_route(conversation_id: int) -> dict[str, Any]:
    delete_conversation(conversation_id)
    return {"status": "deleted"}


@app.post("/api/conversations/{conversation_id}/messages")
async def add_message_route(conversation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    content = str(payload.get("content", "")).strip()
    role = payload.get("role", "user")
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    if role not in {"user", "assistant"}:
        raise HTTPException(status_code=400, detail="Invalid message role")
    message_id = add_message(conversation_id, role, content)
    update_conversation_timestamp(conversation_id)
    return {"id": message_id}


@app.put("/api/messages/{message_id}")
async def edit_message(message_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    message = get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")
    update_message(message_id, content)
    touch_message_conversation(message_id)
    return {"status": "updated"}


@app.delete("/api/messages/{message_id}")
async def remove_message(message_id: int) -> dict[str, Any]:
    delete_message(message_id)
    return {"status": "deleted"}


@app.get("/api/conversations/{conversation_id}/export")
async def export_conversation(conversation_id: int, format: str = Query(default="json")) -> Response:
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_messages(conversation_id)
    if format == "markdown":
        markdown = f"# {conversation['title']}\n\n"
        for item in messages:
            markdown += f"## {item['role'].title()}\n\n{item['content']}\n\n"
        return Response(content=markdown, media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename={conversation['title']}.md"})
    if format == "pdf":
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        pdf.setTitle(conversation["title"])
        pdf.drawString(40, 760, conversation["title"])
        y = 730
        for item in messages:
            text = f"{item['role'].title()}: {item['content']}"
            for line in text.splitlines() or [text]:
                pdf.drawString(40, y, line[:100])
                y -= 14
                if y < 40:
                    pdf.showPage()
                    y = 760
        pdf.save()
        buffer.seek(0)
        return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={conversation['title']}.pdf"})
    return JSONResponse(
        content={"id": conversation_id, "title": conversation["title"], "messages": messages},
        headers={"Content-Disposition": f"attachment; filename={conversation['title']}.json"},
    )


@app.post("/api/models/pull")
async def pull_model(payload: dict[str, Any]) -> dict[str, Any]:
    model_name = payload.get("name")
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name is required")
    try:
        return await client.pull_model(model_name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to pull model: {exc}") from exc


@app.post("/api/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    payload = await request.json()
    conversation_id = int(payload.get("conversation_id"))
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = get_messages(conversation_id)
    messages = [{"role": item["role"], "content": item["content"]} for item in history]
    messages = [{"role": "system", "content": conversation["system_prompt"]}] + messages

    async def event_stream() -> Any:
        response_parts: list[str] = []
        try:
            async for chunk in client.stream_chat(
                messages=messages,
                model=conversation["model"],
                temperature=float(conversation["temperature"]),
                top_p=float(conversation["top_p"]),
                top_k=int(conversation["top_k"]),
                max_tokens=int(conversation["max_tokens"]),
            ):
                if chunk["done"]:
                    break
                delta = chunk["delta"]
                response_parts.append(delta)
                yield f"data: {json.dumps({'delta': delta})}\n\n"
            response_text = "".join(response_parts).strip()
            if response_text:
                add_message(conversation_id, "assistant", response_text)
                update_conversation_timestamp(conversation_id)
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
