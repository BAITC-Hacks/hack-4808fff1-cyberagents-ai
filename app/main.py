from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .assistant import build_reply
from .audio import synthesize_speech, transcribe_audio
from .router import LLMRouter, accepted_ids
from .schemas import ChatResponse, RouteRequest, RouteResponse
from .session import sessions

app = FastAPI(title="Saqta Voice Router", version="0.2.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

MAX_AUDIO_BYTES = 15 * 1024 * 1024
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
    return {"ok": True, "service": "saqta-voice-router", "version": "0.2.0"}


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
        raise HTTPException(status_code=500, detail="Routing failed") from e


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: RouteRequest):
    started = time.perf_counter()
    try:
        state = sessions.get(req.session_id)
        decision, router_ms = get_router().route(req.text, state)
        accepted = accepted_ids(decision)
        reply, reply_language, handoff = build_reply(
            decision,
            accepted,
            state,
            req.text,
        )
        state.history.extend([
            {"role": "client", "text": req.text},
            {"role": "bot", "text": reply},
        ])
        total_ms = round((time.perf_counter() - started) * 1000)
        reason = "; ".join(
            f"{x.scenario_id}: {x.reason}"
            for x in decision.scenarios
        )
        return ChatResponse(
            session_id=req.session_id,
            transcript=req.text,
            reply=reply,
            language=reply_language,
            scenarios=decision.scenarios,
            alternatives=decision.alternatives,
            accepted_scenarios=accepted,
            slots=state.slots,
            reason=reason,
            handoff=handoff,
            latency_ms={
                "router": router_ms,
                "response": max(0, total_ms - router_ms),
                "total": total_ms,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Chat processing failed") from e


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    started = time.perf_counter()
    data = await file.read(MAX_AUDIO_BYTES + 1)

    if not data:
        raise HTTPException(status_code=400, detail="empty audio file")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio file too large")

    try:
        text = await run_in_threadpool(
            transcribe_audio,
            data,
            file.filename or "speech.webm",
        )
        ms = round((time.perf_counter() - started) * 1000)
        return {"text": text, "latency_ms": ms}
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Audio could not be transcribed",
        ) from e


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
        raise HTTPException(
            status_code=500,
            detail="Speech synthesis failed",
        ) from e
