import React from 'react';
import { TrendingUp, Target, Activity } from 'lucide-react';

export default function SolanaMetrics({ metrics }) {
  const { daily_pnl_usd = 0, total_trades = 0, wins = 0, losses = 0, win_rate = 0 } = metrics || {};
  const pnlColor = daily_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400';

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* PnL Card */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 relative overflow-hidden group hover:border-emerald-500/30 transition-colors">
        <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full blur-2xl -mr-10 -mt-10 group-hover:bg-emerald-500/20 transition-colors" />
        <div className="flex items-center gap-3 mb-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <TrendingUp size={16} className="text-emerald-400" />
          </div>
          <span className="text-sm font-semibold text-zinc-400">PnL Diário (Real)</span>
        </div>
        <div className="mt-4">
          <div className={`text-3xl font-bold font-mono tracking-tight ${pnlColor}`}>
            ${daily_pnl_usd.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Win Rate Card */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 relative overflow-hidden group hover:border-blue-500/30 transition-colors">
        <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/10 rounded-full blur-2xl -mr-10 -mt-10 group-hover:bg-blue-500/20 transition-colors" />
        <div className="flex items-center gap-3 mb-2">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Target size={16} className="text-blue-400" />
          </div>
          <span className="text-sm font-semibold text-zinc-400">Win Rate</span>
        </div>
        <div className="mt-4">
          <div className="text-3xl font-bold font-mono tracking-tight text-white">
            {win_rate}%
          </div>
        </div>
      </div>

      {/* Total Trades Card */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 relative overflow-hidden group hover:border-violet-500/30 transition-colors">
        <div className="absolute top-0 right-0 w-24 h-24 bg-violet-500/10 rounded-full blur-2xl -mr-10 -mt-10 group-hover:bg-violet-500/20 transition-colors" />
        <div className="flex items-center gap-3 mb-2">
          <div className="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
            <Activity size={16} className="text-violet-400" />
          </div>
          <span className="text-sm font-semibold text-zinc-400">Total de Trades</span>
        </div>
        <div className="mt-4 flex items-end justify-between">
          <div className="text-3xl font-bold font-mono tracking-tight text-white">
            {total_trades}
          </div>
          <div className="text-sm text-zinc-500 font-mono mb-1">
            <span className="text-emerald-400">{wins} W</span> / <span className="text-rose-400">{losses} L</span>
          </div>
        </div>
      </div>
    </div>
  );
}
