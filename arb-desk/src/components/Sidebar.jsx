import {
  LineChart,
  Target,
  Bot,
  Activity,
  History,
  Settings,
  HelpCircle,
  Waves,
} from 'lucide-react'

const navItems = [
  { name: 'Cotações', icon: LineChart },
  { name: 'Analytics', icon: Activity },
  { name: 'Oceano Azul', icon: Waves },
  { name: 'Histórico', icon: History },
  { name: 'Configurações', icon: Settings },
  { name: 'Corretoras', icon: Target },
  { name: 'Autobot', icon: Bot },
  { name: 'Guia de Ativação', icon: HelpCircle },
]

export default function Sidebar({ wsStatus = 'Offline', ping, activeTab, setActiveTab }) {
  return (
    <aside className="w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen fixed top-0 left-0">
      <div className="p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-wider text-white">Grex <span className="text-emerald-500">.</span></h1>
          <div className="flex items-center" title={`WebSocket: ${wsStatus}`}>
            <span className={`w-2 h-2 rounded-full ${wsStatus === 'Online' ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]' : 'bg-rose-500'}`}></span>
          </div>
        </div>
        <p className="text-xs text-zinc-400 mt-1">HFT Engine Interface</p>
      </div>
      <nav className="flex-1 px-4 space-y-1 mt-4 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon
          const isOcean = item.name === 'Oceano Azul'
          return (
            <button
              key={item.name}
              onClick={() => setActiveTab(item.name)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === item.name
                  ? isOcean
                    ? 'bg-blue-500/10 text-white border border-blue-500/30'
                    : 'bg-zinc-800 text-white'
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
              }`}
            >
              <Icon
                size={18}
                className={
                  activeTab === item.name
                    ? isOcean ? 'text-blue-400' : 'text-emerald-400'
                    : ''
                }
              />
              {item.name}
              {isOcean && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-blue-500/70 bg-blue-500/10 px-1.5 py-0.5 rounded">
                  LIVE
                </span>
              )}
            </button>
          )
        })}
      </nav>
      <div className="p-4 border-t border-zinc-800">
        <div className="bg-zinc-950/50 rounded p-3 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-400">Status</span>
            <span className={`flex items-center gap-1.5 text-xs font-medium ${wsStatus === 'Online' ? 'text-emerald-400' : 'text-rose-400'}`}>
              <span className={`w-2 h-2 rounded-full ${wsStatus === 'Online' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`}></span>
              {wsStatus}
            </span>
          </div>
          {wsStatus === 'Online' && ping !== null && ping !== undefined && (
            <div className="flex items-center justify-between border-t border-zinc-800/50 pt-2 mt-1">
              <span className="text-xs text-zinc-400">Ping</span>
              <span className={`text-xs font-mono font-medium ${ping < 50 ? 'text-emerald-400' : 'text-amber-400'}`}>{ping}ms</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
