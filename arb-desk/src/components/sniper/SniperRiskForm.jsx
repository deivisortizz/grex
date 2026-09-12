import React, { useState, useEffect } from 'react'
import { useSniperContext } from '../../context/SniperContext'
import { Sliders, Save, AlertTriangle } from 'lucide-react'

export default function SniperRiskForm() {
  const { config, updateConfig, isConnected } = useSniperContext()
  
  // Local state to manage form inputs before saving
  const [localConfig, setLocalConfig] = useState({
    snipe_size_eth: 0.0005,
    min_pool_weth: 0.05,
    tp_pct: 100,
    sl_pct: 20
  })

  // Sync local state when config from WS changes
  useEffect(() => {
    if (config) {
      setLocalConfig(config)
    }
  }, [config])

  const handleChange = (key, value) => {
    setLocalConfig(prev => ({ ...prev, [key]: Number(value) }))
  }

  const handleSave = () => {
    updateConfig(localConfig)
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-6">
        <Sliders size={20} className="text-zinc-400" />
        <h3 className="text-lg font-bold text-white tracking-tight">Gestão de Risco HFT</h3>
      </div>

      <div className="flex flex-col gap-5 flex-grow">
        
        {/* Snipe Size */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm font-semibold text-zinc-300">Tamanho do Snipe (ETH)</label>
            <span className="text-sm font-mono text-zinc-500">{localConfig.snipe_size_eth} ETH</span>
          </div>
          <input 
            type="number"
            step="0.0001"
            value={localConfig.snipe_size_eth}
            onChange={(e) => handleChange('snipe_size_eth', e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-white font-mono text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Min WETH Reserve */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm font-semibold text-zinc-300">Reserva Mínima (WETH)</label>
            <span className="text-sm font-mono text-zinc-500">{localConfig.min_pool_weth} WETH</span>
          </div>
          <input 
            type="range"
            min="0.01"
            max="1.0"
            step="0.01"
            value={localConfig.min_pool_weth}
            onChange={(e) => handleChange('min_pool_weth', e.target.value)}
            className="w-full accent-blue-500 h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer"
          />
          <div className="flex justify-between text-xs text-zinc-600 mt-1">
            <span>0.01</span>
            <span>1.0</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Take Profit */}
          <div>
            <div className="flex justify-between mb-1">
              <label className="text-xs font-semibold text-emerald-400">Take-Profit</label>
            </div>
            <div className="relative">
              <input 
                type="number"
                value={localConfig.tp_pct}
                onChange={(e) => handleChange('tp_pct', e.target.value)}
                className="w-full bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2 text-emerald-400 font-mono text-sm focus:outline-none focus:border-emerald-500"
              />
              <span className="absolute right-3 top-2 text-emerald-500/50 text-sm">%</span>
            </div>
          </div>

          {/* Stop Loss */}
          <div>
            <div className="flex justify-between mb-1">
              <label className="text-xs font-semibold text-rose-400">Stop-Loss</label>
            </div>
            <div className="relative">
              <input 
                type="number"
                value={localConfig.sl_pct}
                onChange={(e) => handleChange('sl_pct', e.target.value)}
                className="w-full bg-rose-500/10 border border-rose-500/30 rounded-lg p-2 text-rose-400 font-mono text-sm focus:outline-none focus:border-rose-500"
              />
              <span className="absolute right-3 top-2 text-rose-500/50 text-sm">%</span>
            </div>
          </div>
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={!isConnected}
        className="mt-6 w-full py-3 rounded-xl bg-blue-500 hover:bg-blue-400 text-zinc-950 font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Save size={18} />
        Aplicar Parâmetros
      </button>

      <div className="mt-3 flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-lg">
        <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
        <p className="text-[10px] leading-tight text-amber-500/80">
          As alterações entram em vigor imediatamente via WebSocket, sem necessidade de reiniciar o bot.
        </p>
      </div>
    </div>
  )
}
