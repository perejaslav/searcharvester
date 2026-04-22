"""
FastAPI server that provides Tavily-compatible API using SearXNG backend.

Endpoints:
- POST /search                       — Tavily-совместимый поиск
- POST /extract                      — Извлечение страницы в markdown (s/m/l/f)
- GET  /extract/{id}/{page}          — Пагинация для size=f
- POST /research                     — Запустить deep-research задачу (ephemeral Hermes)
- GET  /research/{job_id}            — Статус / готовый report.md
- GET  /research/{job_id}/logs       — Hermes stdout/stderr (для отладки)
- DELETE /research/{job_id}          — Cancel активной задачи
- GET  /health                       — health-check
"""
import asyncio
import hashlib
import json
import logging
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path as FSPath
from typing import Any, Literal

import aiohttp
import trafilatura
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, constr
from sse_starlette.sse import EventSourceResponse

from tavily_client import TavilyResponse, TavilyResult
from config_loader import config
from orchestrator import Orchestrator, Job, JobStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Searcharvester", version="2.1.0")

# ---------- CORS ----------
# Frontend dev server is on :9762. Prod build served by the same origin or
# another port the user runs — allow anything on localhost by default, tighten
# via env var if needed.
_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:9762,http://127.0.0.1:9762,http://localhost:8000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Orchestrator singleton ----------

def _build_orchestrator() -> Orchestrator | None:
    """Build Orchestrator lazily. None when Docker is unreachable (tests / init)."""
    try:
        import docker  # type: ignore
    except ImportError:
        logger.warning("docker package missing — /research disabled")
        return None

    docker_host = os.environ.get("DOCKER_HOST")  # e.g. tcp://socket-proxy:2375
    try:
        client = docker.DockerClient(base_url=docker_host) if docker_host else docker.from_env()
        client.ping()
    except Exception as e:
        logger.warning("Docker unreachable (%s) — /research disabled", e)
        return None

    hermes_image = os.environ.get(
        "HERMES_IMAGE", "nousresearch/hermes-agent:latest"
    )
    jobs_dir = FSPath(os.environ.get("JOBS_DIR", "/srv/searxng-docker/jobs"))
    jobs_dir.mkdir(parents=True, exist_ok=True)
    jobs_host_dir_env = os.environ.get("JOBS_DIR_HOST")
    jobs_host_dir = FSPath(jobs_host_dir_env) if jobs_host_dir_env else None
    hermes_data_host = os.environ.get("HERMES_DATA_HOST_PATH")
    hermes_data_host_path = FSPath(hermes_data_host) if hermes_data_host else None

    # Whitelist of env vars we pass through to Hermes.
    pass_env_keys = [
        "OPENAI_API_KEY", "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "OLLAMA_API_KEY", "OLLAMA_BASE_URL",
        "NOUS_API_KEY",
    ]
    env = {k: os.environ[k] for k in pass_env_keys if k in os.environ}

    return Orchestrator(
        docker_client=client,
        hermes_image=hermes_image,
        skills=[
            "searcharvester-deep-research",
            "searcharvester-search",
            "searcharvester-extract",
        ],
        jobs_dir=jobs_dir,
        jobs_host_dir=jobs_host_dir,
        hermes_data_host_path=hermes_data_host_path,
        env=env,
        adapter_url_for_hermes=os.environ.get(
            "ADAPTER_URL_FOR_HERMES", "http://host.docker.internal:8000"
        ),
        timeout_sec=int(os.environ.get("RESEARCH_TIMEOUT_SEC", "900")),
        max_turns=int(os.environ.get("RESEARCH_MAX_TURNS", "30")),
    )


orchestrator: Orchestrator | None = _build_orchestrator()


# ---------- Extract constants ----------

SIZE_LIMITS: dict[str, int] = {"s": 5000, "m": 10000, "l": 25000}
PAGE_SIZE = 25000
EXTRACT_CACHE_TTL_SEC = 1800  # 30 минут

# id -> {"url", "title", "content", "created_at"}
_extract_cache: dict[str, dict[str, Any]] = {}


# ---------- Request models ----------

class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    include_raw_content: bool = False
    engines: str | None = Field(
        default=None,
        description="Через запятую: google,duckduckgo,brave,bing,... Пусто → дефолт из кода",
    )
    categories: str | None = Field(
        default=None,
        description="general|news|images|videos|map|music|it|science|files|social",
    )


