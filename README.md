# Searcharvester 🌾

**Self-hosted search + extract + deep research for AI agents**

> 📖 **Docs:** [English](docs/en/README.md) · [Русский](docs/ru/README.md) · [中文](docs/zh/README.md)

Three composable HTTP services in a single `docker compose up`:

- **`/search`** — Tavily-compatible search via SearXNG (100+ engines)
- **`/extract`** — URL → clean markdown via trafilatura, with size presets and pagination
- **`/research`** — deep research agent: give it a question, get back a cited markdown report

No API keys, no quotas, fully self-hosted. Pre-built image on GHCR.

## 🚀 Quick start

```bash
# 1. Clone
git clone git@github.com:vakovalskii/searcharvester.git
cd searcharvester

# 2. Config
cp config.example.yaml config.yaml
# Change server.secret_key (32+ chars)

# 3. (Optional) LLM credentials for /research — any OpenAI-compatible endpoint
cat > .env <<EOF
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
EOF

# 4. Start — pulls ghcr.io/vakovalskii/searcharvester
docker compose up -d

# 5. Test search
curl -X POST localhost:8000/search -H 'Content-Type: application/json' \
  -d '{"query":"bitcoin price","max_results":3}'

# 6. Test extract (URL → markdown)
curl -X POST localhost:8000/extract -H 'Content-Type: application/json' \
  -d '{"url":"https://en.wikipedia.org/wiki/Docker_(software)","size":"m"}'

# 7. Test deep research (needs LLM creds from step 3)
curl -X POST localhost:8000/research -H 'Content-Type: application/json' \
  -d '{"query":"What is trafilatura? One paragraph with source."}'
# → {"job_id":"...","status":"queued"}
# Poll GET /research/{job_id} until status=completed, grab the report.
```

---

## 🧱 Three services, one API

### 1️⃣ `POST /search` — Tavily-compatible search

