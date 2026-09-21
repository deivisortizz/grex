import React from 'react';
import { History, Copy, ArrowRight, ExternalLink, ShieldCheck, ShieldAlert } from 'lucide-react';

export default function SolanaHistoryTable({ history = [] }) {
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  const openSolscan = (mint) => {
    window.open(`https://solscan.io/token/${mint}`, '_blank');
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden flex flex-col">
      <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between bg-black/40">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <History size={18} className="text-violet-400" />
          Histórico Recente (Fechadas)
        </h3>
        <div className="text-xs font-mono text-zinc-500 bg-zinc-900/50 px-2 py-1 rounded">
          {history.length} trades
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-zinc-900/50 text-[10px] uppercase tracking-wider text-zinc-400 font-semibold border-b border-zinc-800">
              <th className="p-3 font-medium">Token (Mint)</th>
              <th className="p-3 font-medium text-right">Custo Total</th>
              <th className="p-3 font-medium text-right">Retorno</th>
              <th className="p-3 font-medium text-right">PnL Final</th>
              <th className="p-3 font-medium text-right">Data/Hora</th>
              <th className="p-3 font-medium text-center">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {history.length === 0 ? (
              <tr>
                <td colSpan="6" className="p-6 text-center text-xs text-zinc-500 font-medium">
                  Nenhum trade fechado encontrado.
                </td>
              </tr>
            ) : (
              history.map((trade, idx) => {
                const isWin = trade.is_win === 1 || trade.is_win === true;
                const pnl = trade.net_pnl_sol || 0;
                
                return (
                  <tr key={idx} className="hover:bg-zinc-800/20 transition-colors">
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full ${isWin ? 'bg-emerald-400' : 'bg-rose-500'}`} />
                        <span className="text-xs text-zinc-300 font-mono truncate max-w-[120px]" title={trade.token_mint}>
                          {trade.token_mint}
                        </span>
                      </div>
                    </td>
                    <td className="p-3 text-right">
                      <div className="text-xs text-zinc-400 font-mono">
                        {trade.sol_spent?.toFixed(5)} SOL
                      </div>
                    </td>
                    <td className="p-3 text-right">
                      <div className="text-xs text-zinc-300 font-mono font-medium">
                        {trade.sol_received?.toFixed(5)} SOL
                      </div>
                    </td>
                    <td className="p-3 text-right">
                      <div className={`text-xs font-bold font-mono flex items-center justify-end gap-1 ${
                        isWin ? 'text-emerald-400' : 'text-rose-500'
                      }`}>
                        {pnl > 0 ? '+' : ''}{pnl.toFixed(5)} SOL
                      </div>
                    </td>
                    <td className="p-3 text-right">
                      <div className="text-xs text-zinc-500 font-mono">
                        {new Date(trade.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center justify-center gap-2">
                        <button 
                          onClick={() => copyToClipboard(trade.token_mint)}
                          className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded transition-colors group"
                          title="Copiar Mint"
                        >
                          <Copy size={14} />
                        </button>
                        <button 
                          onClick={() => openSolscan(trade.token_mint)}
                          className="p-1.5 text-zinc-500 hover:text-violet-400 hover:bg-violet-500/10 rounded transition-colors"
                          title="Abrir no Solscan"
                        >
                          <ExternalLink size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
