import React from 'react'
import { SniperProvider, useSniperContext } from '../../context/SniperContext'
import PoolFeedTable from './PoolFeedTable'
import SniperTerminal from './SniperTerminal'
import SniperMetrics from './SniperMetrics'
import SniperRiskForm from './SniperRiskForm'
import SniperPositionsTable from './SniperPositionsTable'
import BurnerWalletConfig from '../BurnerWalletConfig'
import { Wifi, WifiOff, Wallet, Crosshair, Layers, Power, Play, Pause } from 'lucide-react'

function SniperContent() {
  const { isConnected, walletStatus, pools, isActive, toggleSniper } = useSniperContext()

  const maskAddress = (addr) => {
    if (!addr) return ''
    return `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`
  }

  return (
    <div className="flex flex-col gap-6">

      {/* ── Master Control Banner ── */}
      <div className={`border rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all duration-300 ${
        isActive
          ? 'bg-zinc-900/90 border-emerald-500/30 shadow-[0_0_25px_rgba(16,185,129,0.08)]'
          : 'bg-zinc-900/90 border-rose-500/30 shadow-[0_0_25px_rgba(244,63,94,0.08)]'
      }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center border transition-all shrink-0 ${
            isActive
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}>
            <Power size={24} className={isActive ? 'animate-pulse' : ''} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-lg font-bold text-white tracking-tight">Base Meme Sniper Engine</h2>
              <span className={`px-2.5 py-0.5 text-xs font-bold font-mono rounded-full border flex items-center gap-1.5 ${
                isActive
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                  : 'bg-rose-500/15 border-rose-500/40 text-rose-400'
              }`}>
                <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400 animate-ping' : 'bg-rose-500'}`} />
                {isActive ? 'EXECUÇÃO ATIVA' : 'SNIPER PAUSADO'}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {isActive
                ? 'Ordens automáticas, anti-honeypot, LP check e auto-approve de router ativos.'
                : 'Pausado: novos pools são monitorados, mas nenhuma compra será enviada.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <button
            onClick={() => toggleSniper(!isActive)}
            disabled={!isConnected}
            className={`w-full sm:w-auto px-6 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2.5 transition-all shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
              isActive
                ? 'bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/50 hover:border-rose-400 shadow-rose-500/10 active:scale-95'
                : 'bg-emerald-500 hover:bg-emerald-400 text-zinc-950 shadow-emerald-500/20 active:scale-95'
            }`}
          >
            {isActive ? (
              <>
                <Pause size={18} className="fill-current" />
                <span>Pausar Sniper</span>
              </>
            ) : (
              <>
                <Play size={18} className="fill-current" />
                <span>Ativar Sniper</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── Analytics Metrics Cards ── */}
      <SniperMetrics />

      {/* ── Status Bar ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">

        {/* WS Connection */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          {isConnected ? (
            <>
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                <Wifi size={20} className="text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-zinc-500">Sniper WS</p>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-sm font-bold text-emerald-400">Online</span>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 flex items-center justify-center">
                <WifiOff size={20} className="text-rose-400" />
              </div>
              <div>
                <p className="text-xs text-zinc-500">Sniper WS</p>
                <span className="text-sm font-bold text-rose-400">Offline</span>
              </div>
            </>
          )}
        </div>

        {/* Network */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
            <Layers size={20} className="text-blue-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Rede</p>
            <span className="text-sm font-bold text-blue-400">Base Mainnet</span>
          </div>
        </div>

        {/* Pools Detected */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
            <Crosshair size={20} className="text-amber-400" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Pools Detectados</p>
            <span className="text-2xl font-bold font-mono text-white">{pools.length}</span>
          </div>
        </div>

        {/* Wallet */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${walletStatus ? 'bg-emerald-500/10' : 'bg-zinc-800'}`}>
            <Wallet size={20} className={walletStatus ? 'text-emerald-400' : 'text-zinc-500'} />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Wallet</p>
            {walletStatus ? (
              <span className="text-sm font-bold text-emerald-400 font-mono">
                {maskAddress(walletStatus)}
              </span>
            ) : (
              <span className="text-sm font-bold text-amber-400">Read-Only</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Positions Table (Full Width) ── */}
      <div className="h-[280px]">
        <SniperPositionsTable />
      </div>

      {/* ── Main Grid: Pool Feed + Risk Form ── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Pool Feed – 2/3 */}
        <div className="xl:col-span-2 h-[420px]">
          <PoolFeedTable />
        </div>

        {/* Risk Form + Wallet – 1/3 */}
        <div className="xl:col-span-1 flex flex-col gap-6">
          <SniperRiskForm />
          <BurnerWalletConfig />
        </div>
      </div>

      {/* ── Terminal ── */}
      <div className="h-72">
        <SniperTerminal />
      </div>
    </div>
  )
}

export default function SniperDashboard() {
  return (
    <SniperProvider>
      <SniperContent />
    </SniperProvider>
  )
}
