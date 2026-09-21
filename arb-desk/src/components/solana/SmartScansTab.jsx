import React, { useMemo } from 'react';
import MayhemScreenerTable from '../sniper/MayhemScreenerTable';

export default function SmartScansTab({ pools = [], positions = [], history = [], priceHistory = {} }) {
  
  // Filtragem Inteligente: Apenas tokens que se destacam
  const smartPools = useMemo(() => {
    return pools.filter(pool => {
      const vol = pool.volume || pool.v_sol || 0;
      const mcap = pool.usd_market_cap || pool.market_cap || pool.mcap || 0;
      
      // Critério 1: Volume robusto logo no início (ex: > 3.0 SOL de fluxo inicial puro)
      if (vol >= 3.0) return true;
      
      // Critério 2: Market Cap muito elevado (indica injeção de liquidez maciça)
      if (mcap >= 15000) return true;
      
      // Futuro Critério 3: Momentum e Tendência (priceHistory analysis)
      const ticks = priceHistory[pool.token] || [];
      if (ticks.length >= 3) {
        const last = ticks[ticks.length - 1];
        const first = ticks[0];
        if (last > first * 1.5) return true; // 50% pump
      }
      
      return false;
    });
  }, [pools, priceHistory]);

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="bg-fuchsia-500/10 border border-fuchsia-500/20 rounded-xl p-4 flex items-center justify-between shadow-lg shadow-fuchsia-500/5">
        <div>
          <h2 className="text-fuchsia-400 font-black text-lg flex items-center gap-2">
            🚀 Top Volume & Smart Scans
          </h2>
          <p className="text-zinc-400 text-xs mt-1">
            Exibindo exclusivamente tokens com Volume inicial &gt; 3 SOL ou MCap acima de $15k. Filtrado em tempo real na UI.
          </p>
        </div>
        <div className="bg-black/40 px-3 py-1.5 rounded-lg border border-zinc-800 font-mono text-sm text-zinc-300">
          <span className="text-fuchsia-400 font-bold">{smartPools.length}</span> Tokens Filtrados
        </div>
      </div>
      
      <div className="flex-1 bg-black/20 rounded-xl border border-zinc-800/40 overflow-hidden h-[700px]">
        {/* Reutiliza o componente de Screener limpo, mas com o feed já filtrado! */}
        <MayhemScreenerTable 
          pools={smartPools} 
          positions={positions} 
          history={history} 
          priceHistory={priceHistory}
          networkName="Solana" 
        />
      </div>
    </div>
  );
}
