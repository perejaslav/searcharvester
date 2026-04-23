# Searcharvester Lite Mode

Lite Mode is the low-resource deployment for small VPSes. It runs only:

- `POST /search` — Tavily-compatible search through SearXNG
- `POST /extract` — URL → clean markdown through trafilatura
- `GET /health`

It intentionally does **not** run Hermes Agent and disables `/research`.

## Why Lite Mode exists

The full stack uses the `nousresearch/hermes-agent` image and runs `hermes acp` for deep research jobs. That is useful, but heavy for a tiny server.

Lite Mode uses `python:3.11-slim` for the adapter and skips the frontend/Hermes runtime. It is intended for servers around:

- 1 CPU core
- 2 GB RAM
- limited disk space

## Start

```bash
cp config.example.yaml config.yaml
# edit server.secret_key

docker compose -f docker-compose.lite.yaml up -d --build
scripts/smoke.sh
```

Services:

| Service | Purpose | Port |
|---|---|---|
| `searcharvester-lite-searxng` | search backend | `127.0.0.1:8999` |
| `searcharvester-lite-redis` | SearXNG cache | internal only |
| `searcharvester-lite-adapter` | `/search`, `/extract`, `/health` | `127.0.0.1:8000` |

## Expected `/health`

```json
{
  "status": "ok",
  "service": "searcharvester",
  "version": "2.2.0",
  "mode": "lite",
  "research_enabled": false,
  "orchestrator": "unavailable"
}
```

## What happens to `/research`?

`RESEARCH_DISABLED=1` is set in `docker-compose.lite.yaml`. `/research` endpoints return `503` because the orchestrator is intentionally unavailable.

If you need deep research reports, use the normal `docker-compose.yaml` on a larger host.

## Resource notes

Lite Mode is still not free: SearXNG can use memory and some engines may be slow or blocked. But it avoids the heaviest piece — the Hermes Agent runtime image.

For public exposure, still put it behind a reverse proxy with HTTPS and authentication. The default bindings are local-only (`127.0.0.1`).
