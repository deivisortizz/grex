import React, { useRef, useEffect, useState } from 'react'
import { useSniperContext } from '../../context/SniperContext'
import { AlertTriangle, Zap, TrendingUp, TrendingDown, Minus } from 'lucide-react'

function shortenAddr(addr) {
  if (!addr) return ''
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`
}

function PositionRow({ position, onPanicSell }) {
  const { token, entry_price, current_price, pnl_pct = 0 } = position
  const prevPriceRef = useRef(current_price)
  const priceHistoryRef = useRef([{ value: current_price, ts: Date.now() }])
  const [dumpAlert, setDumpAlert] = useState(false) // 'warn' | 'danger' | false

  useEffect(() => {
    // Add latest price to 3-second history
    priceHistoryRef.current = [
      ...priceHistoryRef.current.filter(p => Date.now() - p.ts < 3000),
      { value: current_price, ts: Date.now() }
    ]
    const oldest = priceHistoryRef.current[0]
    if (oldest && oldest.value > 0) {
      const drop = ((current_price - oldest.value) / oldest.value) * 100
      if (drop <= -10) setDumpAlert('danger')
      else if (drop <= -5) setDumpAlert('warn')
      else setDumpAlert(false)
    }
    prevPriceRef.current = current_price
  }, [current_price])

  const pnlColor = pnl_pct > 0
    ? 'text-emerald-400'
    : pnl_pct < 0
      ? 'text-rose-400'
      : 'text-zinc-400'

  const pnlIcon = pnl_pct > 0
    ? <TrendingUp size={14} className="text-emerald-400 shrink-0" />
    : pnl_pct < 0
      ? <TrendingDown size={14} className="text-rose-400 shrink-0" />
      : <Minus size={14} className="text-zinc-500 shrink-0" />

  const rowBg = dumpAlert === 'danger'
    ? 'bg-rose-900/20 border-rose-500/30'
    : dumpAlert === 'warn'
      ? 'bg-amber-900/20 border-amber-500/30'
      : 'bg-zinc-900/50 border-zinc-800/50'

  return (
    <div className={`flex items-center gap-3 border rounded-xl px-4 py-3 transition-all duration-500 ${rowBg}`}>
      {/* Dump Alert Indicator */}
      <div className="shrink-0 w-8 flex justify-center">
        {dumpAlert === 'danger' && (
          <div className="relative">
            <div className="absolute inset-0 bg-rose-500 rounded-full animate-ping opacity-40" />
            <AlertTriangle size={18} className="text-rose-400 relative" />
          </div>
        )}
        {dumpAlert === 'warn' && (
          <AlertTriangle size={18} className="text-amber-400 animate-pulse" />
        )}
        {!dumpAlert && (
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mt-1" />
        )}
      </div>

      {/* Token Address */}
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-500 mb-0.5">Token</p>
        <p className="font-mono text-sm text-white truncate">{shortenAddr(token)}</p>
      </div>

      {/* Entry */}
      <div className="hidden sm:block min-w-[90px]">
        <p className="text-xs text-zinc-500 mb-0.5">Entrada (wei)</p>
        <p className="font-mono text-xs text-zinc-300">{Number(entry_price).toLocaleString()}</p>
      </div>

      {/* PnL */}
      <div className="min-w-[80px] text-right">
        <p className="text-xs text-zinc-500 mb-0.5">PnL</p>
        <div className="flex items-center justify-end gap-1">
          {pnlIcon}
          <span className={`font-mono text-sm font-bold ${pnlColor}`}>
            {pnl_pct > 0 ? '+' : ''}{Number(pnl_pct).toFixed(2)}%
          </span>
        </div>
      </div>

      {/* Panic Sell Button */}
      <button
        onClick={() => onPanicSell(token)}
        className="ml-2 shrink-0 flex items-center gap-1.5 px-3 py-2 bg-rose-500/15 hover:bg-rose-500/30 
                   border border-rose-500/40 text-rose-400 hover:text-rose-300 rounded-lg text-xs font-bold 
                   transition-all cursor-pointer active:scale-95"
        title="Venda de emergência (100% a mercado)"
      >
        <Zap size={13} className="fill-current" />
        PANIC
      </button>
    </div>
  )
}

export default function SniperPositionsTable() {
  const { openPositions, forceSell } = useSniperContext()

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-2xl flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-500/10 flex items-center justify-center">
            <TrendingUp size={18} className="text-amber-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white tracking-tight">Posições Abertas</h3>
            <p className="text-xs text-zinc-500">Monitoramento em tempo real</p>
          </div>
        </div>
        <span className={`px-2.5 py-1 rounded-full text-xs font-bold border font-mono
          ${openPositions.length > 0
            ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
            : 'bg-zinc-800 border-zinc-700 text-zinc-500'
          }`}>
          {openPositions.length} ativa{openPositions.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {openPositions.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 py-8">
            <div className="w-14 h-14 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center">
              <TrendingUp size={24} className="text-zinc-700" />
            </div>
            <p className="text-zinc-600 text-sm font-medium">Nenhuma posição em custódia</p>
            <p className="text-zinc-700 text-xs">Os tokens snipados aparecerão aqui em tempo real</p>
          </div>
        ) : (
          openPositions.map((pos) => (
            <PositionRow
              key={pos.token}
              position={pos}
              onPanicSell={forceSell}
            />
          ))
        )}
      </div>

      {/* Footer Legend */}
      {openPositions.length > 0 && (
        <div className="border-t border-zinc-800 px-4 py-2 flex items-center gap-4 shrink-0">
          <div className="flex items-center gap-1.5">
            <AlertTriangle size={12} className="text-rose-400" />
            <span className="text-[10px] text-zinc-600">Dump -10% em 3s</span>
          </div>
          <div className="flex items-center gap-1.5">
            <AlertTriangle size={12} className="text-amber-400" />
            <span className="text-[10px] text-zinc-600">Queda -5% em 3s</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="text-[10px] text-zinc-600">Estável</span>
          </div>
        </div>
      )}
    </div>
  )
}
