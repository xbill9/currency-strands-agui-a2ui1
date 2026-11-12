"""Checks for A2UI 1.0 output in an AG-UI event stream.

The agent sends its UI through the ``send_a2ui_json_to_client`` tool. The
``TOOL_CALL_RESULT`` event carries ``{"validated_a2ui_json": [...]}``: a list of
A2UI 1.0 messages, each with ``"version": "1.0"`` and one message body such as
``createSurface`` (which embeds its components).
"""

from __future__ import annotations

import json
from typing import Any


def a2ui_messages(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every A2UI message found in the stream's tool results."""
    messages: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "TOOL_CALL_RESULT":
            continue
        content = event.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                continue
        if isinstance(content, dict):
            messages.extend(content.get("validated_a2ui_json") or [])
    return messages


def check_a2ui_surface(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assert the stream created at least one A2UI 1.0 surface with components.

    Returns the components of the created surfaces.
    """
    messages = a2ui_messages(events)
    assert messages, "No validated_a2ui_json in any TOOL_CALL_RESULT event"

    bad = [m.get("version") for m in messages if m.get("version") != "1.0"]
    assert not bad, f"A2UI messages with version other than 1.0: {bad}"

    surfaces = [m["createSurface"] for m in messages if "createSurface" in m]
    assert surfaces, f"No createSurface message; got {[sorted(m) for m in messages]}"

    components = [c for s in surfaces for c in s.get("components") or []]
    assert components, "createSurface messages carry no components"
    return components


def component_texts(components: list[dict[str, Any]]) -> list[str]:
    """Return the text of every Text component."""
    return [
        str(c.get("text"))
        for c in components
        if c.get("component") == "Text" and c.get("text") is not None
    ]