class ExtractRequest(BaseModel):
    url: str
    size: Literal["s", "m", "l", "f"] = Field(
        default="m",
        description="s=5000, m=10000, l=25000 символов (обрезка), f=полный с пагинацией",
    )


# ---------- Helpers ----------

def _extract_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16]


def _gc_extract_cache() -> None:
    """Удаляет просроченные записи из in-memory кеша."""
    now = time.time()
    expired = [k for k, v in _extract_cache.items() if now - v["created_at"] > EXTRACT_CACHE_TTL_SEC]
    for k in expired:
        _extract_cache.pop(k, None)


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(
        url,
        timeout=aiohttp.ClientTimeout(total=config.scraper_timeout),
        headers={"User-Agent": config.scraper_user_agent},
        allow_redirects=True,
    ) as response:
        if response.status != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Не удалось скачать {url}: HTTP {response.status}",
            )
        return await response.text()


def _extract_markdown(html: str) -> tuple[str, str]:
    """Возвращает (title, markdown_content). Бросает HTTPException, если контента нет."""
    content = trafilatura.extract(
        html,
        output_format="markdown",
        include_formatting=True,
        include_links=True,
        include_tables=True,
        favor_recall=True,
    )
    if not content:
        raise HTTPException(
            status_code=422,
            detail="Не удалось извлечь основной контент страницы (пусто после очистки)",
        )

    title = ""
    try:
        metadata = trafilatura.extract_metadata(html)
        if metadata and metadata.title:
            title = metadata.title
    except Exception:
        pass

    return title, content


async def _extract_markdown_for_url(url: str) -> tuple[str, str]:
    async with aiohttp.ClientSession() as session:
        html = await _fetch_html(session, url)
    return _extract_markdown(html)


def _build_extract_response(
    extract_id: str,
    url: str,
    title: str,
    full_content: str,
    size: str,
    page: int = 1,
) -> dict[str, Any]:
    total_chars = len(full_content)

    if size == "f":
        total_pages = max(1, math.ceil(total_chars / PAGE_SIZE))
        if page > total_pages:
            raise HTTPException(
                status_code=404,
                detail=f"Страница {page} не существует (всего {total_pages})",
            )
        start = (page - 1) * PAGE_SIZE
        chunk = full_content[start : start + PAGE_SIZE]
        pages_info: dict[str, Any] = {
            "current": page,
            "total": total_pages,
            "page_size": PAGE_SIZE,
        }
        if page < total_pages:
            pages_info["next"] = f"/extract/{extract_id}/{page + 1}"
    else:
        limit = SIZE_LIMITS[size]
        chunk = full_content[:limit]
        pages_info = {"current": 1, "total": 1, "page_size": limit}

    return {
        "id": extract_id,
        "url": url,
        "title": title,
        "format": "md",
        "size": size,
        "content": chunk,
        "chars": len(chunk),
        "total_chars": total_chars,
        "pages": pages_info,
    }


# ---------- /search ----------

async def _fetch_raw_content(session: aiohttp.ClientSession, url: str) -> str | None:
    """Скрапит страницу, возвращает markdown-контент (trafilatura) или None при ошибке."""
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=config.scraper_timeout),
            headers={"User-Agent": config.scraper_user_agent},
            allow_redirects=True,
        ) as response:
            if response.status != 200:
                return None
            html = await response.text()
    except Exception:
        return None

    try:
        content = trafilatura.extract(
            html,
            output_format="markdown",
            include_formatting=True,
            include_links=True,
            favor_recall=True,
        )
    except Exception:
        return None

    if not content:
        return None

    if len(content) > config.scraper_max_length:
        content = content[: config.scraper_max_length] + "..."
    return content


