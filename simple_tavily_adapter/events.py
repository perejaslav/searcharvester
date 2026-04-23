"""
Flat, transport-agnostic event schema for research jobs.

One UI, one SSE stream — the orchestrator normalizes everything (lead agent
ACP events, future sub-agent session tails, orchestration lifecycle) into
these events and appends them to an in-memory per-job ring. Clients render
a tree by grouping on agent_id / parent_id.

The schema stays stable even if we swap Hermes for Claude Code SDK, OpenAI
Assistants, etc. — only the normalizer changes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

EventType = Literal[
    "spawn",         # orchestrator spawned an agent (lead or sub)
    "thought",       # chain-of-thought chunk (reasoning_content)
    "message",       # final-answer chunk (assistant text)
    "tool_call",     # agent invoked a tool
    "tool_result",   # tool returned (update for a tool_call)
    "plan",          # agent emitted/updated a plan
    "commands",      # available-commands list updated
    "note",          # free-form note (warnings, retries)
    "done",          # agent session finished (lead: job complete)
]


@dataclass
class Event:
    ts: str
    job_id: str
    agent_id: str           # "lead", "sub-1", "sub-2", ...
    parent_id: str | None   # None for lead, "lead" for first-level sub-agents
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(
        cls,
        *,
        job_id: str,
        agent_id: str,
        type: EventType,
        payload: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> "Event":
        return cls(
            ts=datetime.now(timezone.utc).isoformat(),
            job_id=job_id,
            agent_id=agent_id,
            parent_id=parent_id,
            type=type,
            payload=payload or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_acp_update(
    update: Any,
    *,
    job_id: str,
    agent_id: str,
    parent_id: str | None,
) -> Event | None:
    """Convert one ACP `session_update` (typed pydantic model) into an Event.

    Returns None for updates we intentionally don't surface (e.g. keepalives).

    Keeps coupling to the ACP SDK shallow: one function, one switch. If the
    ACP schema changes in a future Hermes release, this is the only place
    that needs to adapt.
    """
    kind = type(update).__name__

    def dump(u: Any) -> dict[str, Any]:
        if hasattr(u, "model_dump"):
            return u.model_dump(mode="json", exclude_none=True)
        return {"raw": repr(u)}

    if kind == "AgentThoughtChunk":
        d = dump(update)
        text = _extract_text_block(d.get("content"))
        return _ev(job_id, agent_id, parent_id, "thought", {"text": text})

    if kind == "AgentMessageChunk":
        d = dump(update)
        text = _extract_text_block(d.get("content"))
        return _ev(job_id, agent_id, parent_id, "message", {"text": text})

    if kind == "ToolCallStart":
        d = dump(update)
        return _ev(job_id, agent_id, parent_id, "tool_call", {
            "id": d.get("tool_call_id"),
            "title": d.get("title"),
            "kind": d.get("kind"),
            "raw_input": d.get("raw_input"),
            "preview": _extract_tool_content_preview(d.get("content")),
            "locations": d.get("locations"),
        })

    if kind == "ToolCallProgress":
        d = dump(update)
        return _ev(job_id, agent_id, parent_id, "tool_result", {
            "id": d.get("tool_call_id"),
            "status": d.get("status"),
            "content": _extract_tool_content_preview(d.get("content")),
        })

    if kind == "Plan":
        return _ev(job_id, agent_id, parent_id, "plan", dump(update))

    if kind == "AvailableCommandsUpdate":
        d = dump(update)
        cmds = d.get("available_commands") or d.get("commands") or []
        # Flatten to just names — UI doesn't need argument schemas
        names = [c.get("name") if isinstance(c, dict) else str(c) for c in cmds]
        return _ev(job_id, agent_id, parent_id, "commands", {"names": names})

    # Everything else: surface as a generic note so nothing silently disappears.
    return _ev(job_id, agent_id, parent_id, "note", {
        "kind": kind,
        "data": dump(update),
    })


def _ev(
    job_id: str,
    agent_id: str,
    parent_id: str | None,
    type_: EventType,
    payload: dict[str, Any],
) -> Event:
    return Event.now(
        job_id=job_id,
        agent_id=agent_id,
        parent_id=parent_id,
        type=type_,
        payload=payload,
    )


def _extract_text_block(content: Any) -> str:
    """ACP content blocks are [{type:'text', text:'...'}] or similar. Collapse
    into a single string for `thought`/`message` events.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") == "text" and "content" in item:
                    parts.append(str(item["content"]))
        return "".join(parts)
    return str(content)


def _extract_tool_content_preview(content: Any) -> str:
    """ToolCallStart.content is a list of {type:'content', content:{type:'text', text:'...'}}.
    Return a compact preview string for UI."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content[:2000]
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            inner = item.get("content")
            if isinstance(inner, dict):
                t = inner.get("text")
                if t:
                    chunks.append(str(t))
        return "\n".join(chunks)[:2000]
    return str(content)[:2000]
