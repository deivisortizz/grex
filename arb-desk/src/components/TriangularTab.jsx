import { useState } from 'react'
import { Activity, ArrowRight, TrendingUp, TrendingDown, DollarSign } from 'lucide-react'

export default function TriangularTab({ triangularData = [] }) {
  const CAPITAL_BASE = 1000.00 // R$ 1000 simulados

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="text-blue-500" />
          Oceano Azul <span className="text-xs font-normal text-zinc-500 ml-2">Arbitragem Triangular Interna (Mesma Corretora)</span>
        </h2>
      </div>

      {triangularData.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-10 flex flex-col items-center justify-center text-center">
          <div className="w-12 h-12 rounded-full border-2 border-blue-500 border-t-transparent animate-spin mb-4"></div>
          <p className="text-zinc-400">Aguardando mapeamento do Triângulo (ETH/BRL, ETH/USDT, USDT/BRL)...</p>
          <p className="text-xs text-zinc-500 mt-2">Certifique-se de que há corretoras conectadas.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {triangularData.map((data, idx) => {
            const isDirectProfitable = data.direct_route.net > 0.05
            const isReverseProfitable = data.reverse_route.net > 0.05
            
            const bestNet = Math.max(data.direct_route.net, data.reverse_route.net)
            const isAnyProfitable = bestNet > 0.05
            const bestProfitBrl = CAPITAL_BASE * (bestNet / 100)

            return (
              <div key={idx} className={`bg-zinc-900 border rounded-xl p-6 transition-all duration-500 ${isAnyProfitable ? 'border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.3)]' : 'border-zinc-800'}`}>
                
                <div className="flex justify-between items-center mb-6 border-b border-zinc-800 pb-4">
                  <h3 className="text-lg font-bold text-white uppercase">{data.exchange}</h3>
                  <div className="flex gap-4">
                    <div className="text-right">
                      <p className="text-xs text-zinc-500">Lucro Máx (Base R$1.000)</p>
                      <p className={`font-bold ${isAnyProfitable ? 'text-emerald-500' : 'text-zinc-300'}`}>
                        R$ {bestProfitBrl > 0 ? bestProfitBrl.toFixed(2) : '0.00'}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  {/* Ciclo Direto */}
                  <div className="bg-zinc-950 p-5 rounded-xl border border-zinc-900 relative overflow-hidden">
                    {isDirectProfitable && (
                      <div className="absolute inset-0 bg-blue-500/5 animate-pulse rounded-xl pointer-events-none"></div>
                    )}
                    <h4 className="text-sm font-bold text-zinc-300 mb-4 uppercase tracking-wider flex items-center justify-between">
                      Ciclo Direto 
                      <span className={`px-2 py-0.5 rounded text-xs ${isDirectProfitable ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-800 text-zinc-500'}`}>
                        {data.direct_route.net.toFixed(3)}% Líquido
                      </span>
                    </h4>
                    
                    <div className="flex items-center justify-between mt-6">
                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center font-bold text-white border-2 border-zinc-700">BRL</div>
                      </div>
                      
                      <div className="flex-1 flex flex-col items-center px-2">
                        <p className="text-[10px] text-zinc-500 mb-1">Compra ETH</p>
                        <ArrowRight size={20} className={isDirectProfitable ? 'text-blue-500' : 'text-zinc-600'} />
                        <p className="text-[10px] text-zinc-400 mt-1 font-mono">Ask: {data.prices['ETH/BRL'].ask}</p>
                      </div>

                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-blue-900 flex items-center justify-center font-bold text-blue-300 border-2 border-blue-800 shadow-[0_0_10px_rgba(59,130,246,0.3)]">ETH</div>
                      </div>

                      <div className="flex-1 flex flex-col items-center px-2">
                        <p className="text-[10px] text-zinc-500 mb-1">Vende ETH</p>
                        <ArrowRight size={20} className={isDirectProfitable ? 'text-blue-500' : 'text-zinc-600'} />
                        <p className="text-[10px] text-zinc-400 mt-1 font-mono">Bid: {data.prices['ETH/USDT'].bid}</p>
                      </div>

                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-emerald-900 flex items-center justify-center font-bold text-emerald-300 border-2 border-emerald-800">USDT</div>
                      </div>

                      <div className="flex-1 flex flex-col items-center px-2">
                        <p className="text-[10px] text-zinc-500 mb-1">Vende USDT</p>
                        <ArrowRight size={20} className={isDirectProfitable ? 'text-blue-500' : 'text-zinc-600'} />
                        <p className="text-[10px] text-zinc-400 mt-1 font-mono">Bid: {data.prices['USDT/BRL'].bid}</p>
                      </div>

                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center font-bold text-white border-2 border-zinc-700">BRL</div>
                      </div>
                    </div>
                  </div>

                  {/* Ciclo Reverso */}
                  <div className="bg-zinc-950 p-5 rounded-xl border border-zinc-900 relative overflow-hidden">
                    {isReverseProfitable && (
                      <div className="absolute inset-0 bg-fuchsia-500/5 animate-pulse rounded-xl pointer-events-none"></div>
                    )}
                    <h4 className="text-sm font-bold text-zinc-300 mb-4 uppercase tracking-wider flex items-center justify-between">
                      Ciclo Reverso 
                      <span className={`px-2 py-0.5 rounded text-xs ${isReverseProfitable ? 'bg-fuchsia-500/20 text-fuchsia-400' : 'bg-zinc-800 text-zinc-500'}`}>
                        {data.reverse_route.net.toFixed(3)}% Líquido
                      </span>
                    </h4>
                    
                    <div className="flex items-center justify-between mt-6">
                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center font-bold text-white border-2 border-zinc-700">BRL</div>
                      </div>
                      
                      <div className="flex-1 flex flex-col items-center px-2">
                        <p className="text-[10px] text-zinc-500 mb-1">Compra USDT</p>
                        <ArrowRight size={20} className={isReverseProfitable ? 'text-fuchsia-500' : 'text-zinc-600'} />
                        <p className="text-[10px] text-zinc-400 mt-1 font-mono">Ask: {data.prices['USDT/BRL'].ask}</p>
                      </div>

                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-emerald-900 flex items-center justify-center font-bold text-emerald-300 border-2 border-emerald-800">USDT</div>
                      </div>

                      <div className="flex-1 flex flex-col items-center px-2">
                        <p className="text-[10px] text-zinc-500 mb-1">Compra ETH</p>
                        <ArrowRight size={20} className={isReverseProfitable ? 'text-fuchsia-500' : 'text-zinc-600'} />
                        <p className="text-[10px] text-zinc-400 mt-1 font-mono">Ask: {data.prices['ETH/USDT'].ask}</p>
                      </div>

                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-blue-900 flex items-center justify-center font-bold text-blue-300 border-2 border-blue-800 shadow-[0_0_10px_rgba(59,130,246,0.3)]">ETH</div>
                      </div>

                      <div className="flex-1 flex flex-col items-center px-2">
                        <p className="text-[10px] text-zinc-500 mb-1">Vende ETH</p>
                        <ArrowRight size={20} className={isReverseProfitable ? 'text-fuchsia-500' : 'text-zinc-600'} />
                        <p className="text-[10px] text-zinc-400 mt-1 font-mono">Bid: {data.prices['ETH/BRL'].bid}</p>
                      </div>

                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center font-bold text-white border-2 border-zinc-700">BRL</div>
                      </div>
                    </div>
                  </div>
                </div>

              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