@app.post("/search")
async def search(request: SearchRequest) -> dict[str, Any]:
    """Tavily-совместимый эндпойнт поиска."""
    start_time = time.time()
    request_id = str(uuid.uuid4())

    logger.info(
        "Search: q=%r engines=%s categories=%s raw=%s",
        request.query, request.engines, request.categories, request.include_raw_content,
    )

    searxng_params = {
        "q": request.query,
        "format": "json",
        "categories": request.categories or "general",
        "engines": request.engines or "google,duckduckgo,brave",
        "pageno": 1,
        "language": "auto",
        "safesearch": 1,
    }

    headers = {
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
        "User-Agent": "Mozilla/5.0 (compatible; TavilyBot/1.0)",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{config.searxng_url}/search",
                data=searxng_params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=500, detail="SearXNG request failed")
                searxng_data = await response.json()
        except aiohttp.TimeoutError:
            raise HTTPException(status_code=504, detail="SearXNG timeout")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("SearXNG error: %s", e)
            raise HTTPException(status_code=500, detail="Search service unavailable")

    searxng_results = searxng_data.get("results", [])

    raw_contents: dict[str, str] = {}
    if request.include_raw_content and searxng_results:
        urls_to_scrape = [
            r["url"] for r in searxng_results[: request.max_results] if r.get("url")
        ]
        async with aiohttp.ClientSession() as scrape_session:
            tasks = [_fetch_raw_content(scrape_session, u) for u in urls_to_scrape]
            page_contents = await asyncio.gather(*tasks, return_exceptions=True)
            for url, content in zip(urls_to_scrape, page_contents):
                if isinstance(content, str) and content:
                    raw_contents[url] = content

    results: list[TavilyResult] = []
    for i, result in enumerate(searxng_results[: request.max_results]):
        if not result.get("url"):
            continue
        raw_content = raw_contents.get(result["url"]) if request.include_raw_content else None
        results.append(
            TavilyResult(
                url=result["url"],
                title=result.get("title", ""),
                content=result.get("content", ""),
                score=0.9 - (i * 0.05),
                raw_content=raw_content,
            )
        )

    response_time = time.time() - start_time

    response = TavilyResponse(
        query=request.query,
        follow_up_questions=None,
        answer=None,
        images=[],
        results=results,
        response_time=response_time,
        request_id=request_id,
    )

    logger.info("Search done: %d results in %.2fs", len(results), response_time)
    return response.model_dump()


# ---------- /extract ----------

@app.post("/extract")
async def extract(req: ExtractRequest) -> dict[str, Any]:
    """Извлекает main-content страницы в markdown. Возвращает id для пагинации (size=f)."""
    _gc_extract_cache()
    extract_id = _extract_id(req.url)

    cached = _extract_cache.get(extract_id)
    if cached and cached["url"] == req.url:
        title, content = cached["title"], cached["content"]
    else:
        title, content = await _extract_markdown_for_url(req.url)
        _extract_cache[extract_id] = {
            "url": req.url,
            "title": title,
            "content": content,
            "created_at": time.time(),
        }

    return _build_extract_response(extract_id, req.url, title, content, req.size, page=1)


@app.get("/extract/{extract_id}/{page}")
async def extract_page(
    extract_id: str = Path(..., min_length=16, max_length=16),
    page: int = Path(..., ge=1),
) -> dict[str, Any]:
    """Возвращает page-ую страницу ранее извлечённого контента (только для size=f)."""
    _gc_extract_cache()
    cached = _extract_cache.get(extract_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="id не найден или просрочен (TTL 30 мин). Повторите POST /extract.",
        )
    return _build_extract_response(
        extract_id, cached["url"], cached["title"], cached["content"], size="f", page=page,
    )


# ---------- /research ----------

class ResearchRequest(BaseModel):
    query: constr(min_length=1, max_length=2000)  # type: ignore[valid-type]


class ResearchCreated(BaseModel):
    job_id: str
    status: str


class ResearchStatus(BaseModel):
    job_id: str
    status: str
    query: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_sec: float | None = None
    report: str | None = None
    error: str | None = None


def _ensure_orchestrator() -> Orchestrator:
    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Research orchestrator is not available (Docker unreachable). "
                "Check DOCKER_HOST / docker-socket-proxy."
            ),
        )
    return orchestrator


def _job_to_status(job: Job) -> ResearchStatus:
    return ResearchStatus(
        job_id=job.id,
        status=job.status.value,
        query=job.query,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        duration_sec=job.duration_sec,
        report=job.report,
        error=job.error,
    )


