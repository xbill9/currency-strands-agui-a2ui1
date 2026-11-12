# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

AWS sibling of `~/currency-claude-agui-a2ui1` (ADK + Gemini). Here: Strands Agents + Amazon Nova on Bedrock, agent on AgentCore Runtime (AGUI protocol), Next.js UI on ECS Express Mode, A2UI 1.0.

## Running

Use the active `python3` and install packages into it; never create a virtualenv. AWS credentials come from `aws login` (session expires; `aws sts get-caller-identity` to check).

| What | Command |
|---|---|
| Agent + MCP (stdio child), :8090 `/invocations`, `/ping` | `cd app/agent && PORT=8090 python3 main.py` |
| UI, :3001 | `cd frontend-react && PORT=3001 AGENT_URL=http://127.0.0.1:8090/invocations npx next dev --webpack -p 3001` |
| Offline tests | `python3 -m pytest tests` |
| Render suite (stack up) | `python3 tools/render_suite.py 10 LABEL evidence/OUT.jsonl` (`UI_URL` picks the UI; default :3001) |
| Deploy agent | `agentcore deploy` (after `infra/configure_aws_target.sh`) |
| Deploy UI | `infra/deploy_ui.sh` |

Ports 3000, 8008, 8080 and 10000 belong to the ADK sibling when it runs; don't kill by process name (`pkill -f main.py` matches both stacks). Stop by port. `npm install` needs `--legacy-peer-deps` (`@a2ui/markdown-it` peers on web_core 0.14).

## Rules

- Keep `tools/render_suite.py` at 100% on the default model, locally and against the AWS URL.
- `send_a2ui_json_to_client` ends the turn with `agent.cancel(after_current_tools=True)` only on success; an error goes back to the model. Don't swap this for `ToolBehavior(stop_streaming_after_result=True)`: that also stops after errors and leaves the user with nothing.
- `RescuingBedrockModel` (`a2ui_rescue.py`) turns `<a2ui>` text into tool calls. Keep it.
- Macro arguments are untrusted: validate and clamp in `macros.py`. The charts catalog id and props must match `custom_catalog.json` and `frontend-react/src/components/A2UICustomCatalog.tsx`.
- `app/agent/pyproject.toml` is what AgentCore installs. Don't add `bedrock-agentcore[strands-agents]`: it caps `mcp` below 2.0, and FastMCP 4 needs `mcp` 2.3.
- The UI reaches AgentCore only through `/api/agentcore` (SigV4, task role). The browser never gets AWS credentials.

## Git

Commit straight to `main` and push.
