// Forwards an AG-UI run to the agent on Amazon Bedrock AgentCore Runtime.
//
// AgentCore's invoke endpoint takes SigV4-signed requests, so the browser
// cannot call it directly. CopilotKit's runtime posts the AG-UI RunAgentInput
// here; this route signs it with the server's AWS credentials (the ECS task
// role when deployed, the local profile in development) and streams the
// agent's AG-UI events straight back.
import { Sha256 } from "@aws-crypto/sha256-js";
import { defaultProvider } from "@aws-sdk/credential-provider-node";
import { HttpRequest } from "@smithy/protocol-http";
import { SignatureV4 } from "@smithy/signature-v4";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const credentials = defaultProvider();

function runtimeTarget() {
  const arn = process.env.AGENTCORE_RUNTIME_ARN;
  if (!arn) throw new Error("AGENTCORE_RUNTIME_ARN is not set");
  const region = process.env.AWS_REGION || arn.split(":")[3];
  const host = `bedrock-agentcore.${region}.amazonaws.com`;
  const path = `/runtimes/${encodeURIComponent(arn)}/invocations`;
  return { region, host, path };
}

// AgentCore keeps one microVM per session id, which must be 33+ characters.
function sessionId(threadId: unknown): string {
  const base = typeof threadId === "string" && threadId ? threadId : crypto.randomUUID();
  return base.length >= 33 ? base.slice(0, 100) : `${base}-${"0".repeat(33)}`.slice(0, 40);
}

export async function POST(req: Request): Promise<Response> {
  const body = await req.text();
  const { region, host, path } = runtimeTarget();
  let threadId: unknown;
  try {
    threadId = JSON.parse(body).threadId;
  } catch {
    threadId = undefined;
  }

  const signer = new SignatureV4({
    service: "bedrock-agentcore",
    region,
    credentials,
    sha256: Sha256,
  });
  const signed = await signer.sign(
    new HttpRequest({
      method: "POST",
      protocol: "https:",
      hostname: host,
      path,
      query: { qualifier: process.env.AGENTCORE_QUALIFIER || "DEFAULT" },
      headers: {
        host,
        "content-type": "application/json",
        accept: "text/event-stream",
        "x-amzn-bedrock-agentcore-runtime-session-id": sessionId(threadId),
      },
      body,
    }),
  );

  const qualifier = encodeURIComponent(process.env.AGENTCORE_QUALIFIER || "DEFAULT");
  const upstream = await fetch(`https://${host}${path}?qualifier=${qualifier}`, {
    method: "POST",
    headers: signed.headers as Record<string, string>,
    body,
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "text/event-stream",
      "cache-control": "no-cache",
    },
  });
}
