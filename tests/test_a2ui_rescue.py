"""The safety net that sends A2UI written as reply text through the UI tool."""

import asyncio
import json

from currency_agent.a2ui_rescue import PAYLOAD_ARG, TOOL_NAME, rescue_stream

BLOCK = '<a2ui>\nroot = RateCard("USD", "EUR", 100)\n</a2ui>'


def run(chunks, stop="end_turn"):
    async def source():
        yield {"messageStart": {"role": "assistant"}}
        for c in chunks:
            yield {"contentBlockDelta": {"delta": {"text": c}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": stop}}

    async def collect():
        return [e async for e in rescue_stream(source())]

    return asyncio.run(collect())


def shown(events):
    return "".join(
        e["contentBlockDelta"]["delta"].get("text", "")
        for e in events
        if "contentBlockDelta" in e
    )


def calls(events):
    names = [
        e["contentBlockStart"]["start"]["toolUse"]["name"]
        for e in events
        if "contentBlockStart" in e
    ]
    inputs = [
        json.loads(e["contentBlockDelta"]["delta"]["toolUse"]["input"])
        for e in events
        if "toolUse" in e.get("contentBlockDelta", {}).get("delta", {})
    ]
    return names, inputs


def test_streamed_block_is_held_back_and_becomes_a_tool_call():
    events = run(["Here it is. ", "<a2", BLOCK[3:20], BLOCK[20:]])
    assert shown(events) == "Here it is. "
    names, inputs = calls(events)
    assert names == [TOOL_NAME]
    assert inputs == [{PAYLOAD_ARG: BLOCK}]
    assert events[-1]["messageStop"]["stopReason"] == "tool_use"


def test_unclosed_block_is_closed():
    _, inputs = calls(run(['<a2ui>\nroot = RateCard("USD", "EUR")']))
    assert inputs[0][PAYLOAD_ARG].endswith("</a2ui>")


def test_two_blocks_become_two_calls():
    names, _ = calls(run([BLOCK, "\n", BLOCK.replace("EUR", "GBP")]))
    assert len(names) == 2


def test_plain_text_passes_unchanged():
    text = ["The rate is ", "1 <", " 2 and <a", "lso that."]
    events = run(text)
    assert shown(events) == "".join(text)
    assert calls(events) == ([], [])
    assert events[-1]["messageStop"]["stopReason"] == "end_turn"