Drop-in replacement for the [Tavily](https://tavily.com) API:

```python
from tavily import TavilyClient
client = TavilyClient(api_key="ignored", base_url="http://localhost:8000")
response = client.search(query="...", max_results=5, include_raw_content=True)
```

Request body:

```json
{
  "query": "...",
  "max_results": 10,
  "include_raw_content": false,
  "engines": "google,duckduckgo,brave",
  "categories": "general"
}
```

Response — Tavily schema (see [`docs/en/api.md`](docs/en/api.md)).

### 2️⃣ `POST /extract` — URL → clean markdown

Takes a URL, fetches the HTML, runs [trafilatura](https://github.com/adbar/trafilatura) for main-content extraction (strips nav/footer/ads, preserves headings, lists, tables, links), returns ready-to-use markdown.

**Size presets for different context windows:**

| Size | Chars | Use case |
|---|---|---|
| `s` | 5 000 | Quick summary, small-context LLMs |
| `m` | 10 000 | Default agent reading |
| `l` | 25 000 | Deep single-page read |
| `f` | full | Paginated by 25 000 — read long docs piece by piece |

**Pagination via cache:**

```bash
# Get id + page 1
curl -X POST localhost:8000/extract -d '{"url":"...","size":"f"}'
# → {"id":"abc123","content":"...","pages":{"current":1,"total":4,"next":"/extract/abc123/2"}}

# Next pages — no re-download
curl localhost:8000/extract/abc123/2
```

Cache keyed by `md5(url)[:16]`, TTL 30 minutes. Cold fetch: 1-3 s; cached page: <50 ms.

Useful as a standalone service, not just for the agent — plug it into any LLM pipeline that needs clean page text.

### 3️⃣ `POST /research` — deep research agent

`{query}` → orchestrator spawns an ephemeral [Hermes Agent](https://github.com/nousresearch/hermes-agent) container with three skills:

| Skill | Role |
|---|---|
| `searcharvester-search` | Tool: calls our `/search` |
| `searcharvester-extract` | Tool: calls our `/extract` |
| `searcharvester-deep-research` | Methodology (markdown only, no code): plan → gather → gap-check → synthesise → verify |

The agent reads the methodology, plans sub-queries, loops search→extract, synthesises a markdown report with `[1][2]` citations, saves it to `/workspace/report.md`. The orchestrator watches for the `REPORT_SAVED:` marker and returns the file to the client.

LLM-agnostic — works with any OpenAI-compatible endpoint: OpenAI, OpenRouter, Anthropic (via LiteLLM), vLLM, Ollama, LM Studio.

```bash
# Async flow
JOB=$(curl -sX POST localhost:8000/research -d '{"query":"compare vLLM vs SGLang"}' | jq -r .job_id)
while true; do
  R=$(curl -s localhost:8000/research/$JOB)
  STATUS=$(echo "$R" | jq -r .status)
  [ "$STATUS" = "running" ] && sleep 5 && continue
  echo "$R" | jq -r .report
  break
done
```

---

## 🧱 Stack — how the services are wired

Four always-running containers + one ephemeral per research job.

```
                        HOST (Mac / Linux server)
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║    Files on disk (bind-mounted into containers):                             ║
║    ┌──────────────┐  ┌─────────────────┐  ┌────────────────────────────┐     ║
║    │ config.yaml  │  │ hermes-data/    │  │ jobs/{job_id}/             │     ║
║    │ (SearXNG +   │  │  skills/        │  │  plan.md                   │     ║
║    │  adapter)    │  │   searcharv-*   │  │  notes.md                  │     ║
║    │              │  │  config.yaml    │  │  report.md                 │     ║
║    │              │  │  sessions/ ...  │  │  hermes.log                │     ║
║    └──────┬───────┘  └──────┬──────────┘  └──────────┬─────────────────┘     ║
║           │ ro (bind)       │ rw (bind)              │ rw (bind)             ║
║           ▼                 ▼                        ▼                       ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │  DOCKER ENGINE                                                         │  ║
║  │                                                                        │  ║
║  │  ┌──────────────────── network: searxng (bridge) ──────────────────┐   │  ║
║  │  │                                                                 │   │  ║
║  │  │  ┌────────────────┐    internal HTTP    ┌──────────────────┐    │   │  ║
║  │  │  │ tavily-adapter │◀──────────────────▶│ searxng           │    │   │  ║
║  │  │  │ :8000 (exposed)│   /search?format=  │ :8080             │    │   │  ║
║  │  │  │                │      json          │ (:8999 exposed)   │    │   │  ║
║  │  │  │ FastAPI:       │                    └────────┬──────────┘    │   │  ║
║  │  │  │  /search       │                             │ RESP          │   │  ║
║  │  │  │  /extract      │                             ▼               │   │  ║
║  │  │  │  /research     │                    ┌─────────────┐          │   │  ║
║  │  │  │  /health       │                    │ valkey      │          │   │  ║
║  │  │  │                │                    │ (redis)     │          │   │  ║
║  │  │  │ + trafilatura  │                    │ (cache)     │          │   │  ║
║  │  │  │ + orchestrator │                    └─────────────┘          │   │  ║
║  │  │  └───────┬────────┘                                             │   │  ║
║  │  │          │ Docker HTTP API                                      │   │  ║
║  │  │          │ (create / start /                                    │   │  ║
║  │  │          │  kill / rm / logs / wait)                            │   │  ║
║  │  │          ▼                                                      │   │  ║
║  │  │  ┌──────────────────────┐                                       │   │  ║
║  │  │  │ docker-socket-proxy  │  Whitelist:                           │   │  ║
║  │  │  │ :2375                │   CONTAINERS=1 POST=1 IMAGES=1        │   │  ║
║  │  │  │                      │   (everything else denied)            │   │  ║
║  │  │  └──────────┬───────────┘                                       │   │  ║
║  │  └─────────────│───────────────────────────────────────────────────┘   │  ║
║  │                │                                                       │  ║
║  │                │ reads (ro) /var/run/docker.sock                       │  ║
║  │                │  — adapter itself never touches it                    │  ║
║  │                │                                                       │  ║
║  │                ▼                                                       │  ║
║  │        (host docker daemon)                                            │  ║
║  │                │                                                       │  ║
║  │                │ spawns ephemeral container                            │  ║
║  │                ▼                                                       │  ║
║  │        ┌───────────────────────────────────────────────┐               │  ║
║  │        │ hermes-agent  (EPHEMERAL, one per /research)  │               │  ║
║  │        │                                               │               │  ║
║  │        │   /opt/data   ← hermes-data bind mount        │               │  ║
║  │        │   /workspace  ← jobs/{job_id} bind mount      │               │  ║
║  │        │                                               │               │  ║
║  │        │   Env: OPENAI_API_KEY, OPENAI_BASE_URL,       │               │  ║
║  │        │        SEARCHARVESTER_URL                     │               │  ║
║  │        │                                               │               │  ║
║  │        │   Skills loaded at startup:                   │               │  ║
║  │        │     - searcharvester-deep-research            │               │  ║
║  │        │     - searcharvester-search                   │               │  ║
║  │        │     - searcharvester-extract                  │               │  ║
║  │        │                                               │               │  ║
║  │        │   Exits 0 → container --rm                    │               │  ║
║  │        └──┬────────────────────┬───────────────────────┘               │  ║
║  │        └──┬────────────────────┬───────────────────────┘               │  ║
║  │           │                    │                                       │  ║
║  │           │                    │ HTTP via host.docker.internal:8000    │  ║
║  │           │                    └─────────▶ tavily-adapter above        │  ║
║  │           │                      (calls our /search and /extract)      │  ║
║  │           │                                                            │  ║
║  │           │                                                            │  ║
║  └───────────│────────────────────────────────────────────────────────────┘  ║
║              │                                                               ║
╚══════════════│═══════════════════════════════════════════════════════════════╝
               │ HTTPS
               ▼
      ┌─────────────────────────────────────────────┐
      │  EXTERNAL SERVICES                          │
      │                                             │
      │  • LLM endpoint                             │
      │    (OpenAI, OpenRouter, Anthropic,          │
      │     vLLM, Ollama — whatever                 │
      │     OpenAI-compatible API)                  │
      │                                             │
      │  • Search engines                           │
      │    (Google, DuckDuckGo, Brave, ...          │
      │     ← queried by searxng)                   │
      │                                             │
      │  • Target websites                          │
      │    (← scraped by tavily-adapter /extract    │
      │       and by /search with raw_content=true) │
      └─────────────────────────────────────────────┘
```

**Key points:**
- `tavily-adapter` sees the Docker API **only through `docker-socket-proxy`** — never `/var/run/docker.sock` directly. If the adapter is ever compromised, the attacker gets whitelisted container ops and nothing else.
- Every `/research` call = **a fresh, short-lived Hermes container**. After the agent exits, `--rm` wipes it. No cross-session state leakage.
- The spawned Hermes container reaches back to `tavily-adapter` via `host.docker.internal:8000` (uses `extra_hosts=host-gateway`). It's **not** on the `searxng` network.
- `/workspace` inside Hermes = `jobs/{job_id}/` on the host. Everything the agent writes there — plan, notes, report, log — is readable by the adapter after the job finishes.

### `/research` flow (sequence)

```
Client                tavily-adapter           socket-proxy      hermes (ephemeral)    LLM / web
  │                         │                       │                   │                  │
  │──POST /research────────▶│                       │                   │                  │
  │   {query}               │─ generate job_id      │                   │                  │
  │                         │─ mkdir jobs/{id}      │                   │                  │
  │                         │──create container────▶│──docker daemon──▶ (spawn)            │
  │                         │──start container─────▶│                   │                  │
  │◀─202 {job_id, queued}───│                       │                   │                  │
  │                         │                       │                   │──load skills     │
  │                         │                       │                   │──chat with LLM──▶│
  │                         │                       │                   │◀──tool_call──────│
  │                         │                       │                   │    "search(...)" │
  │                         │                       │                   │                  │
  │                         │◀──HTTP /search────────────────────────────│                  │
  │                         │──SearXNG query                            │                  │
  │                         │──results JSON────────────────────────────▶│                  │
  │                         │                                           │                  │
  │                         │                       │                   │──chat───────────▶│
  │                         │                       │                   │◀──tool_call──────│
  │                         │                       │                   │    "extract(url)"│
  │                         │◀──HTTP /extract───────────────────────────│                  │
  │                         │──trafilatura → md─────────────────────── ▶│                  │
  │                         │                                           │                  │
  │                         │                       │                   │──chat───────────▶│
  │                         │                       │                   │◀──tool: bash──   │
  │                         │                       │                   │    "cat > /workspace/report.md"
  │                         │                       │                   │     + print "REPORT_SAVED:"
  │                         │                       │                   │──exit 0 (--rm)   │
  │                         │◀─container done───────│                   │                  │
  │                         │──read logs + report.md                    │                  │
  │                         │─ check REPORT_SAVED marker                │                  │
  │                         │─ status = completed                       │                  │
  │                                                                                        │
  │  (polling in parallel)                                                                 │
  │──GET /research/{id}────▶│                                                              │
  │◀─200 {completed, report}│                                                              │
```

For C4 diagrams in Mermaid (Context / Container / Component + Deployment), see [`docs/en/architecture.md`](docs/en/architecture.md).

## 🧪 Tests

Written TDD-style (tests first, then implementation):

- 12 unit tests for the orchestrator with a fake Docker client
- 7 FastAPI route tests with mocked orchestrator
- 1 E2E test (real Hermes + real LLM)

```bash
docker compose exec tavily-adapter pytest tests/test_orchestrator.py tests/test_research_api.py -q
# 19 passed in ~3s
```

## 🎯 SimpleQA smoke bench

Stratified sample of 20 questions from OpenAI's SimpleQA:

- **6/6 correct** on the first six (rest interrupted — next benchmark round is parallel + LLM-judge)
- 30–120 s/question on `gpt-oss-120b` via an external vLLM

Harness in [`bench/`](bench/).

## 🎯 Why this vs. hosted services

| | Tavily / Exa / You.com | Searcharvester |
|---|---|---|
| 💰 Cost | Paid | Free (compute only) |
| 🔑 Keys | Required | None |
| 📊 Quotas | Yes | None |
| 🏢 Data location | External | Your host |
| 🎛 Search sources | Opaque | You control the engines |
| 🤖 Deep research | Add-on product | Built-in via `/research` |

## ⚙️ Configuration

`config.yaml` — single file, shared by SearXNG and the adapter. See [CONFIG_SETUP.md](CONFIG_SETUP.md) and [`docs/en/getting-started.md`](docs/en/getting-started.md).

LLM credentials for `/research` go in `.env` (or the environment of whoever runs `docker compose up`) — only passed through to the spawned Hermes container.

## 🐳 Pre-built image

Published to GitHub Container Registry — public:

- `ghcr.io/vakovalskii/searcharvester:latest`
- `ghcr.io/vakovalskii/searcharvester:2.1.0`

`docker-compose.yaml` uses `image:` by default — no build needed. For local dev: `docker compose up --build`.

## 🔧 Development

```bash
# Adapter — any change, fast iteration
cd simple_tavily_adapter
docker compose build tavily-adapter && docker compose up -d

# Run tests
docker compose exec tavily-adapter pytest -q

# Tail logs
docker compose logs -f tavily-adapter
```

## 📜 License

MIT on our code. AGPL on upstream SearXNG artifacts (Caddyfile, limiter.toml).

🔗 https://github.com/vakovalskii/searcharvester
