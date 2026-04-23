# Searcharvester 🌾

**Self-hosted search + extract + deep research for AI agents.**

Searcharvester exposes three composable HTTP APIs:

- `POST /search` — Tavily-compatible search via SearXNG.
- `POST /extract` — URL → clean markdown via `trafilatura`, with size presets and pagination.
- `POST /research` — deep-research jobs powered by Hermes Agent over ACP, with typed SSE events and a final cited markdown report.

Docs: [English](docs/en/README.md) · [Русский](docs/ru/README.md) · [中文](docs/zh/README.md)

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/vakovalskii/searcharvester.git
cd searcharvester

# 2. SearXNG config
cp config.example.yaml config.yaml
# Edit server.secret_key; use at least 32 random characters.

# 3. Optional: LLM credentials for /research
cp .env.example .env
# Fill OPENAI_API_KEY / OPENAI_BASE_URL or another supported provider.

# 4. Start
docker compose --env-file .env up -d

# 5. Smoke-check search/extract
scripts/smoke.sh
```

`/search` and `/extract` do not require external API keys. `/research` requires an OpenAI-compatible LLM endpoint or another provider configured for Hermes Agent.

---

## API examples

### `POST /search`

```bash
curl -X POST http://localhost:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"trafilatura python", "max_results":3}'
```

Response follows the Tavily-style schema:

```json
{
  "query": "trafilatura python",
  "results": [
    {"url": "https://...", "title": "...", "content": "...", "score": 0.9, "raw_content": null}
  ],
  "response_time": 1.23,
  "request_id": "..."
}
```

### `POST /extract`

```bash
curl -X POST http://localhost:8000/extract \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com", "size":"m"}'
```

Size presets:

| Size | Chars | Use case |
|---|---:|---|
| `s` | 5,000 | quick read |
| `m` | 10,000 | default agent context |
| `l` | 25,000 | deep single-page read |
| `f` | full, paginated by 25,000 | long documents |

For `size: "f"`, follow the returned `pages.next` URL, e.g. `GET /extract/{id}/2`. Extract cache is in-memory and expires after 30 minutes.

### `POST /research`

```bash
JOB=$(curl -s -X POST http://localhost:8000/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is trafilatura? One paragraph with sources."}' | jq -r .job_id)

curl -N http://localhost:8000/research/$JOB/events
curl http://localhost:8000/research/$JOB | jq -r .report
```

If `RESEARCH_API_TOKEN` is set, research endpoints require:

```http
Authorization: Bearer <token>
```

---

## Current v2.2 architecture

The current research path uses **ACP subprocess orchestration**. There is no per-job Docker container orchestration in the adapter.

```text
POST /research
  -> FastAPI creates jobs/{job_id}/
  -> Orchestrator starts `hermes acp` inside the tavily-adapter container
  -> Python ACP client receives typed session_update events
  -> events.py normalizes events to flat Event records
  -> /research/{job_id}/events streams replay + live events over SSE
  -> Hermes writes ./report.md in the job workspace
  -> GET /research/{job_id} returns final report
```

Always-running services in `docker-compose.yaml`:

- `redis` / Valkey — SearXNG cache.
- `searxng` — search backend.
- `tavily-adapter` — FastAPI API + Hermes CLI runtime.
- `frontend` — React/Vite UI for research jobs.

Important paths:

| Path | Purpose |
|---|---|
| `simple_tavily_adapter/main.py` | FastAPI routes for search/extract/research/health |
| `simple_tavily_adapter/orchestrator.py` | ACP subprocess orchestration and event streaming |
| `simple_tavily_adapter/events.py` | ACP event normalizer |
| `hermes-data/` | `HERMES_HOME`: config, SOUL, skills |
| `jobs/{job_id}/` | per-research workspace: `report.md`, `events.jsonl`, logs |
| `frontend/` | browser UI |

---

## Configuration

Create `config.yaml` from `config.example.yaml` and set a strong `server.secret_key`.

Create `.env` from `.env.example` for optional LLM credentials and deployment settings:

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
RESEARCH_API_TOKEN=
```

The default Compose file binds public ports to `127.0.0.1` for safer local development. For remote use, put the API/UI behind a reverse proxy instead of exposing raw service ports directly.

---

## Security notes

The default setup is intended for local/dev use. Before exposing it publicly:

- put API/UI behind HTTPS and authentication;
- avoid direct public exposure of SearXNG on port `8999`;
- set `RESEARCH_API_TOKEN` or enforce auth at the reverse proxy;
- configure rate limits for `/research`;
- set a strong SearXNG `server.secret_key`;
- treat `/research` prompts as untrusted input because Hermes tools run inside the adapter container;
- increase log retention beyond the small dev defaults if operating in production.

---

## Development checks

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r simple_tavily_adapter/requirements.txt
python -m pytest -q simple_tavily_adapter/tests

docker compose config >/tmp/searcharvester-compose.rendered.yaml
bash -n scripts/smoke.sh
```

Optional frontend check:

```bash
cd frontend
npm install
npm run build
```

---

## License

See [LICENSE](LICENSE).
