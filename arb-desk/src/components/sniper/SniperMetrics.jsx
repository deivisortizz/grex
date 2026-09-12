import React from 'react'
import { useSniperContext } from '../../context/SniperContext'
import { TrendingUp, TrendingDown, Target, Activity, DollarSign } from 'lucide-react'

export default function SniperMetrics() {
  const { metrics } = useSniperContext()

  const { total_trades = 0, win_trades = 0, daily_pnl_usd = 0 } = metrics || {}
  const winRate = total_trades > 0 ? ((win_trades / total_trades) * 100).toFixed(1) : 0
  
  const isProfit = daily_pnl_usd >= 0

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* PnL Card */}
      <div className={`bg-zinc-900 border rounded-2xl p-5 flex flex-col justify-between ${isProfit ? 'border-emerald-500/30' : 'border-rose-500/30'}`}>
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-2 text-zinc-400">
            <DollarSign size={16} />
            <span className="text-sm font-semibold">PnL Diário (USD)</span>
          </div>
          <div className={`p-2 rounded-lg ${isProfit ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
            {isProfit ? <TrendingUp size={18} className="text-emerald-400" /> : <TrendingDown size={18} className="text-rose-400" />}
          </div>
        </div>
        <div className="mt-4">
          <span className={`text-3xl font-bold font-mono ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isProfit ? '+' : ''}${Number(daily_pnl_usd).toFixed(2)}
          </span>
        </div>
      </div>

      {/* Win Rate Card */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 flex flex-col justify-between">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-2 text-zinc-400">
            <Target size={16} />
            <span className="text-sm font-semibold">Win Rate</span>
          </div>
          <div className="p-2 rounded-lg bg-blue-500/10">
            <Activity size={18} className="text-blue-400" />
          </div>
        </div>
        <div className="mt-4 flex items-end gap-2">
          <span className="text-3xl font-bold font-mono text-white">{winRate}%</span>
          <span className="text-sm text-zinc-500 mb-1">({win_trades} wins)</span>
        </div>
      </div>

      {/* Total Trades Card */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 flex flex-col justify-between">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-2 text-zinc-400">
            <Activity size={16} />
            <span className="text-sm font-semibold">Total de Operações</span>
          </div>
        </div>
        <div className="mt-4">
          <span className="text-3xl font-bold font-mono text-white">{total_trades}</span>
          <span className="text-sm text-zinc-500 ml-2 block sm:inline">snipes hoje</span>
        </div>
      </div>
    </div>
  )
}
