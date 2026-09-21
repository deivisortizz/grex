import React, { useState, useMemo } from 'react';
import { Activity, Copy, ExternalLink, Zap, ArrowUpRight, ArrowDownRight, TrendingUp, Search, Star } from 'lucide-react';

// Sparkline component that draws a real chart based on price arrays
const TrendSparkline = ({ prices = [], isPositive }) => {
  if (!prices || prices.length < 2) {
    // Linha reta ou mini pontilhado para tokens sem histórico de ticks (Idle)
    return (
      <svg width="40" height="25" viewBox="0 0 40 30" className="opacity-40">
        <line x1="0" y1="15" x2="40" y2="15" stroke="#71717a" strokeWidth="2" strokeDasharray="4 2" />
      </svg>
    );
  }

  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const range = maxPrice - minPrice || 1;
  
  // Mapear preços para coordenadas SVG (0-40 largura, 30-0 altura invertida)
  const stepX = 40 / (prices.length - 1);
  const points = prices.map((price, i) => {
    const x = i * stepX;
    // O y será entre 5 e 25 para dar uma margem no SVG
    const y = 25 - (((price - minPrice) / range) * 20);
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width="40" height="25" viewBox="0 0 40 30" className="opacity-90">
      <polyline
        fill="none"
        stroke={isPositive ? "#10b981" : "#f43f5e"}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
};

export default function MayhemScreenerTable({ pools = [], positions = [], history = [], priceHistory = {}, sendCommand, networkName = "Solana" }) {
  const [activeTab, setActiveTab] = useState('All');
  const [sortBy, setSortBy] = useState('Newest');
  
  const [watchlist, setWatchlist] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('mayhem_watchlist') || '[]');
    } catch {
      return [];
    }
  });

  const toggleWatchlist = (mint) => {
    setWatchlist(prev => {
      const next = prev.includes(mint) ? prev.filter(m => m !== mint) : [...prev, mint];
      localStorage.setItem('mayhem_watchlist', JSON.stringify(next));
      return next;
    });
  };
  
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  const formatAddress = (addr) => {
    if (!addr) return '';
    return `${addr.substring(0, 4)}...${addr.substring(addr.length - 4)}`;
  };

  // [FIX] Antes chamava fetch('/api/manual-buy'|'/api/manual-sell'), rotas que nunca
  // existiram em server.py — o clique não fazia nada e falhava em silêncio (só
  // console.error, sem feedback ao usuário). A compra/venda manual real só é possível
  // via WebSocket (force_buy/force_sell), que é o canal já autenticado e conectado
  // ao processo do sniper (server.py é um processo separado e não tem acesso à carteira).
  const handleManualSnipe = (token) => {
    if (typeof sendCommand === 'function') {
      sendCommand('force_buy', { token });
    }
  };

  const handleManualSell = (token) => {
    if (typeof sendCommand === 'function') {
      sendCommand('force_sell', { token });
    }
  };

  // Build unified token list
  const unifiedTokens = useMemo(() => {
    const tokenMap = new Map();

    // 1. Map pools (Idle / Base Data)
    pools.forEach(pool => {
      // Extrair o mint com segurança
      const mint = pool.token || pool.mint;
      if (!mint) return;

      tokenMap.set(mint, {
        mint: mint,
        name: pool.name || pool.token_name || pool.symbol || `Pump-${mint.slice(0, 4)}`,
        symbol: pool.symbol || pool.ticker || pool.token_symbol || pool.name || `PUMP-${mint.slice(0, 4)}`,
        image: pool.image_uri || null,
        mcap: pool.usd_market_cap || pool.market_cap || pool.mcap || 4500,
        volume: pool.volume || pool.v_sol || pool.initial_buy || 0.01, 
        replies: pool.reply_count || 0,
        timestamp: pool.timestamp || Date.now(),
        state: 'Idle',
        mode: 'Manual',
        pnl_pct: 0,
        price_ticks: priceHistory[mint] || []
      });
    });

    // 2. Map history (Ended)
    history.forEach(h => {
      const mint = h.token_mint || h.mint;
      if (!mint) return;

      if (!tokenMap.has(mint)) {
        tokenMap.set(mint, {
          mint: mint,
          name: h.name || h.token_name || h.symbol || `Pump-${mint.slice(0, 4)}`,
          symbol: h.symbol || h.ticker || h.token_symbol || h.name || `PUMP-${mint.slice(0, 4)}`,
          image: h.image_uri || h.image || null,
          mcap: h.usd_market_cap || h.market_cap || h.mcap || 4500,
          volume: h.volume || h.v_sol || h.initial_buy || 0.01, 
          replies: h.reply_count || h.replies || 0,
          timestamp: new Date(h.timestamp || h.created_at || Date.now()).getTime(),
          state: 'Ended',
          mode: 'Auto',
          pnl_pct: h.pnl_pct || 0,
          price_ticks: priceHistory[mint] || []
        });
      } else {
        const t = tokenMap.get(mint);
        t.state = 'Ended';
        t.mode = 'Auto';
        t.pnl_pct = h.pnl_pct || 0;
        t.price_ticks = priceHistory[mint] || t.price_ticks;
      }
    });

    // 3. Map positions (Active)
    positions.forEach(pos => {
      const mint = pos.token || pos.mint;
      if (!mint) return;

      if (!tokenMap.has(mint)) {
        tokenMap.set(mint, {
          mint: mint,
          name: pos.name || pos.token_name || pos.symbol || `Pump-${mint.slice(0, 4)}`,
          symbol: pos.symbol || pos.ticker || pos.token_symbol || pos.name || `PUMP-${mint.slice(0, 4)}`,
          image: pos.image_uri || pos.image || null,
          mcap: pos.usd_market_cap || pos.market_cap || pos.mcap || 4500,
          volume: pos.volume || pos.v_sol || pos.initial_buy || 0.01, 
          replies: pos.reply_count || pos.replies || 0,
          timestamp: Date.now(),
          state: 'Active',
          mode: 'Auto',
          pnl_pct: pos.pnl_pct || 0,
          current_price: pos.current_price,
          price_ticks: priceHistory[mint] || []
        });
      } else {
        const t = tokenMap.get(mint);
        t.state = 'Active';
        t.mode = 'Auto';
        t.pnl_pct = pos.pnl_pct || 0;
        t.current_price = pos.current_price;
        t.price_ticks = priceHistory[mint] || t.price_ticks;
        if (pos.usd_market_cap) t.mcap = pos.usd_market_cap;
        if (pos.volume) t.volume = pos.volume;
      }
    });

    return Array.from(tokenMap.values());
  }, [pools, positions, history, priceHistory]);

  const filteredAndSortedTokens = useMemo(() => {
    let result = [...unifiedTokens];
    
    // Filters
    if (activeTab === 'Watchlist ⭐') {
      result = result.filter(t => watchlist.includes(t.mint));
    } else if (activeTab !== 'All') {
      result = result.filter(t => t.state === activeTab || (activeTab === 'Idle' && t.state === 'Idle'));
    }

    // Sort
    if (sortBy === 'Newest') {
      result.sort((a, b) => b.timestamp - a.timestamp);
    } else if (sortBy === 'MCap') {
      result.sort((a, b) => b.mcap - a.mcap);
    } else if (sortBy === 'Volume') {
      // Ordena por volume ou replies (já que o volume pode não estar no WSS da Pump.fun base)
      result.sort((a, b) => (b.volume || b.replies) - (a.volume || a.replies));
    }

    return result.slice(0, 100); // Max 100 elements to keep UI fast
  }, [unifiedTokens, activeTab, sortBy]);

  return (
    <div className="bg-[#0a0a0c] border border-zinc-800 rounded-2xl flex flex-col h-full overflow-hidden shadow-2xl relative">
      {/* Header & Tabs */}
      <div className="px-5 py-4 border-b border-zinc-800/80 bg-zinc-900/40 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
              <Activity className="text-indigo-400" size={20} />
            </div>
            <div>
              <h2 className="font-extrabold text-white tracking-tight text-lg">Mayhem Screener</h2>
              <div className="text-[11px] font-mono text-zinc-500 uppercase tracking-widest mt-0.5">
                Advanced Token Feed & State
              </div>
            </div>
          </div>
          
          <div className="flex bg-black/40 p-1 rounded-lg border border-zinc-800/60">
            {['All', 'Idle', 'Active', 'Ended', 'Watchlist ⭐'].map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all ${
                  activeTab === tab 
                    ? 'bg-zinc-800 text-white shadow-sm' 
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 bg-black/40 px-3 py-1.5 rounded-lg border border-zinc-800/60 w-64">
            <Search size={14} className="text-zinc-500" />
            <input 
              type="text" 
              placeholder="Search token..." 
              className="bg-transparent border-none outline-none text-xs text-white w-full"
            />
          </div>
          <div className="flex gap-2">
            {['Newest', 'MCap', 'Volume'].map(sort => (
              <button
                key={sort}
                onClick={() => setSortBy(sort)}
                className={`px-3 py-1 rounded text-[10px] font-bold uppercase transition-all border ${
                  sortBy === sort
                    ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30'
                    : 'bg-transparent text-zinc-600 border-zinc-800 hover:text-zinc-400'
                }`}
              >
                {sort}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto bg-[#0a0a0c]">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-[#0a0a0c] text-zinc-500 sticky top-0 z-10 text-[10px] uppercase font-bold tracking-wider shadow-md">
            <tr>
              <th className="px-5 py-3 border-b border-zinc-800">#</th>
              <th className="px-5 py-3 border-b border-zinc-800">COIN</th>
              <th className="px-5 py-3 border-b border-zinc-800">MCap</th>
              <th className="px-5 py-3 border-b border-zinc-800">STATE</th>
              <th className="px-5 py-3 border-b border-zinc-800 text-center">TREND</th>
              <th className="px-5 py-3 border-b border-zinc-800 text-right">ACTION</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/40">
            {filteredAndSortedTokens.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-5 py-12 text-center text-zinc-600">
                  <TrendingUp className="mx-auto h-8 w-8 mb-3 opacity-20" />
                  <p>Nenhum token encontrado na rede {networkName}.</p>
                </td>
              </tr>
            ) : (
              filteredAndSortedTokens.map((token, idx) => {
                const isProfit = token.pnl_pct >= 0;
                return (
                  <tr key={token.mint} className="hover:bg-zinc-800/30 transition-colors group">
                    <td className="px-5 py-3 text-xs text-zinc-600 font-mono">{idx + 1}</td>
                    
                    {/* COIN Column */}
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <button 
                          onClick={() => toggleWatchlist(token.mint)}
                          className={`shrink-0 transition-colors ${watchlist.includes(token.mint) ? 'text-amber-400' : 'text-zinc-700 hover:text-zinc-500'}`}
                          title={watchlist.includes(token.mint) ? "Remover dos Favoritos" : "Adicionar aos Favoritos"}
                        >
                          <Star size={16} fill={watchlist.includes(token.mint) ? "currentColor" : "none"} />
                        </button>
                        <div className="w-8 h-8 rounded-full bg-zinc-800 overflow-hidden shrink-0 border border-zinc-700">
                          {token.image ? (
                            <img src={token.image} alt={token.symbol} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] font-bold text-zinc-500">?</div>
                          )}
                        </div>
                        <div className="flex flex-col">
                          <div className="flex items-center gap-1.5">
                            <span className="font-bold text-white text-sm">{token.symbol}</span>
                            {token.mode === 'Auto' && <span className="bg-blue-500/20 text-blue-400 text-[9px] px-1 rounded uppercase font-bold">Auto</span>}
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-[10px] text-zinc-500 font-mono">{formatAddress(token.mint)}</span>
                            <button onClick={() => copyToClipboard(token.mint)} className="text-zinc-600 hover:text-white transition-colors">
                              <Copy size={10} />
                            </button>
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* MCap Column */}
                    <td className="px-5 py-3">
                      <div className="flex flex-col">
                        <span className="font-mono text-emerald-400 text-sm font-bold">
                          {token.mcap > 0 ? `$${(token.mcap / 1000).toFixed(1)}k` : '$4.5k'}
                        </span>
                        <span className="text-[10px] text-zinc-500 font-mono">
                          {token.volume > 0 ? `Vol: ${token.volume.toFixed(2)} SOL` : 'Vol: 0.01 SOL'}
                        </span>
                      </div>
                    </td>

                    {/* STATE Column */}
                    <td className="px-5 py-3">
                      {token.state === 'Active' && (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          <span className="text-xs font-bold text-emerald-400">Active</span>
                        </div>
                      )}
                      {token.state === 'Idle' && (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-800/50 border border-zinc-700/50">
                          <span className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
                          <span className="text-xs font-bold text-zinc-400">Idle</span>
                        </div>
                      )}
                      {token.state === 'Ended' && (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-rose-500/10 border border-rose-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                          <span className="text-xs font-bold text-rose-400">Ended</span>
                        </div>
                      )}
                    </td>

                    {/* TREND Column */}
                    <td className="px-5 py-3 text-center">
                      <div className="flex flex-col items-center gap-1">
                        <TrendSparkline prices={token.price_ticks} isPositive={isProfit || token.state === 'Idle'} />
                        {(token.state === 'Active' || token.state === 'Ended') && (
                          <span className={`text-[10px] font-bold font-mono ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {isProfit ? '+' : ''}{token.pnl_pct.toFixed(2)}%
                          </span>
                        )}
                      </div>
                    </td>

                    {/* ACTION Column */}
                    <td className="px-5 py-3 text-right">
                      {token.state === 'Idle' && (
                        <button 
                          onClick={() => handleManualSnipe(token.mint)}
                          className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg transition-colors shadow-[0_0_15px_rgba(99,102,241,0.3)] text-xs font-bold inline-flex items-center gap-1.5"
                          title="Manual Snipe"
                        >
                          <Zap size={14} /> Buy
                        </button>
                      )}
                      {token.state === 'Active' && (
                        <button 
                          onClick={() => handleManualSell(token.mint)}
                          className="bg-rose-500/20 border border-rose-500/30 hover:bg-rose-500/30 text-rose-400 hover:text-white px-3 py-1.5 rounded-lg transition-colors text-xs font-bold inline-flex items-center gap-1.5"
                          title="Panic Sell"
                        >
                          Sell
                        </button>
                      )}
                      {token.state === 'Ended' && (
                        <span className="text-[10px] text-zinc-600 font-mono">Closed</span>
                      )}
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
