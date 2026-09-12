import React from 'react'
import { Activity, Copy, ExternalLink, Zap } from 'lucide-react'
import { useSniperContext } from '../../context/SniperContext'

export default function PoolFeedTable() {
  const { pools, sendCommand } = useSniperContext()

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
  }

  const formatAddress = (addr) => {
    if (!addr) return ''
    return `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`
  }

  const handleManualSnipe = (token) => {
    sendCommand({
      type: 'manual_snipe',
      token: token
    })
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl flex flex-col h-full overflow-hidden shadow-xl">
      <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <div className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
          </div>
          <h2 className="font-bold text-white tracking-tight">Live Pool Stream</h2>
        </div>
        <div className="text-xs font-mono text-zinc-500">
          Last 50 detected
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-zinc-950/50 text-zinc-400 sticky top-0 z-10 backdrop-blur-md">
            <tr>
              <th className="px-5 py-3 font-semibold text-xs uppercase tracking-wider">Time</th>
              <th className="px-5 py-3 font-semibold text-xs uppercase tracking-wider">Token</th>
              <th className="px-5 py-3 font-semibold text-xs uppercase tracking-wider">Pair</th>
              <th className="px-5 py-3 font-semibold text-xs uppercase tracking-wider text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {pools.length === 0 ? (
              <tr>
                <td colSpan="4" className="px-5 py-10 text-center text-zinc-500">
                  <Activity className="mx-auto h-8 w-8 mb-3 opacity-20" />
                  <p>Escutando a mempool da rede Base...</p>
                </td>
              </tr>
            ) : (
              pools.map((pool) => (
                <tr key={pool.id} className="hover:bg-zinc-800/30 transition-colors group">
                  <td className="px-5 py-3 font-mono text-zinc-400">
                    {new Date(pool.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-emerald-400">{formatAddress(pool.token)}</span>
                      <button 
                        onClick={() => copyToClipboard(pool.token)}
                        className="text-zinc-500 hover:text-white transition-colors opacity-0 group-hover:opacity-100"
                        title="Copiar Contrato"
                      >
                        <Copy size={14} />
                      </button>
                      <a 
                        href={`https://basescan.org/token/${pool.token}`} 
                        target="_blank" 
                        rel="noreferrer"
                        className="text-zinc-500 hover:text-blue-400 transition-colors opacity-0 group-hover:opacity-100"
                        title="Ver no Basescan"
                      >
                        <ExternalLink size={14} />
                      </a>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-1 bg-blue-500/10 text-blue-400 rounded text-xs font-bold border border-blue-500/20">
                        {pool.pairedWith}
                      </span>
                      {pool.skipped && (
                        <span className="px-1.5 py-0.5 bg-zinc-800/80 text-zinc-400 rounded text-[10px] font-mono border border-zinc-700">
                          Pausado
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button 
                      onClick={() => handleManualSnipe(pool.token)}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white p-1.5 rounded-lg transition-colors shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                      title="Manual Snipe"
                    >
                      <Zap size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
