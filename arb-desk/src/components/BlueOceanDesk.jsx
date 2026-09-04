import { TrendingUp, TrendingDown, ArrowRight, Zap, WifiOff, Power } from 'lucide-react'

const RouteFlow = ({ labels, prices, color, isActive }) => {
  const colorMap = {
    blue: {
      node: isActive ? 'border-blue-500 bg-blue-500/10 text-blue-200 shadow-[0_0_10px_rgba(59,130,246,0.5)]' : 'border-zinc-700 bg-zinc-800 text-zinc-400',
      arrow: isActive ? 'text-blue-400' : 'text-zinc-700',
    },
    fuchsia: {
      node: isActive ? 'border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-200 shadow-[0_0_10px_rgba(217,70,239,0.5)]' : 'border-zinc-700 bg-zinc-800 text-zinc-400',
      arrow: isActive ? 'text-fuchsia-400' : 'text-zinc-700',
    }
  }
  const c = colorMap[color]

  return (
    <div className="flex items-center justify-between gap-1 flex-wrap">
      {labels.map((label, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center text-xs font-bold transition-all duration-500 ${c.node}`}>
            {label}
          </div>
          {i < labels.length - 1 && (
            <div className="flex flex-col items-center mx-1">
              <ArrowRight size={14} className={`${c.arrow} transition-colors duration-500`} />
              {prices[i] && (
                <span className="text-[9px] text-zinc-600 font-mono mt-0.5 whitespace-nowrap">
                  {Number(prices[i]).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function BlueOceanDesk({ triangularData = [], isTriangularActive = false, sendCommand }) {
  const CAPITAL_BASE = 1000.0

  const handleToggle = () => {
    if (isTriangularActive) {
      sendCommand('pause_triangular')
    } else {
      sendCommand('start_triangular')
    }
  }

  return (
    <div className="space-y-6">

      {/* Controle Manual do Motor */}
      <div className={`rounded-2xl border p-5 flex items-center justify-between transition-all duration-500 ${
        isTriangularActive
          ? 'bg-emerald-950/30 border-emerald-600/40 shadow-[0_0_25px_rgba(16,185,129,0.12)]'
          : 'bg-zinc-900 border-zinc-800'
      }`}>
        <div>
          <h3 className="text-white font-bold text-base">Motor Triangular (Oceano Azul)</h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {isTriangularActive
              ? '⚡ Escaneando e executando ciclos triangulares em tempo real'
              : '⏸ Apenas monitorando — nenhuma ordem será enviada'}
          </p>
        </div>
        <button
          onClick={handleToggle}
          className={`flex items-center gap-2 px-6 py-3 rounded-xl font-bold text-sm transition-all duration-300 ${
            isTriangularActive
              ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-[0_0_15px_rgba(239,68,68,0.4)]'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.4)]'
          }`}
        >
          <Power size={16} />
          {isTriangularActive ? 'PAUSAR MOTOR' : 'LIGAR MOTOR'}
        </button>
      </div>

      {/* Cards das Corretoras */}
      {triangularData.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-56 gap-4 text-center bg-zinc-900 border border-zinc-800 rounded-2xl">
          <div className="w-10 h-10 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
          <div>
            <p className="text-zinc-300 font-medium">Aguardando streams triangulares...</p>
            <p className="text-xs text-zinc-500 mt-1">Certifique-se de que o Python está rodando e uma corretora está conectada.</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-600">
            <WifiOff size={14} />
            ETH/BRL · ETH/USDT · USDT/BRL
          </div>
        </div>
      ) : (
        triangularData.map((data, idx) => {
          const isDirectGood = data.direct_route?.net > 0.05
          const isReverseGood = data.reverse_route?.net > 0.05
          const bestNet = Math.max(data.direct_route?.net ?? -99, data.reverse_route?.net ?? -99)
          const bestProfitBrl = CAPITAL_BASE * (bestNet / 100)
          const prices = data.prices ?? {}

          return (
            <div
              key={idx}
              className={`rounded-2xl border bg-zinc-900 p-6 transition-all duration-700 ${
                isDirectGood || isReverseGood
                  ? 'border-blue-500/40 shadow-[0_0_25px_rgba(59,130,246,0.1)]'
                  : 'border-zinc-800'
              }`}
            >
              {/* Header da Corretora */}
              <div className="flex items-center justify-between mb-5 pb-4 border-b border-zinc-800">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-500/10 rounded-lg">
                    <Zap size={18} className="text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-white font-bold text-sm uppercase tracking-wide">{data.exchange}</h3>
                    <p className="text-xs text-zinc-500">ETH/BRL · ETH/USDT · USDT/BRL</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-zinc-500">Lucro Proj. (R$1.000)</p>
                  <p className={`text-xl font-bold font-mono ${bestNet > 0.05 ? 'text-emerald-400' : 'text-zinc-600'}`}>
                    {bestNet > 0.05 ? `R$ ${bestProfitBrl.toFixed(2)}` : '—'}
                  </p>
                </div>
              </div>

              {/* Preços em Tempo Real */}
              <div className="grid grid-cols-3 gap-3 mb-5">
                {[
                  { pair: 'ETH/BRL', d: prices['ETH/BRL'] },
                  { pair: 'ETH/USDT', d: prices['ETH/USDT'] },
                  { pair: 'USDT/BRL', d: prices['USDT/BRL'] },
                ].map(({ pair, d }) => (
                  <div key={pair} className="bg-zinc-950 rounded-xl p-3 border border-zinc-800">
                    <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider mb-2">{pair}</p>
                    <div className="flex justify-between text-xs">
                      <div>
                        <p className="text-zinc-600 text-[9px]">BID</p>
                        <p className="text-emerald-400 font-mono font-bold text-xs">
                          {d?.bid ? Number(d.bid).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-zinc-600 text-[9px]">ASK</p>
                        <p className="text-rose-400 font-mono font-bold text-xs">
                          {d?.ask ? Number(d.ask).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Rotas */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Ciclo Direto */}
                <div className={`relative bg-zinc-950 rounded-xl p-4 border transition-all duration-500 overflow-hidden ${isDirectGood ? 'border-blue-500/50' : 'border-zinc-800'}`}>
                  {isDirectGood && <div className="absolute inset-0 bg-blue-500/5 animate-pulse pointer-events-none rounded-xl" />}
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-zinc-400">Ciclo Direto</p>
                    <div className="flex items-center gap-2">
                      {data.direct_route?.net > 0 ? <TrendingUp size={12} className="text-emerald-400" /> : <TrendingDown size={12} className="text-rose-400" />}
                      <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${isDirectGood ? 'bg-blue-500/20 text-blue-300' : 'bg-zinc-800 text-zinc-500'}`}>
                        {data.direct_route?.net?.toFixed(4) ?? '—'}% líq.
                      </span>
                    </div>
                  </div>
                  <RouteFlow
                    labels={['BRL', 'ETH', 'USDT', 'BRL']}
                    prices={[prices['ETH/BRL']?.ask, prices['ETH/USDT']?.bid, prices['USDT/BRL']?.bid]}
                    color="blue"
                    isActive={isDirectGood}
                  />
                </div>

                {/* Ciclo Reverso */}
                <div className={`relative bg-zinc-950 rounded-xl p-4 border transition-all duration-500 overflow-hidden ${isReverseGood ? 'border-fuchsia-500/50' : 'border-zinc-800'}`}>
                  {isReverseGood && <div className="absolute inset-0 bg-fuchsia-500/5 animate-pulse pointer-events-none rounded-xl" />}
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-zinc-400">Ciclo Reverso</p>
                    <div className="flex items-center gap-2">
                      {data.reverse_route?.net > 0 ? <TrendingUp size={12} className="text-emerald-400" /> : <TrendingDown size={12} className="text-rose-400" />}
                      <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${isReverseGood ? 'bg-fuchsia-500/20 text-fuchsia-300' : 'bg-zinc-800 text-zinc-500'}`}>
                        {data.reverse_route?.net?.toFixed(4) ?? '—'}% líq.
                      </span>
                    </div>
                  </div>
                  <RouteFlow
                    labels={['BRL', 'USDT', 'ETH', 'BRL']}
                    prices={[prices['USDT/BRL']?.ask, prices['ETH/USDT']?.ask, prices['ETH/BRL']?.bid]}
                    color="fuchsia"
                    isActive={isReverseGood}
                  />
                </div>
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}