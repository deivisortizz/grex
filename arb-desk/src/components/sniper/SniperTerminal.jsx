import React, { useEffect, useRef } from 'react'
import { Terminal } from 'lucide-react'
import { useSniperContext } from '../../context/SniperContext'

export default function SniperTerminal() {
  const { logs } = useSniperContext()
  const endOfLogRef = useRef(null)

  useEffect(() => {
    if (endOfLogRef.current) {
      endOfLogRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  const getColor = (level) => {
    switch (level) {
      case 'ERROR': return 'text-rose-500'
      case 'WARNING': return 'text-amber-500'
      case 'SUCCESS': return 'text-emerald-500'
      default: return 'text-zinc-400'
    }
  }

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-2xl flex flex-col h-full overflow-hidden shadow-2xl">
      <div className="px-4 py-2 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-zinc-500" />
          <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider">HFT Terminal</span>
        </div>
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
        </div>
      </div>
      
      <div className="flex-1 p-4 overflow-y-auto font-mono text-xs leading-relaxed space-y-1.5 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
        {logs.length === 0 ? (
          <div className="text-zinc-600 italic">Aguardando eventos do mempool...</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="break-all">
              <span className="text-zinc-600 mr-2">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
              <span className={`font-bold mr-2 ${getColor(log.level)}`}>[{log.level}]</span>
              <span className="text-zinc-300">{log.message.split(' - ').slice(1).join(' - ') || log.message}</span>
            </div>
          ))
        )}
        <div ref={endOfLogRef} />
      </div>
    </div>
  )
}
