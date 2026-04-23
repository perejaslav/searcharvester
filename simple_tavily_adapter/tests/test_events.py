"""Pure-logic tests for the ACP → flat-event normalizer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from events import Event, normalize_acp_update


# Minimal stand-ins for pydantic ACP models. normalize_acp_update only cares
# about type(x).__name__ + .model_dump(), so plain dataclasses with a
# model_dump method pass through unchanged.
def _model_dump_factory(d: dict[str, Any]):
    def _dump(self, **_: Any) -> dict[str, Any]:
        return d
    return _dump


def _make(cls_name: str, data: dict[str, Any]) -> Any:
    cls = type(cls_name, (), {"model_dump": _model_dump_factory(data)})
    return cls()


def test_normalize_thought_chunk():
    upd = _make("AgentThoughtChunk", {"content": [{"type": "text", "text": "thinking"}]})
    ev = normalize_acp_update(upd, job_id="j1", agent_id="lead", parent_id=None)
    assert ev is not None
    assert ev.type == "thought"
    assert ev.payload["text"] == "thinking"
    assert ev.agent_id == "lead"
    assert ev.parent_id is None


def test_normalize_tool_call_start_extracts_key_fields():
    upd = _make("ToolCallStart", {
        "tool_call_id": "tc-1",
        "title": "search",
        "kind": "other",
        "raw_input": {"query": "x"},
        "content": [{"content": {"type": "text", "text": "preview"}}],
        "locations": [],
    })
    ev = normalize_acp_update(upd, job_id="j1", agent_id="lead", parent_id=None)
    assert ev is not None
    assert ev.type == "tool_call"
    assert ev.payload["id"] == "tc-1"
    assert ev.payload["title"] == "search"
    assert ev.payload["raw_input"] == {"query": "x"}
    assert "preview" in ev.payload["preview"]


def test_normalize_tool_call_progress_error():
    upd = _make("ToolCallProgress", {
        "tool_call_id": "tc-1",
        "status": "error",
        "content": [{"content": {"type": "text", "text": "boom"}}],
    })
    ev = normalize_acp_update(upd, job_id="j1", agent_id="lead", parent_id=None)
    assert ev is not None
    assert ev.type == "tool_result"
    assert ev.payload["status"] == "error"
    assert "boom" in ev.payload["content"]


def test_normalize_unknown_becomes_note():
    upd = _make("SomeFutureEvent", {"foo": "bar"})
    ev = normalize_acp_update(upd, job_id="j1", agent_id="lead", parent_id=None)
    assert ev is not None
    assert ev.type == "note"
    assert ev.payload["kind"] == "SomeFutureEvent"
    assert ev.payload["data"] == {"foo": "bar"}


def test_event_to_dict_is_jsonable():
    import json
    ev = Event.now(
        job_id="j1", agent_id="sub-1", parent_id="lead",
        type="message", payload={"text": "hi"},
    )
    # Should round-trip through json without losing data
    reconstructed = json.loads(json.dumps(ev.to_dict()))
    assert reconstructed["type"] == "message"
    assert reconstructed["agent_id"] == "sub-1"
    assert reconstructed["parent_id"] == "lead"
    assert reconstructed["payload"]["text"] == "hi"
