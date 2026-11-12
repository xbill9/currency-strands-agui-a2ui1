"""AG-UI endpoint for the Strands currency agent, on the AgentCore Runtime contract.

POST /invocations takes an AG-UI ``RunAgentInput`` and streams AG-UI events;
GET /ping is the health check. Port 8080, as AgentCore Runtime expects. The same
app runs locally (``python3 main.py``) and on AgentCore Runtime.
"""

import logging
import os

import uvicorn
from ag_ui_strands import (
    StrandsAgent,
    add_ping,
    add_strands_fastapi_endpoint,
)
from currency_agent.agent import build_agent, mcp_client
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(format="[%(levelname)s] %(name)s: %(message)s", level=logging.INFO)

agent = build_agent([mcp_client()])

agui_agent = StrandsAgent(
    agent=agent,
    name="currency_agent",
    description="An agent that can help with currency conversions",
)

# Built by hand instead of create_strands_app so FastAPI's own OTLP export stays
# off: on AgentCore Runtime the OpenTelemetry distro already exports, signed.
app = FastAPI(title="Strands currency agent", telemetry={"auto_configure": False})
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
add_strands_fastapi_endpoint(app, agui_agent, "/invocations")
add_ping(app, "/ping")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
