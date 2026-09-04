import { useState, useEffect, useRef } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

export default function ExchangeCard({ name, initialBid, initialAsk, realBid, realAsk }) {
  const [bid, setBid] = useState(initialBid)
  const [ask, setAsk] = useState(initialAsk)
  const [lastBidDirection, setLastBidDirection] = useState('up')
  
  const prevBid = useRef(initialBid)

  useEffect(() => {
    // Se receber dados reais via WebSockets (vindo do Python)
    if (realBid !== undefined && realAsk !== undefined) {
      setBid(realBid)
      setAsk(realAsk)
      
      if (realBid > prevBid.current) {
        setLastBidDirection('up')
      } else if (realBid < prevBid.current) {
        setLastBidDirection('down')
      }
      prevBid.current = realBid
    }
  }, [realBid, realAsk])

  const isLive = realBid !== undefined

  return (
    <div className={`bg-zinc-900 border ${isLive ? 'border-emerald-900/30' : 'border-zinc-800'} rounded-xl p-5 transition-colors relative overflow-hidden`}>
      {/* Indicador sutil de live feed piscando */}
      {isLive && (
        <div className="absolute top-0 right-0 w-12 h-12 flex justify-end p-2 opacity-50">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
        </div>
      )}

      <div className="flex justify-between items-center mb-6 relative z-10">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            {name}
            {!isLive && <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 font-normal tracking-wide">MOCK</span>}
          </h3>
          <p className="text-xs text-zinc-400 mt-0.5">USDT / BRL</p>
        </div>
        <div className="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center text-sm font-bold text-zinc-400 border border-zinc-700/50">
          {name.substring(0, 2).toUpperCase()}
        </div>
      </div>

      <div className="space-y-3 relative z-10">
        {/* Bid - Melhor Compra */}
        <div className="bg-zinc-950/60 rounded-lg p-3.5 border border-zinc-800/50">
          <div className="text-[10px] text-zinc-500 mb-1.5 font-semibold uppercase tracking-wider">Melhor Compra (Bid)</div>
          <div className="flex items-center justify-between">
            <span className={`text-xl font-mono font-bold ${isLive ? 'text-emerald-400' : 'text-zinc-500'}`}>
              R$ {bid.toFixed(4)}
            </span>
            {isLive && (
              lastBidDirection === 'up' ? (
                <TrendingUp size={16} className="text-emerald-400/70" />
              ) : (
                <TrendingDown size={16} className="text-rose-400/70" />
              )
            )}
          </div>
        </div>

        {/* Ask - Melhor Venda */}
        <div className="bg-zinc-950/60 rounded-lg p-3.5 border border-zinc-800/50">
          <div className="text-[10px] text-zinc-500 mb-1.5 font-semibold uppercase tracking-wider">Melhor Venda (Ask)</div>
          <div className="flex items-center justify-between">
            <span className={`text-xl font-mono font-bold ${isLive ? 'text-rose-400' : 'text-zinc-500'}`}>
              R$ {ask.toFixed(4)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
