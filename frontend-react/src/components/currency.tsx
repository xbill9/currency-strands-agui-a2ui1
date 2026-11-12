import React from "react";

export function ExchangeRateCard({
  currencyFrom,
  currencyTo,
  rate,
  date,
  themeColor,
}: {
  currencyFrom: string;
  currencyTo: string;
  rate?: number;
  date?: string;
  themeColor: string;
}) {
  return (
    <div
      style={{ borderLeft: `4px solid ${themeColor}` }}
      className="rounded-xl shadow-xl mt-6 mb-4 max-w-md w-full bg-slate-800 border border-slate-700 overflow-hidden text-white"
    >
      <div className="bg-slate-900/50 p-4 w-full">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white capitalize">
              Exchange Rate Details
            </h3>
            <p className="text-slate-400 text-xs">
              Date: {date || new Date().toLocaleDateString()}
            </p>
          </div>
          <div className="text-2xl">💵</div>
        </div>

        <div className="mt-4 flex items-center justify-between bg-slate-900/30 p-3 rounded-lg border border-slate-700/50">
          <div className="flex flex-col">
            <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">From</span>
            <span className="text-lg font-bold text-emerald-400">{currencyFrom}</span>
          </div>
          <div className="text-slate-500 font-bold">➔</div>
          <div className="flex flex-col text-right">
            <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">To</span>
            <span className="text-lg font-bold text-emerald-400">{currencyTo}</span>
          </div>
        </div>

        <div className="mt-4 flex items-end justify-between">
          <div className="text-3xl font-extrabold text-white tracking-tight">
            {rate ? rate.toFixed(4) : "Fetching..."}
          </div>
          <div className="text-xs text-slate-400">
            1 {currencyFrom} = {rate ? rate.toFixed(4) : "?"} {currencyTo}
          </div>
        </div>
      </div>
    </div>
  );
}
