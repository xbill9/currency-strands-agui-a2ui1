"""Turns an A2UI block that the model writes as reply text into the UI tool call.

The model is told to pass A2UI to the ``send_a2ui_json_to_client`` tool. When it
writes the ``<a2ui>`` block into its reply instead, this model wrapper

* holds back streamed text from the point ``<a2ui`` starts, so the raw block
  never reaches the chat, and
* ends the message with one ``toolUse`` block per A2UI block and stop reason
  ``tool_use``, so Strands runs the tool, which compiles, expands and validates
  it like any other A2UI.

It works on the Bedrock ConverseStream events that Strands models yield.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from strands.models.bedrock import BedrockModel

TOOL_NAME = "send_a2ui_json_to_client"
PAYLOAD_ARG = "a2ui_payload"
MARKER = "<a2ui"
CLOSE = "</a2ui>"

logger = logging.getLogger(__name__)
_BLOCK = re.compile(r"<a2ui>.*?(?:</a2ui>|\Z)", re.DOTALL)


def _held_back(text: str) -> int:
    """Length of the tail of ``text`` that could be the start of ``<a2ui``."""
    for n in range(min(len(MARKER) - 1, len(text)), 0, -1):
        if MARKER.startswith(text[-n:]):
            return n
    return 0


def _text_delta(text: str) -> dict:
    return {"contentBlockDelta": {"delta": {"text": text}}}


def tool_use_events(block: str) -> list[dict]:
    """The stream events for one call of the UI tool carrying ``block``."""
    payload = block if block.rstrip().endswith(CLOSE) else block.rstrip() + "\n" + CLOSE
    return [
        {
            "contentBlockStart": {
                "start": {
                    "toolUse": {
                        "toolUseId": f"tooluse_a2ui_{uuid.uuid4().hex[:20]}",
                        "name": TOOL_NAME,
                    }
                }
            }
        },
        {
            "contentBlockDelta": {
                "delta": {"toolUse": {"input": json.dumps({PAYLOAD_ARG: payload})}}
            }
        },
        {"contentBlockStop": {}},
    ]


async def rescue_stream(
    events: AsyncGenerator[dict[str, Any]],
) -> AsyncGenerator[dict[str, Any]]:
    """Passes events through, moving A2UI written as text into tool calls."""
    text, sent, in_text = "", 0, False
    blocks: list[str] = []
    async for event in events:
        if "contentBlockStart" in event:
            in_text = "toolUse" not in event["contentBlockStart"].get("start", {})
            text, sent = "", 0
            yield event
            continue
        delta = event.get("contentBlockDelta", {}).get("delta", {})
        if "text" in delta:
            in_text = True
            text += delta["text"]
            start = text.find(MARKER)
            end = start if start >= 0 else len(text) - _held_back(text)
            if end > sent:
                yield _text_delta(text[sent:end])
                sent = end
            continue
        if "contentBlockStop" in event and in_text:
            if MARKER in text:
                blocks.extend(_BLOCK.findall(text[text.find(MARKER) :]))
            elif sent < len(text):
                yield _text_delta(text[sent:])
            text, sent, in_text = "", 0, False
            yield event
            continue
        if "messageStop" in event and blocks:
            for block in blocks:
                for e in tool_use_events(block):
                    yield e
            logger.info(
                "A2UI written as reply text: sent %d block(s) through %s",
                len(blocks),
                TOOL_NAME,
            )
            blocks = []
            stop = dict(event["messageStop"])
            stop["stopReason"] = "tool_use"
            yield {"messageStop": stop}
            continue
        yield event


class RescuingBedrockModel(BedrockModel):
    """BedrockModel whose replies never carry a raw ``<a2ui>`` block."""

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        async for event in rescue_stream(super().stream(*args, **kwargs)):
            yield event
