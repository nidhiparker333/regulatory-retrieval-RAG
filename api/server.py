"""
HTTP layer over the answering pipeline.

Thin on purpose: all the work lives in scripts/answer.py, which is also what
the evaluation runs against. If the API and the eval could diverge, the
measured numbers would stop describing what the UI actually does.

Run:  .venv\\Scripts\\python.exe -m uvicorn api.server:app --reload --port 8000
Then: http://localhost:8000/docs
"""

import json
import os
import pathlib
import sys
import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from answer import answer, retrieve, load_env, MODEL  # noqa: E402

app = FastAPI(
    title="Governance RAG",
    description="Grounded question answering over AI governance documents.",
    version="0.1.0",
)

# The UI runs on a different port in development, so its origin is allowed.
#
# CORS is NOT an access control. It instructs browsers not to let one origin
# read another's responses; it is invisible to curl, and a request carrying a
# forged Origin header is served normally. The list below therefore protects
# nothing on its own - what keeps this endpoint private is that uvicorn binds
# to 127.0.0.1 unless told otherwise.
#
# That matters here more than it usually would, because every generated answer
# spends real money. Two guards below make the protection real rather than
# assumed: a per-client rate limit, and an optional shared token.
app.add_middleware(
    CORSMiddleware,
    # The UI lands on whichever port is free, so allow the usual few.
    allow_origins=[
        f"http://{host}:{port}"
        for host in ("localhost", "127.0.0.1")
        for port in (3000, 3001, 3002)
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Requests per client per minute against the paid path. Generous for a person
# clicking around, immediately obvious to anything in a loop.
RATE_LIMIT = int(os.environ.get("ASK_RATE_LIMIT", "10"))

# If set, every paid request must carry `X-API-Token: <value>`. Unset by
# default so local use needs no ceremony; set it before exposing the port.
API_TOKEN = os.environ.get("API_TOKEN", "")

_hits: dict[str, list[float]] = defaultdict(list)


def _rate_limit(client: str) -> None:
    """Sliding one-minute window, in memory. Resets on restart, which is the
    right scope for a single-process local tool."""
    now = time.time()
    recent = [t for t in _hits[client] if now - t < 60]
    if len(recent) >= RATE_LIMIT:
        recent.sort()
        retry = max(1, int(60 - (now - recent[0])))
        _hits[client] = recent
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached ({RATE_LIMIT}/min). Try again in {retry}s.",
            headers={"Retry-After": str(retry)},
        )
    recent.append(now)
    _hits[client] = recent


class Ask(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    # Retrieval only: skips generation entirely, so it costs nothing. Useful
    # for exploring the corpus without spending.
    retrieval_only: bool = False


@app.get("/api/health")
def health():
    load_env()
    chunks = json.loads((ROOT / "data" / "clean" / "chunks.json").read_text(encoding="utf-8"))
    return {
        "ok": True,
        "chunks": len(chunks),
        "model": MODEL,
        "key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "auth_required": bool(API_TOKEN),
    }


@app.post("/api/ask")
def ask(body: Ask, request: Request):
    started = time.perf_counter()

    if body.retrieval_only:
        passages, steps = retrieve(body.question, k=5, follow=True)
        return {
            "question": body.question,
            "answer": None,
            "refused": False,
            "uncited": False,
            "citations_used": [],
            "passages": [
                {"n": i, "citation": p["citation"], "score": p.get("score"),
                 "source": p["source_group"], "title": p.get("title", ""),
                 "text": p["text"].split("\n\n", 1)[-1][:600]}
                for i, p in enumerate(passages, 1)
            ],
            "trace": steps,
            "cost_usd": 0.0,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    # Guards apply to the generating path only. Retrieval is free and local,
    # so throttling it would cost usability and protect nothing.
    if API_TOKEN and request.headers.get("X-API-Token") != API_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid API token.")
    _rate_limit(request.client.host if request.client else "unknown")

    try:
        result = answer(body.question, k=5, follow=True)
    except SystemExit as e:
        # answer() raises SystemExit when no key is configured.
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result
