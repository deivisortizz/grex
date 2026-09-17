import React from 'react';
import { useSolanaWebSocket } from '../../hooks/useSolanaWebSocket';
import SolanaSniperTab from './SolanaSniperTab';
import SolanaMetrics from './SolanaMetrics';
import SolanaPositionsTable from './SolanaPositionsTable';
import { Power, Wifi, WifiOff, Layers, Crosshair, Wallet } from 'lucide-react';

export default function SolanaDashboard() {
  const { status, config, logs, metrics, positions, sendCommand } = useSolanaWebSocket();
  const isActive = config.is_active === true || config.status === 'watching' || config.status === 'monitoring_position';

  const toggleSniper = (activate) => {
    if (activate) {
      sendCommand('start');
    } else {
      sendCommand('stop');
    }
  };

  const forceBuy = () => {
    let token = config.target_token;
    if (!token) {
      token = window.prompt("Nenhum token alvo configurado.\nInsira o endereço (Mint) do token que deseja comprar AGORA:");
      if (!token) return;
    }
    const confirmBuy = window.confirm(`ATENÇÃO: Você está prestes a forçar uma COMPRA REAL na Solana para o token:\n${token}\n\nDeseja continuar?`);
    if (confirmBuy) {
      sendCommand('force_buy', { token });
    }
  };

  const forceSell = () => {
    let token = config.target_token;
    if (!token) {
      token = window.prompt("Nenhum token alvo configurado.\nInsira o endereço (Mint) do token que deseja VENDER AGORA (Dump 100%):");
      if (!token) return;
    }
    const confirmSell = window.confirm(`🚨 PANIC SELL 🚨\n\nVocê está prestes a fazer o DUMP (Vender 100%) da sua posição no token:\n${token}\n\nDeseja confirmar a venda imediata na rede?`);
    if (confirmSell) {
      sendCommand('force_sell', { token });
    }
  };

  return (
    <div className="flex flex-col gap-6 w-full max-w-7xl mx-auto">
      
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
            onClick={forceBuy}
            className="w-full sm:w-auto px-5 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-lg cursor-pointer bg-amber-500 hover:bg-amber-400 text-zinc-900 shadow-amber-500/20 active:scale-95"
          >
            ⚡ Forçar Compra
          </button>

          <button
            onClick={forceSell}
            className="w-full sm:w-auto px-5 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-lg cursor-pointer bg-rose-600 hover:bg-rose-500 text-white shadow-rose-500/20 active:scale-95"
          >
            🔴 Forçar Venda
          </button>

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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <SolanaSniperTab isActive={isActive} sendCommand={sendCommand} />
        <SolanaPositionsTable positions={positions} />
      </div>

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
