import React, { useState, useEffect } from 'react';
import { useSolanaWebSocket } from '../../hooks/useSolanaWebSocket';
import SolanaSniperTab from './SolanaSniperTab';
import SolanaCopyTrading from './SolanaCopyTrading';
import SolanaMetrics from './SolanaMetrics';
import SolanaPositionsTable from './SolanaPositionsTable';
import SolanaHistoryTable from './SolanaHistoryTable';
import SolanaPnLHistory from './SolanaPnLHistory';
import SmartScansTab from './SmartScansTab';
import MayhemScreenerTable from '../sniper/MayhemScreenerTable';
import { Power, Wifi, WifiOff, Layers, Crosshair, Wallet, Users, Activity } from 'lucide-react';

export default function SolanaDashboard({ initialSubTab = 'sniper' }) {
  const { status, config, logs, metrics, positions, pools, history, priceHistory, smartAlert, setSmartAlert, sendCommand } = useSolanaWebSocket();
  const [activeSubTab, setActiveSubTab] = useState(initialSubTab);

  useEffect(() => {
    if (smartAlert) {
      const timer = setTimeout(() => {
        setSmartAlert(null);
      }, 7000); // Exibe por 7 segundos
      return () => clearTimeout(timer);
    }
  }, [smartAlert, setSmartAlert]);

  useEffect(() => {
    if (initialSubTab) {
      setActiveSubTab(initialSubTab);
    }
  }, [initialSubTab]);

  const isActive = config.is_active === true || config.status === 'watching' || config.status === 'monitoring_position';

  const toggleSniper = (activate) => {
    if (activate) {
      sendCommand('start');
    } else {
      sendCommand('stop');
    }
  };

  // [FIX] Antes chamava fetch('/api/manual-sell'|'/api/manual-buy'), rotas que nunca
  // existiram em server.py (processo separado, sem acesso à carteira/engine do sniper).
  // O comando real de compra/venda manual só existe via WebSocket (force_buy/force_sell,
  // tratado em solana_core.py ws_handler), que já está conectado e autenticado aqui.
  const handleManualSell = (token) => {
    sendCommand('force_sell', { token });
  };

  const handleAlertBuy = (token) => {
    sendCommand('force_buy', { token });
    setSmartAlert(null);
  };

  return (
    <div className="flex flex-col gap-6 w-full max-w-7xl mx-auto relative">
      {/* Floating Smart Alert Toast */}
      {smartAlert && (
        <div className="fixed top-24 right-8 z-50 animate-in slide-in-from-right-8 fade-in duration-300">
          <div className="bg-zinc-950/95 border border-fuchsia-500/50 shadow-2xl shadow-fuchsia-500/20 p-4 rounded-xl flex items-start gap-4 max-w-sm backdrop-blur-md">
            <div className="text-3xl animate-bounce">🐟</div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <h4 className="text-fuchsia-400 font-black text-sm uppercase tracking-wider">Peixe à Vista!</h4>
                <button onClick={() => setSmartAlert(null)} className="text-zinc-500 hover:text-white">&times;</button>
              </div>
              <p className="text-zinc-300 text-sm font-bold mt-1">{smartAlert.symbol} <span className="text-xs text-zinc-500 font-mono">detectado com</span></p>
              <p className="text-emerald-400 text-xs font-mono mb-3">{smartAlert.reason}</p>
              <div className="flex gap-2">
                <button 
                  onClick={() => {
                    setActiveSubTab('smart_scans');
                    setSmartAlert(null);
                  }}
                  className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-bold py-1.5 rounded-lg transition-colors border border-zinc-700"
                >
                  Ver no Radar
                </button>
                <button 
                  onClick={() => handleAlertBuy(smartAlert.token)}
                  className="flex-1 bg-fuchsia-600 hover:bg-fuchsia-500 text-white text-xs font-bold py-1.5 rounded-lg transition-colors shadow-lg shadow-fuchsia-500/30 flex items-center justify-center gap-1"
                >
                  <Crosshair size={12} /> Snipe
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* ── Master Control Banner ── */}
      <div className={`border rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all duration-300 ${
        isActive
          ? 'bg-zinc-900/90 border-emerald-500/30 shadow-[0_0_25px_rgba(16,185,129,0.08)]'
          : 'bg-zinc-900/90 border-violet-500/30 shadow-[0_0_25px_rgba(139,92,246,0.08)]'
      }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center border transition-all shrink-0 ${
            isActive
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-violet-500/10 border-violet-500/30 text-violet-400'
          }`}>
            <Power size={24} className={isActive ? 'animate-pulse' : ''} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-lg font-bold text-white tracking-tight">Solana Sniper Engine (Pump.fun)</h2>
              <span className={`px-2.5 py-0.5 text-xs font-bold font-mono rounded-full border flex items-center gap-1.5 ${
                isActive
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                  : 'bg-violet-500/15 border-violet-500/40 text-violet-400'
              }`}>
                <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400 animate-ping' : 'bg-violet-500'}`} />
                {isActive ? 'EXECUÇÃO ATIVA' : 'SNIPER PAUSADO'}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {isActive
                ? 'Ordens automáticas e monitoramento de logs da Pump.fun ativos.'
                : 'Pausado: o websocket Helius/RPC está ocioso.'}
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto justify-end">
          <button
            onClick={() => toggleSniper(!isActive)}
            className={`w-full sm:w-auto px-6 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2.5 transition-all shadow-lg cursor-pointer ${
              isActive
                ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500/20'
                : 'bg-emerald-500 hover:bg-emerald-400 text-zinc-900'
            }`}
          >
            {isActive ? 'Parar Sniper' : 'Ativar Sniper'}
          </button>
        </div>
      </div>

      <SolanaMetrics metrics={metrics} />

      {/* ── Status Bar ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* WS Connection */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          {status === 'Online' ? (
            <>
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0">
                <Wifi size={20} className="text-emerald-400" />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-zinc-500 truncate">Sniper WS</p>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                  <span className="text-sm font-bold text-emerald-400 truncate">Online</span>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 flex items-center justify-center shrink-0">
                <WifiOff size={20} className="text-rose-400" />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-zinc-500 truncate">Sniper WS</p>
                <span className="text-sm font-bold text-rose-400 truncate">Offline</span>
              </div>
            </>
          )}
        </div>

        {/* Network */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-500/10 flex items-center justify-center shrink-0">
            <Layers size={20} className="text-violet-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-zinc-500 truncate">Rede</p>
            <span className="text-sm font-bold text-violet-400 truncate">Solana Mainnet</span>
          </div>
        </div>

        {/* Pools Detected */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center shrink-0">
            <Crosshair size={20} className="text-amber-400" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-zinc-500 truncate">Pools (Pump.fun)</p>
            <span className="text-2xl font-bold font-mono text-white truncate">
              {metrics?.total_trades || 0}
            </span>
          </div>
        </div>

        {/* Wallet */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${isActive || config.target_token ? 'bg-emerald-500/10' : 'bg-zinc-800'}`}>
            <Wallet size={20} className={isActive || config.target_token ? 'text-emerald-400' : 'text-zinc-500'} />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-zinc-500 truncate">Burner Wallet</p>
            {isActive || config.target_token ? (
              <span className="text-sm font-bold font-mono text-emerald-400 truncate">Ativa</span>
            ) : (
              <span className="text-sm font-bold text-zinc-500 truncate">Aguardando</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Sub-Navigation: Mode Selector ── */}
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 pb-3">
        <button
          onClick={() => setActiveSubTab('sniper')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all cursor-pointer ${
            activeSubTab === 'sniper'
              ? 'bg-violet-600 text-white shadow-lg shadow-violet-600/25 border border-violet-500'
              : 'bg-zinc-900/80 text-zinc-400 hover:text-white hover:bg-zinc-800 border border-zinc-800'
          }`}
        >
          <Crosshair size={16} />
          Sniper Pump.fun (Autônomo)
        </button>

        <button
          onClick={() => setActiveSubTab('copy_trading')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all cursor-pointer ${
            activeSubTab === 'copy_trading'
              ? 'bg-cyan-500 text-zinc-950 shadow-lg shadow-cyan-500/25 border border-cyan-400 font-extrabold'
              : 'bg-zinc-900/80 text-zinc-400 hover:text-white hover:bg-zinc-800 border border-zinc-800'
          }`}
        >
          <Users size={16} />
          Copy Trading & Wallet Hunter
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded uppercase ${
            activeSubTab === 'copy_trading'
              ? 'bg-zinc-950/30 text-zinc-900 font-bold'
              : 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
          }`}>
            Smart Money
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('pnl_history')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all cursor-pointer ${
            activeSubTab === 'pnl_history'
              ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/25 border border-emerald-500'
              : 'bg-zinc-900/80 text-zinc-400 hover:text-white hover:bg-zinc-800 border border-zinc-800'
          }`}
        >
          <Activity size={16} />
          Histórico & PnL
        </button>

        <button
          onClick={() => setActiveSubTab('smart_scans')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all cursor-pointer ${
            activeSubTab === 'smart_scans'
              ? 'bg-fuchsia-600 text-white shadow-lg shadow-fuchsia-600/25 border border-fuchsia-500'
              : 'bg-zinc-900/80 text-zinc-400 hover:text-white hover:bg-zinc-800 border border-zinc-800'
          }`}
        >
          <span className="text-lg">🚀</span>
          Smart Scans
        </button>
      </div>

      {activeSubTab === 'sniper' ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
          <SolanaSniperTab isActive={isActive} sendCommand={sendCommand} onSwitchToCopy={() => setActiveSubTab('copy_trading')} />
          <div className="flex flex-col gap-6 h-[800px]">
            <MayhemScreenerTable
              pools={pools}
              positions={positions}
              history={history}
              priceHistory={priceHistory}
              sendCommand={sendCommand}
              networkName="Solana"
            />
          </div>
        </div>
      ) : activeSubTab === 'copy_trading' ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-8 flex flex-col gap-6">
            <SolanaCopyTrading />
          </div>
          <div className="lg:col-span-4 flex flex-col gap-6 h-[800px]">
            <MayhemScreenerTable
              pools={pools}
              positions={positions}
              history={history}
              priceHistory={priceHistory}
              sendCommand={sendCommand}
              networkName="Solana"
            />
          </div>
        </div>
      ) : activeSubTab === 'pnl_history' ? (
        <div className="h-[800px]">
          <SolanaPnLHistory sendCommand={sendCommand} />
        </div>
      ) : activeSubTab === 'smart_scans' ? (
        <div className="h-[800px]">
          <SmartScansTab pools={pools} positions={positions} history={history} priceHistory={priceHistory} />
        </div>
      ) : null}


      {/* Terminal Logs */}
      <div className="bg-black border border-zinc-800 rounded-2xl p-5 mt-6 font-mono text-sm h-64 overflow-y-auto">
        <div className="text-zinc-500 mb-2">// WSS Logs da Solana</div>
        {logs.map((log, i) => (
          <div key={i} className="text-zinc-300 mb-1">{log}</div>
        ))}
        {logs.length === 0 && <div className="text-zinc-700">Nenhum log capturado ainda...</div>}
      </div>

    </div>
  );
}