def _job_phase(job: Job) -> str:
    """Cheap phase heuristic based on workspace contents.

    - queued / cancelled / failed / timeout / completed → pass-through of status
    - running without plan.md → "planning"
    - running with plan.md, no notes.md → "gather"
    - running with notes.md, no report.md → "synthesise"
    - running with report.md → "verify"  (the agent is writing the REPORT_SAVED marker now)
    """
    if job.status != JobStatus.running:
        return job.status.value
    ws = job.workspace_path
    if ws is None:
        return "running"
    try:
        if (ws / "report.md").exists():
            return "verify"
        if (ws / "notes.md").exists():
            return "synthesise"
        if (ws / "plan.md").exists():
            return "gather"
    except Exception:
        pass
    return "planning"


def _job_artifacts(job: Job) -> dict[str, int]:
    """Map artifact name → size in bytes, for debug pane in the UI."""
    if job.workspace_path is None:
        return {}
    out: dict[str, int] = {}
    for name in ("plan.md", "notes.md", "report.md", "hermes.log"):
        p = job.workspace_path / name
        try:
            if p.exists():
                out[name] = p.stat().st_size
        except Exception:
            pass
    return out


@app.post("/research", response_model=ResearchCreated, status_code=202)
async def research_create(req: ResearchRequest) -> dict[str, str]:
    orch = _ensure_orchestrator()
    job_id = await orch.spawn(query=req.query)
    return {"job_id": job_id, "status": "queued"}


@app.get("/research/{job_id}", response_model=ResearchStatus)
async def research_get(job_id: str) -> ResearchStatus:
    orch = _ensure_orchestrator()
    job = orch.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_to_status(job)


@app.get("/research/{job_id}/logs")
async def research_logs(job_id: str) -> dict[str, str]:
    orch = _ensure_orchestrator()
    job = orch.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    logs = orch.read_logs(job_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Logs not available yet")
    return {"job_id": job_id, "logs": logs}


@app.get("/research/{job_id}/events")
async def research_events(job_id: str):
    """Server-Sent Events stream for a single research job.

    Emits one event per second while running, plus a terminal event on exit.
    Events:
      - status: {status, phase, elapsed_sec, artifacts}
      - completed: {status, phase, duration_sec, report, artifacts}
      - failed | timeout | cancelled: {status, error, artifacts}

    Client sample (JS):
        const es = new EventSource(`/research/${jobId}/events`);
        es.addEventListener("status", e => setState(JSON.parse(e.data)));
        es.addEventListener("completed", e => {setFinal(JSON.parse(e.data)); es.close();});
    """
    orch = _ensure_orchestrator()
    job = orch.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    async def event_stream():
        last_payload: dict[str, Any] | None = None
        terminal = {JobStatus.completed, JobStatus.failed, JobStatus.timeout, JobStatus.cancelled}
        while True:
            current = orch.get(job_id)
            if current is None:
                # Job vanished (shouldn't happen during normal life).
                yield {"event": "failed", "data": json.dumps({"status": "failed", "error": "job removed"})}
                return

            phase = _job_phase(current)
            elapsed = None
            if current.started_at:
                base = current.finished_at or datetime.now(timezone.utc)
                elapsed = (base - current.started_at).total_seconds()

            payload: dict[str, Any] = {
                "status": current.status.value,
                "phase": phase,
                "elapsed_sec": round(elapsed, 1) if elapsed is not None else None,
                "artifacts": _job_artifacts(current),
            }

            if current.status in terminal:
                # Attach terminal-only fields.
                payload["duration_sec"] = current.duration_sec
                payload["report"] = current.report
                payload["error"] = current.error
                event_name = current.status.value  # "completed", "failed", "timeout", "cancelled"
                yield {"event": event_name, "data": json.dumps(payload, ensure_ascii=False)}
                return

            # Only emit a "status" event when payload changed or every 5s
            # (keepalive). Keeps the stream quiet when nothing's happening.
            if payload != last_payload:
                yield {"event": "status", "data": json.dumps(payload, ensure_ascii=False)}
                last_payload = payload

            await asyncio.sleep(1.0)

    return EventSourceResponse(event_stream())


@app.delete("/research/{job_id}")
async def research_cancel(job_id: str) -> dict[str, Any]:
    orch = _ensure_orchestrator()
    job = orch.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    cancelled = await orch.cancel(job_id)
    return {"job_id": job_id, "cancelled": cancelled, "status": orch.get(job_id).status.value}


# ---------- /health ----------

@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "searcharvester",
        "version": "2.1.0",
        "orchestrator": "available" if orchestrator is not None else "unavailable",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.server_host, port=config.server_port)
