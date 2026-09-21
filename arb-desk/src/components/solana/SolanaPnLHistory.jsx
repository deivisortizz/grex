import React, { useState, useEffect } from 'react';
import { Activity, ArrowUpRight, ArrowDownRight, RefreshCcw, Crosshair } from 'lucide-react';

export default function SolanaPnLHistory({ sendCommand }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/trade-history', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await res.json();
      if (res.ok) {
        setHistory(Array.isArray(data.history) ? data.history : []);
      } else {
        setError(data.detail || "Erro ao carregar histórico");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  // [FIX] Antes chamava fetch('/api/manual-buy'), rota que nunca existiu em server.py
  // (processo separado, sem acesso à carteira/engine do sniper). O re-snipe manual real
  // só é possível via WebSocket (force_buy), já autenticado e conectado ao sniper.
  const handleReSnipe = (mint) => {
    if (typeof sendCommand === 'function') {
      sendCommand('force_buy', { token: mint });
    }
  };

  const formatAddress = (addr) => {
    if (!addr) return '';
    return `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`;
  };

  return (
    <div className="bg-[#0a0a0c] border border-zinc-800 rounded-2xl flex flex-col h-full overflow-hidden shadow-2xl relative">
      <div className="px-5 py-4 border-b border-zinc-800/80 bg-zinc-900/40 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-500/10 flex items-center justify-center border border-violet-500/20">
            <Activity className="text-violet-400" size={20} />
          </div>
          <div>
            <h2 className="font-extrabold text-white tracking-tight text-lg">Global PnL History</h2>
            <div className="text-[11px] font-mono text-zinc-500 uppercase tracking-widest mt-0.5">
              Auditoria de Desempenho
            </div>
          </div>
        </div>
        <button 
          onClick={fetchHistory}
          disabled={loading}
          className="p-2 rounded-lg bg-zinc-800/50 text-zinc-400 hover:text-white transition-colors border border-zinc-700/50"
        >
          <RefreshCcw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-5">
        {error ? (
          <div className="text-rose-400 text-sm p-4 bg-rose-500/10 rounded-lg border border-rose-500/20">
            {error}
          </div>
        ) : (
          <div className="rounded-xl border border-zinc-800/60 overflow-hidden">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-black/40 text-zinc-500 text-[10px] uppercase font-bold tracking-wider">
                <tr>
                  <th className="px-5 py-3 border-b border-zinc-800/60">Data/Hora</th>
                  <th className="px-5 py-3 border-b border-zinc-800/60">Token</th>
                  <th className="px-5 py-3 border-b border-zinc-800/60">Investido (SOL)</th>
                  <th className="px-5 py-3 border-b border-zinc-800/60">Retorno (SOL)</th>
                  <th className="px-5 py-3 border-b border-zinc-800/60">Jito Fee</th>
                  <th className="px-5 py-3 border-b border-zinc-800/60 text-right">Resultado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40 bg-zinc-900/20">
                {(!Array.isArray(history) || history.length === 0) && !loading ? (
                  <tr>
                    <td colSpan="6" className="px-5 py-10 text-center text-zinc-500">
                      Nenhum histórico de PnL registado.
                    </td>
                  </tr>
                ) : (
                  (Array.isArray(history) ? history : []).map((trade, idx) => {
                    const dateStr = trade.created_at || trade.timestamp;
                    const dateFormatted = dateStr ? new Date(dateStr + 'Z').toLocaleString() : 'N/A';
                    const solSpent = trade.sol_spent || trade.buy_amount_sol || 0;
                    const solReceived = trade.sol_received || 0;
                    const jitoBuy = trade.jito_tip_buy || 0;
                    const jitoSell = trade.jito_tip_sell || 0;
                    const netPnl = trade.net_pnl_sol || 0;
                    
                    return (
                      <tr key={idx} className="hover:bg-zinc-800/30 transition-colors">
                        <td className="px-5 py-3 text-xs text-zinc-400 font-mono">
                          {dateFormatted}
                        </td>
                        <td className="px-5 py-3 font-mono text-xs text-emerald-400">
                          <div className="flex items-center gap-2">
                            <span>{formatAddress(trade.token_mint || trade.mint)}</span>
                            <button 
                              onClick={() => handleReSnipe(trade.token_mint || trade.mint)}
                              className="bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/40 p-1.5 rounded transition-colors border border-indigo-500/30"
                              title="Re-Snipe (Entrada Manual Direta)"
                            >
                              <Crosshair size={12} />
                            </button>
                          </div>
                        </td>
                        <td className="px-5 py-3 text-zinc-300 font-mono">
                          {solSpent.toFixed(4)}
                        </td>
                        <td className="px-5 py-3 text-zinc-300 font-mono">
                          {solReceived.toFixed(4)}
                        </td>
                        <td className="px-5 py-3 text-zinc-500 font-mono text-[10px]">
                          B: {jitoBuy.toFixed(4)} / S: {jitoSell.toFixed(4)}
                        </td>
                        <td className="px-5 py-3 text-right">
                          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-bold text-xs ${
                            trade.is_win 
                              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' 
                              : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
                          }`}>
                            {trade.is_win ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                            {netPnl > 0 ? '+' : ''}{netPnl.toFixed(4)} SOL
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
