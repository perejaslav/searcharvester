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
) -> list[Event]:
    """Convert one ACP `session_update` into one-or-more normalized Events.

    Returns a list because some updates (notably delegate_task) expand into
    multiple surface-level events: one for the lead's tool_call/result plus
    synthetic spawn/done events for each sub-agent so the UI can draw
    branches under the lead.

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
        return [_ev(job_id, agent_id, parent_id, "thought", {"text": text})]

    if kind == "AgentMessageChunk":
        d = dump(update)
        text = _extract_text_block(d.get("content"))
        return [_ev(job_id, agent_id, parent_id, "message", {"text": text})]

    if kind == "ToolCallStart":
        d = dump(update)
        lead_ev = _ev(job_id, agent_id, parent_id, "tool_call", {
            "id": d.get("tool_call_id"),
            "title": d.get("title"),
            "kind": d.get("kind"),
            "raw_input": d.get("raw_input"),
            "preview": _extract_tool_content_preview(d.get("content")),
            "locations": d.get("locations"),
        })
        events: list[Event] = [lead_ev]
        if _is_delegate_task(d.get("title")):
            tasks = _extract_delegate_tasks(d.get("raw_input"))
            call_id = d.get("tool_call_id") or ""
            for i, task in enumerate(tasks, start=1):
                sub_id = _sub_agent_id(call_id, i)
                events.append(_ev(job_id, sub_id, agent_id, "spawn", {
                    "goal": task.get("goal", "") if isinstance(task, dict) else "",
                    "toolsets": task.get("toolsets") if isinstance(task, dict) else None,
                    "delegate_call_id": call_id,
                    "task_index": i - 1,
                }))
        return events

    if kind == "ToolCallProgress":
        d = dump(update)
        call_id = d.get("tool_call_id") or ""
        # Full untruncated content for structured parsing; preview separately
        # for the UI field.
        full_content = _extract_tool_content_full(d.get("content"))
        lead_ev = _ev(job_id, agent_id, parent_id, "tool_result", {
            "id": call_id,
            "status": d.get("status"),
            "content": full_content[:2000],
        })
        events = [lead_ev]
        results = _extract_delegate_results_from_text(full_content)
        if results:
            for r in results:
                idx = r.get("task_index")
                if idx is None:
                    continue
                sub_id = _sub_agent_id(call_id, int(idx) + 1)
                status = r.get("status", "completed")
                summary = r.get("summary") or r.get("result") or ""
                if summary:
                    events.append(_ev(job_id, sub_id, agent_id, "message", {
                        "text": summary if isinstance(summary, str) else str(summary),
                    }))
                events.append(_ev(job_id, sub_id, agent_id, "done", {
                    "status": status,
                    "error": r.get("error"),
                    "delegate_call_id": call_id,
                }))
        return events

    if kind == "Plan":
        return [_ev(job_id, agent_id, parent_id, "plan", dump(update))]

    if kind == "AvailableCommandsUpdate":
        d = dump(update)
        cmds = d.get("available_commands") or d.get("commands") or []
        names = [c.get("name") if isinstance(c, dict) else str(c) for c in cmds]
        return [_ev(job_id, agent_id, parent_id, "commands", {"names": names})]

    return [_ev(job_id, agent_id, parent_id, "note", {
        "kind": kind,
        "data": dump(update),
    })]


def _is_delegate_task(title: Any) -> bool:
    if not title:
        return False
    t = str(title).lower().strip()
    # Hermes prints "delegate task" or "delegate_task" depending on version.
    return t.startswith("delegate") and ("task" in t)


def _extract_delegate_tasks(raw_input: Any) -> list[Any]:
    """delegate_task `tasks=[...]` — list of {goal, context, toolsets}.

    Some variants accept a single task via `goal=` + `context=`; treat that
    as a 1-element list so downstream code is uniform.
    """
    if not isinstance(raw_input, dict):
        return []
    tasks = raw_input.get("tasks")
    if isinstance(tasks, list):
        return tasks
    # Single-goal fallback
    if "goal" in raw_input:
        return [raw_input]
    return []


def _extract_delegate_results_from_text(text: str) -> list[dict[str, Any]] | None:
    """The delegate_task tool_result serialises as JSON like
    `{"results": [{"task_index": 0, "status": "completed", "summary": "..."}]}`.
    Dig that out so we can attribute per-sub outcomes.

    Hermes' ACP adapter caps tool_result content around 2000 chars per update,
    so the JSON arriving here is often truncated. Fall back to a regex
    scrape for {task_index, status, summary} when full json.loads fails —
    partial data is better than none.
    """
    if not text or "task_index" not in text:
        return None
    import json as _json
    import re
    obj: Any = None
    # First try: clean json.loads
    try:
        obj = _json.loads(text)
    except Exception:
        # Second try: trim to outermost braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = _json.loads(text[start:end + 1])
            except Exception:
                obj = None
    if isinstance(obj, dict) and isinstance(obj.get("results"), list):
        return [r for r in obj["results"] if isinstance(r, dict)]

    # Third try: regex-scrape task_index + status + (optional) summary.
    # Works on truncated JSON — we just get whatever key-value pairs survived.
    results: list[dict[str, Any]] = []
    # Match one {...} object that contains task_index + status, greedy on
    # the summary which may itself contain nested braces/strings.
    obj_re = re.compile(
        r'"task_index"\s*:\s*(\d+)[^{}]*?"status"\s*:\s*"(\w+)"'
        r'(?:[^{}]*?"summary"\s*:\s*"((?:[^"\\]|\\.)*)")?',
        re.DOTALL,
    )
    for m in obj_re.finditer(text):
        idx = int(m.group(1))
        status = m.group(2)
        summary = m.group(3)
        if summary is not None:
            # Un-escape basic JSON string escapes so the UI shows readable text
            summary = (
                summary.replace("\\n", "\n")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
        entry: dict[str, Any] = {"task_index": idx, "status": status}
        if summary:
            entry["summary"] = summary
        results.append(entry)
    return results or None


def _sub_agent_id(delegate_call_id: str, task_index_1based: int) -> str:
    """Stable, unique agent_id for a sub-agent.

    Scoped by the delegate_task call id so the same sub-1 from two different
    batches doesn't collide. Short hex prefix keeps the id UI-friendly.
    """
    import hashlib
    short = hashlib.blake2b(
        (delegate_call_id or "anon").encode("utf-8"), digest_size=2
    ).hexdigest()
    return f"sub-{short}-{task_index_1based}"


def _extract_tool_content_full(content: Any) -> str:
    """Join ACP content blocks into a single untruncated string — used for
    structured parsing (delegate results JSON). For UI previews, use
    _extract_tool_content_preview() which caps length."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
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
        return "\n".join(chunks)
    return str(content)


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
