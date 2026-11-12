"use client";

import { ExchangeRateCard } from "@/components/currency";
import {
  useFrontendTool,
  useRenderTool,
  CopilotSidebar,
} from "@copilotkit/react-core/v2";
import dynamic from "next/dynamic";
import { extractA2uiMessages, extractRatePayload } from "@/components/a2uiResult";

// @a2ui/react touches browser globals at import time, so load it client-only.
const A2uiMessages = dynamic(
  () => import("@/components/A2uiMessages").then((m) => m.A2uiMessages),
  { ssr: false },
);
import React, { useState } from "react";
import { z } from "zod";

const Sidebar = CopilotSidebar as any;

export default function CopilotKitPage() {
  const [themeColor, setThemeColor] = useState("#10b981"); // Mint green primary theme

  // 🪁 Frontend Actions
  useFrontendTool({
    name: "setThemeColor",
    description: "Set the theme color of the workspace.",
    parameters: z.object({
      themeColor: z.string().describe("The theme color to set. Make sure to pick nice colors."),
    }),
    async handler({ themeColor }) {
      setThemeColor(themeColor);
    },
  });

  return (
    <main
      style={
        { "--copilot-kit-primary-color": themeColor } as React.CSSProperties
      }
    >
      <Sidebar
        defaultOpen={true}
        labels={{
          title: "Currency Intelligence Assistant",
          initial: "👋 Hi! I can help you convert currencies and look up exchange rates. Try asking for a conversion below!",
        } as any}
        suggestions={[
          {
            title: "Convert USD to EUR",
            message: "How much is 250 USD in EUR?",
          },
          {
            title: "Compare USD to GBP",
            message: "What is the exchange rate for USD to GBP?",
          },
          {
            title: "Convert CAD to USD",
            message: "Can you convert 1500 CAD to USD?",
          },
          {
            title: "USD/JPY trend",
            message: "Show me the USD to JPY trend over the last 30 days.",
          },
        ]}
      />
      <YourMainContent themeColor={themeColor} setThemeColor={setThemeColor} />
    </main>
  );
}


function YourMainContent({
  themeColor,
  setThemeColor,
}: {
  themeColor: string;
  setThemeColor: (color: string) => void;
}) {
  // 🪁 A2UI 1.0: the agent's send_a2ui_json_to_client tool returns validated
  // A2UI messages (macros already expanded on the server); render them here.
  useRenderTool(
    {
      name: "send_a2ui_json_to_client",
      render: ({ result }: any) => {
        const messages = extractA2uiMessages(result);
        return messages ? <A2uiMessages messages={messages} /> : null;
      },
    } as any,
    [],
  );

  // 🪁 Generative UI: Renders the ExchangeRateCard dynamically during agent tool calls
  useRenderTool(
    {
      name: "get_exchange_rate",
      render: ({ parameters, result }: any) => {
        const from = (parameters as any)?.currency_from || "USD";
        const to = (parameters as any)?.currency_to || "EUR";
        const payload = extractRatePayload(result);
        const rate = payload?.rates?.[to] ?? payload?.rates?.[to.toUpperCase()];
        const date = payload?.date;

        return (
          <ExchangeRateCard
            currencyFrom={from}
            currencyTo={to}
            rate={rate}
            date={date}
            themeColor={themeColor}
          />
        );
      },
    } as any,

    [themeColor],
  );

  return (
    <div
      style={{ backgroundColor: "#0f172a" }} // Matches deep dark-theme
      className="h-screen flex justify-center items-center flex-col transition-colors duration-300 px-6 text-center"
    >
      <div className="max-w-md bg-slate-800/80 border border-slate-700 p-8 rounded-2xl shadow-2xl backdrop-blur-md">
        <span className="text-5xl mb-4 block">💵</span>
        <h1 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          Currency Intellect
        </h1>
        <p className="text-slate-400 text-sm mb-6">
          Generative UI Workspace powered by A2UI 1.0, CopilotKit and Strands Agents on Amazon Bedrock. Ask the assistant to query rates.
        </p>
        <div className="flex justify-center gap-2">
          <button 
            onClick={() => setThemeColor("#10b981")} 
            className="w-8 h-8 rounded-full border-2 border-white/20 bg-emerald-500" 
          />
          <button 
            onClick={() => setThemeColor("#3b82f6")} 
            className="w-8 h-8 rounded-full border-2 border-white/20 bg-blue-500" 
          />
          <button 
            onClick={() => setThemeColor("#ec4899")} 
            className="w-8 h-8 rounded-full border-2 border-white/20 bg-pink-500" 
          />
        </div>
      </div>
    </div>
  );
}

