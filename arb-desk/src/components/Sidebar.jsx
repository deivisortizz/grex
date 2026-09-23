import {
  LineChart,
  Target,
  Bot,
  Activity,
  History,
  Settings,
  HelpCircle,
  Waves,
  Flame,
  Shield,
  User,
  Zap,
  Users,
  Globe2,
  Rocket
} from 'lucide-react'

const navItems = [
  { name: 'Cotações', icon: LineChart },
  { name: 'Analytics', icon: Activity },
  { name: 'Oceano Azul', icon: Waves },
  { name: 'Pares Exóticos', icon: Globe2, accent: 'amber' },
  { name: 'Base Sniper', icon: Flame, accent: 'orange' },
  { name: 'Solana Sniper', icon: Zap, accent: 'violet' },
  { name: 'Copy Trading', icon: Users, accent: 'cyan' },
  { name: 'Listing Sniper', icon: Rocket, accent: 'pink' },
  { name: 'Histórico', icon: History },
  { name: 'Configurações', icon: Settings },
  { name: 'Corretoras', icon: Target },
  { name: 'Autobot', icon: Bot },
  { name: 'Minha Conta', icon: User },
  { name: 'Guia de Ativação', icon: HelpCircle },
]

export default function Sidebar({ wsStatus = 'Offline', ping, activeTab, setActiveTab, isOpen, setIsOpen, isAdmin }) {
  const visibleNavItems = isAdmin 
    ? [...navItems, { name: 'Master Admin', icon: Shield, accent: 'purple' }] 
    : navItems
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-40 md:hidden backdrop-blur-sm"
          onClick={() => setIsOpen(false)}
        />
      )}
      
      {/* Sidebar container */}
      <aside className={`w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen fixed top-0 left-0 z-50 transition-transform duration-300 ease-in-out md:translate-x-0 ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}>
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
        {visibleNavItems.map((item) => {
          const Icon = item.icon
          const isOcean = item.name === 'Oceano Azul'
          const isExotic = item.name === 'Pares Exóticos'
          const isSniper = item.name === 'Base Sniper'
          const isSolana = item.name === 'Solana Sniper'
          const isCopy = item.name === 'Copy Trading'
          const isListing = item.name === 'Listing Sniper'
          const isAdminTab = item.name === 'Master Admin'
          return (
            <button
              key={item.name}
              onClick={() => setActiveTab(item.name)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                activeTab === item.name
                  ? isOcean
                    ? 'bg-blue-500/10 text-white border border-blue-500/30'
                    : isExotic
                      ? 'bg-amber-500/10 text-white border border-amber-500/30'
                      : isSniper
                        ? 'bg-orange-500/10 text-white border border-orange-500/30'
                        : isSolana
                          ? 'bg-violet-500/10 text-white border border-violet-500/30'
                          : isCopy
                            ? 'bg-cyan-500/10 text-white border border-cyan-500/30'
                            : isListing
                              ? 'bg-pink-500/10 text-white border border-pink-500/30'
                              : isAdminTab
                                ? 'bg-purple-500/10 text-white border border-purple-500/30'
                                : 'bg-zinc-800 text-white'
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
              }`}
            >
              <Icon
                size={18}
                className={
                  activeTab === item.name
                    ? isOcean
                      ? 'text-blue-400'
                      : isExotic
                        ? 'text-amber-400'
                        : isSniper
                          ? 'text-orange-400'
                          : isSolana
                            ? 'text-violet-400'
                            : isCopy
                              ? 'text-cyan-400'
                              : isListing
                                ? 'text-pink-400'
                                : isAdminTab
                                  ? 'text-purple-400'
                                  : 'text-emerald-400'
                    : ''
                }
              />
              {item.name}
              {isOcean && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-blue-500/70 bg-blue-500/10 px-1.5 py-0.5 rounded">
                  LIVE
                </span>
              )}
              {isExotic && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-amber-400 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded font-mono">
                  NOVO
                </span>
              )}
              {isSniper && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-orange-500/70 bg-orange-500/10 px-1.5 py-0.5 rounded">
                  BASE
                </span>
              )}
              {isSolana && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-violet-500/70 bg-violet-500/10 px-1.5 py-0.5 rounded">
                  SOL
                </span>
              )}
              {isCopy && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-cyan-400 bg-cyan-500/15 border border-cyan-500/30 px-1.5 py-0.5 rounded font-mono">
                  SMART
                </span>
              )}
              {isListing && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-pink-400 bg-pink-500/15 border border-pink-500/30 px-1.5 py-0.5 rounded font-mono">
                  NOVO
                </span>
              )}
              {isAdminTab && (
                <span className="ml-auto text-[9px] font-bold uppercase tracking-widest text-purple-500/70 bg-purple-500/10 px-1.5 py-0.5 rounded">
                  SAAS
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
    </>
  )
}
