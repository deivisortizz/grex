import React from 'react';
import { Layers, ArrowUpRight, ArrowDownRight, ExternalLink, Zap } from 'lucide-react';

export default function SolanaPositionsTable({ positions = [], onPanicSell }) {
  if (!positions || positions.length === 0) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Layers size={20} className="text-zinc-400" />
          <h3 className="text-lg font-bold text-white tracking-tight">Posições Abertas (Solana)</h3>
        </div>
        <div className="text-center text-zinc-500 py-10 text-sm">
          Nenhuma posição ativa no momento.
        </div>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Layers size={20} className="text-zinc-400" />
        <h3 className="text-lg font-bold text-white tracking-tight">Posições Abertas (Solana)</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="py-3 px-4 text-xs font-semibold text-zinc-400">Token</th>
              <th className="py-3 px-4 text-xs font-semibold text-zinc-400">Custo Total</th>
              <th className="py-3 px-4 text-xs font-semibold text-zinc-400">Valor Atual</th>
              <th className="py-3 px-4 text-xs font-semibold text-zinc-400 text-right">PnL (%)</th>
              <th className="py-3 px-4 text-xs font-semibold text-zinc-400 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos, idx) => {
              const isProfit = pos.pnl_pct >= 0;
              return (
                <tr key={idx} className="border-b border-zinc-800/50 hover:bg-zinc-800/20 transition-colors">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-zinc-300">
                        {pos.token ? `${pos.token.substring(0,6)}...${pos.token.substring(pos.token.length-4)}` : 'Desconhecido'}
                      </span>
                      <a 
                        href={`https://pump.fun/${pos.token}`}
                        target="_blank" 
                        rel="noreferrer"
                        className="text-zinc-500 hover:text-blue-400 transition-colors"
                      >
                        <ExternalLink size={14} />
                      </a>
                    </div>
                  </td>
                  <td className="py-3 px-4 font-mono text-sm text-zinc-400">
                    {pos.entry_price ? pos.entry_price.toFixed(6) : '0.00'} SOL
                  </td>
                  <td className="py-3 px-4 font-mono text-sm text-zinc-300">
                    {pos.current_price ? pos.current_price.toFixed(6) : '0.00'} SOL
                  </td>
                  <td className="py-3 px-4 text-right">
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold font-mono ${
                      isProfit ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {isProfit ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {Math.abs(pos.pnl_pct || 0).toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <button
                      onClick={() => onPanicSell && onPanicSell(pos.token)}
                      className="inline-flex items-center justify-center p-2 rounded-lg bg-rose-500/20 text-rose-500 hover:bg-rose-500/30 hover:text-rose-400 transition-colors"
                      title="Panic Sell (100% Emergência)"
                    >
                      <Zap size={16} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
