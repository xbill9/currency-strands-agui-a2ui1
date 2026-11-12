"""Currency agent on Strands Agents and an Amazon model on Bedrock, answering in A2UI 1.0.

The A2UI pipeline is the one the ADK build uses, without ADK: the model writes
A2UI Express, the ``send_a2ui_json_to_client`` tool compiles it, validates it
against the inference catalogs (Basic 1.0 + charts + the macro sidecar), runs
the server-side macros, and validates the expanded messages again against the
catalogs the renderer implements.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from a2ui.core.basic_catalog import BasicCatalog
from a2ui.core.schema import AgentToRendererMessage
from a2ui.inference_formats import to_message_dicts
from a2ui.parser import RawA2uiPart
from a2ui.processor import A2uiRequestProcessor
from a2ui.transformers.macros import MacroExpander
from a2ui.utils import validate_payload
from botocore.config import Config as BotocoreConfig
from mcp import StdioServerParameters, stdio_client
from pydantic import TypeAdapter
from strands import Agent, ToolContext, tool
from strands.tools.mcp import MCPClient

from currency_agent.a2ui_rescue import RescuingBedrockModel
from currency_agent.macros import CHARTS_CATALOG, MACROS

logger = logging.getLogger(__name__)

TOOL_NAME = "send_a2ui_json_to_client"
VALIDATED_KEY = "validated_a2ui_json"
ERROR_KEY = "error"
DEFAULT_MODEL = "us.amazon.nova-2-lite-v1:0"

# Transport catalogs: what the renderer implements (Basic 1.0 + currency charts).
BASE_CATALOGS = [BasicCatalog("1.0"), CHARTS_CATALOG]
macro_expander = MacroExpander(MACROS, on_error="raise")
INFERENCE_CATALOGS = macro_expander.transform_catalogs(BASE_CATALOGS)
# A2uiRequestProcessor uses the A2UI Express inference format by default.
a2ui_processor = A2uiRequestProcessor(catalogs=INFERENCE_CATALOGS)
_message_adapter: TypeAdapter[AgentToRendererMessage] = TypeAdapter(
    AgentToRendererMessage
)

ROLE_INSTRUCTION = (
    "You are a specialized assistant for currency conversions. "
    "If the user asks about anything other than currency conversion or exchange rates, "
    "politely state that you cannot help with that topic and can only assist with "
    "currency-related queries. Do not attempt to answer unrelated questions or use "
    "tools for other purposes.\n\n"
    "Show results as A2UI. Prefer the server-side macros: RateCard for a rate or a "
    "conversion, RateHistoryChart for trends or history over time, RateComparison for "
    "comparing several currencies against one. These macros look up the figures on the "
    "server, so pass only currency codes and the amount or day count; do not call "
    "get_exchange_rate first. Use Basic catalog components (Card, Column, Row, Text) "
    "or the charts only for layouts the macros do not cover. Use get_exchange_rate "
    "only to answer in plain text when no UI is wanted."
)
TOOL_INSTRUCTION = (
    f"To show A2UI to the user, call the `{TOOL_NAME}` tool and pass the A2UI block"
    " in its `a2ui_payload` argument instead of writing the block in your reply."
)


def system_prompt() -> str:
    """The role, then the A2UI format's rules, catalog, examples and tool rule."""
    gen = a2ui_processor.format.prompt_generator
    sections = [
        ROLE_INSTRUCTION,
        "## Workflow Description:\n" + gen.generate_base_rules(),
        gen.generate_catalog_instructions(include_schema=True),
        "### Examples:\n" + gen.generate_examples(),
        TOOL_INSTRUCTION,
    ]
    return "\n\n".join(s for s in sections if s and s.strip())


def compile_a2ui(payload: str) -> list[dict]:
    """Compiles an Express block, expands the macros, validates both sides."""
    parser = a2ui_processor.parser
    blocks = (
        [
            raw.part.a2ui_raw
            for raw in parser.unwrap(payload)
            if isinstance(raw.part, RawA2uiPart)
        ]
        if parser.has_format_content(payload)
        else [payload]
    )
    compiled = []
    for block in blocks:
        compiled.extend(parser.compile(block))
    messages = to_message_dicts(compiled)
    if not messages:
        raise ValueError("The payload holds no A2UI messages.")
    validate_payload(a2ui_processor.active_catalogs, messages)
    typed = [_message_adapter.validate_python(m) for m in messages]
    expanded = macro_expander.transform_to_transport(typed)
    wire = [m.model_dump(by_alias=True, exclude_none=True) for m in expanded]
    validate_payload(BASE_CATALOGS, wire)
    return wire


@tool(name=TOOL_NAME, context=True)
def send_a2ui_json_to_client(a2ui_payload: str, tool_context: ToolContext) -> str:
    """Sends A2UI to the client to render rich UI for the user.

    This tool can be called multiple times in the same turn to render multiple
    UI surfaces.

    Args:
        a2ui_payload: The A2UI block to send to the client, in the A2UI format
            that the system instructions describe.
    """
    try:
        wire = compile_a2ui(a2ui_payload)
    except Exception as e:  # noqa: BLE001 - every failure goes back to the model as a tool error
        logger.warning("A2UI tool rejected a payload: %s", type(e).__name__)
        return json.dumps({ERROR_KEY: f"Failed to call A2UI tool {TOOL_NAME}: {e}"})
    logger.info("Validated call to tool %s", TOOL_NAME)
    # The UI is the answer: end the turn without another model call, as ADK's
    # skip_summarization does. A rejected payload goes back to the model instead.
    tool_context.agent.cancel(after_current_tools=True)
    return json.dumps({VALIDATED_KEY: wire})


def mcp_client() -> MCPClient:
    """The Frankfurter MCP server, started as a stdio child of the agent."""
    server = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_server.py")
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[server],
                env={**os.environ, "MCP_TRANSPORT": "stdio"},
            )
        )
    )


def model() -> RescuingBedrockModel:
    # A2UI written as reply text goes through the UI tool all the same.
    return RescuingBedrockModel(
        model_id=os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL),
        temperature=float(os.getenv("BEDROCK_TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("BEDROCK_MAX_TOKENS", "4096")),
        # Throttling and 5xx from Bedrock are retried before they reach the user.
        boto_client_config=BotocoreConfig(
            retries={"max_attempts": 6, "mode": "adaptive"}, read_timeout=120
        ),
    )


def build_agent(tools_extra: list | None = None) -> Agent:
    return Agent(
        model=model(),
        system_prompt=system_prompt(),
        tools=[send_a2ui_json_to_client, *(tools_extra or [])],
        callback_handler=None,
    )
