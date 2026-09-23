from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .assistant import build_reply
from .audio import synthesize_speech, transcribe_audio
from .router import LLMRouter, accepted_ids
from .schemas import ChatResponse, RouteRequest, RouteResponse
from .session import sessions

app = FastAPI(title="Saqta Voice Router", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "service": "saqta-voice-router", "version": "0.1.0"}


@app.post("/api/reset/{session_id}")
def reset(session_id: str):
    sessions.reset(session_id)
    return {"ok": True}


@app.post("/api/route", response_model=RouteResponse)
def route(req: RouteRequest):
    try:
        state = sessions.get(req.session_id)
        decision, router_ms = get_router().route(req.text, state)
        accepted = accepted_ids(decision)
        return RouteResponse(
            decision=decision,
            accepted_scenarios=accepted,
            latency_ms={"router": router_ms, "total": router_ms},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: RouteRequest):
    started = time.perf_counter()
    try:
        state = sessions.get(req.session_id)
        decision, router_ms = get_router().route(req.text, state)
        accepted = accepted_ids(decision)
        reply = build_reply(decision, accepted, state)
        state.history.extend([
            {"role": "client", "text": req.text},
            {"role": "bot", "text": reply},
        ])
        total_ms = round((time.perf_counter() - started) * 1000)
        reason = "; ".join(f"{x.scenario_id}: {x.reason}" for x in decision.scenarios)
        return ChatResponse(
            session_id=req.session_id,
            transcript=req.text,
            reply=reply,
            language=decision.language,
            scenarios=decision.scenarios,
            alternatives=decision.alternatives,
            slots=state.slots,
            reason=reason,
            latency_ms={"stt": 0, "triage": 0, "router": router_ms, "response": total_ms-router_ms, "tts_first_audio": 0, "total": total_ms},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    started = time.perf_counter()
    data = await file.read()
    try:
        text = transcribe_audio(data, file.filename or "speech.webm")
        ms = round((time.perf_counter() - started) * 1000)
        return {"text": text, "latency_ms": ms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/tts")
def tts(payload: dict):
    text = str(payload.get("text", "")).strip()
    language = str(payload.get("language", "ru"))
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        audio = synthesize_speech(text, language)
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
