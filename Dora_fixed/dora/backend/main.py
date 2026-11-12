"""Dora API: configurable LLM chat and optional natural-sounding neural TTS."""
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5")
API_KEY = os.getenv("LLM_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
RATE_LIMIT = max(1, int(os.getenv("RATE_LIMIT_PER_MIN", "60")))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("TTS_VOICE", "coral")

SYSTEM = (
    "You are Dora, a warm, caring female virtual companion who speaks naturally, like a thoughtful friend. "
    "Match the user's language and script (Hindi in Devanagari, Roman Hinglish, or English). "
    "Use short, conversational spoken phrasing, with natural pauses. Avoid markdown, lists and emojis unless asked. "
    "Be honest about limitations; do not claim to perform actions you cannot perform."
)
app = FastAPI(title="Dora", version="2.0.0")
hits: dict[str, deque] = defaultdict(deque)


class Msg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=20)


class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)
    language: Literal["hi-IN", "en-IN", "en-US"] = "hi-IN"


def client_ip(request: Request) -> str:
    # On managed hosts, prefer the first forwarded address; fall back to socket peer.
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def check_rate(ip: str) -> None:
    now, q = time.time(), hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Rate limit reached. Wait a minute and try again.", headers={"Retry-After": "60"})
    q.append(now)


async def call_llm(messages: list[dict]) -> str:
    if not API_KEY:
        raise HTTPException(503, "Chat is not configured: add LLM_API_KEY in the hosting environment.")
    system = SYSTEM + " Current local date and time: " + datetime.now().astimezone().strftime("%A, %d %B %Y, %I:%M %p %Z") + "."
    async with httpx.AsyncClient(timeout=60) as c:
        try:
            if PROVIDER == "anthropic":
                r = await c.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": MODEL, "max_tokens": 500, "system": system, "messages": messages},
                )
                if r.status_code == 429:
                    raise HTTPException(503, "The AI provider is temporarily rate-limiting requests. Try again shortly.")
                if r.is_error:
                    raise HTTPException(502, f"AI provider error ({r.status_code}). Check the model name and API key in hosting settings.")
                data = r.json()
                return "".join(x.get("text", "") for x in data.get("content", []) if x.get("type") == "text")
            if PROVIDER == "openai":
                r = await c.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    json={"model": MODEL, "max_tokens": 500, "messages": [{"role": "system", "content": system}] + messages},
                )
                if r.status_code == 429:
                    raise HTTPException(503, "The AI provider is temporarily rate-limiting requests. Try again shortly.")
                if r.is_error:
                    raise HTTPException(502, f"AI provider error ({r.status_code}). Check model, key and billing settings.")
                return r.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            raise HTTPException(504, "The AI provider took too long to respond. Please retry.")
        except httpx.HTTPError:
            raise HTTPException(502, "Could not connect to the AI provider.")
    raise HTTPException(500, "Unknown LLM_PROVIDER. Use anthropic or openai.")


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    check_rate(client_ip(request))
    if body.messages[-1].role != "user" or body.messages[0].role != "user":
        raise HTTPException(422, "Conversation must start and end with a user message")
    reply = (await call_llm([m.model_dump() for m in body.messages])).strip()
    if not reply:
        raise HTTPException(502, "The AI provider returned an empty response.")
    return {"reply": reply}


@app.post("/api/speech")
async def speech(body: SpeechIn, request: Request):
    """Generate neural speech. If no TTS key is configured, frontend uses browser voice."""
    if not OPENAI_API_KEY:
        raise HTTPException(503, "Natural voice is not configured. Add OPENAI_API_KEY to enable it.")
    check_rate("tts:" + client_ip(request))
    instructions = (
        "Speak as a friendly, warm, young adult female assistant. Sound natural, expressive and reassuring, "
        "with a soft conversational pace, clear pronunciation and subtle emotion. Avoid sounding like a narrator. "
        + ("Speak fluent Hindi with a natural Indian accent." if body.language == "hi-IN" else "Speak fluent Indian English with a natural Indian accent.")
    )
    async with httpx.AsyncClient(timeout=60) as c:
        try:
            r = await c.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"model": TTS_MODEL, "voice": TTS_VOICE, "input": body.text, "instructions": instructions, "response_format": "mp3"},
            )
        except httpx.HTTPError:
            raise HTTPException(502, "Could not connect to the speech provider.")
    if r.status_code == 429:
        raise HTTPException(503, "Speech provider is temporarily rate-limiting requests.")
    if r.is_error:
        raise HTTPException(502, f"Speech provider error ({r.status_code}). Check OPENAI_API_KEY and TTS settings.")
    return Response(content=r.content, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "provider": PROVIDER,
        "chat_configured": bool(API_KEY),
        "neural_voice_configured": bool(OPENAI_API_KEY),
        "tts_voice": TTS_VOICE,
    }


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
