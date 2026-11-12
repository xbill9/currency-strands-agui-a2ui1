// Kept free of @a2ui imports so it is safe during server rendering.

/** Pulls the A2UI message list out of a tool result (object or JSON string). */
export function extractA2uiMessages(result: unknown): unknown[] | null {
  let value: any = result;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  const messages = value?.validated_a2ui_json;
  return Array.isArray(messages) && messages.length > 0 ? messages : null;
}

/**
 * Pulls the Frankfurter payload ({date, rates, ...}) out of a get_exchange_rate
 * MCP tool result. The result arrives as a JSON string or object shaped
 * {content: [{type: "text", text: "<json>"}], structuredContent: {...}}.
 */
export function extractRatePayload(
  result: unknown,
): { date?: string; rates?: Record<string, number> } | null {
  let value: any = result;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (value?.rates) return value;
  if (value?.structuredContent?.rates) return value.structuredContent;
  const text = value?.content?.find?.((c: any) => c?.type === "text")?.text;
  if (typeof text === "string") {
    try {
      const parsed = JSON.parse(text);
      if (parsed?.rates) return parsed;
    } catch {
      return null;
    }
  }
  return null;
}
