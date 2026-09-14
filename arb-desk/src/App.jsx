import { useState, useEffect, useRef } from 'react'
import { Menu } from 'lucide-react'
import Sidebar from './components/Sidebar'
import DashboardTab from './components/DashboardTab'
import ConfigTab from './components/ConfigTab'
import HistoryTab from './components/HistoryTab'
import AnalyticsTab from './components/AnalyticsTab'
import AutobotTab from './components/AutobotTab'
import ExchangesTab from './components/ExchangesTab'
import BlueOceanDesk from './components/BlueOceanDesk'
import Login from './components/Login'
import Register from './components/Register'
import SniperDashboard from './components/sniper/SniperDashboard'
import AdminDashboard from './components/admin/AdminDashboard'
import AccountSettings from './components/AccountSettings'

function App() {
  // Controle do menu mobile
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  // Estado de autenticação
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [isAdmin, setIsAdmin] = useState(localStorage.getItem('is_admin') === 'true')
  const [isAuthenticated, setIsAuthenticated] = useState(!!token)

  const [activeTab, setActiveTab] = useState('Cotações')
  const [marketData, setMarketData] = useState({})
  const [wsStatus, setWsStatus] = useState('Conectando...')
  const [ping, setPing] = useState(null)

  const [config, setConfig] = useState({ target_spread: 0.30, trade_amount: 11.0, is_spatial_active: false, is_triangular_active: false, exchanges: [] })
  const [history, setHistory] = useState([])
  const [chartData, setChartData] = useState([])
  const [triangularData, setTriangularData] = useState([])

  const wsRef = useRef(null)

  useEffect(() => {
    const currentHost = window.location.hostname;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Ignorando .env local hardcoded e forçando uso dinâmico para evitar ERR_CONNECTION_REFUSED
    const wsUrl = `${wsProtocol}//${currentHost}:8765`;
    
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    let pingInterval;

    ws.onopen = () => {
      setWsStatus('Online')
      
      // Envia o token JWT de autenticação na conexão inicial
      const currentToken = localStorage.getItem('token')
      ws.send(JSON.stringify({ type: 'auth', token: currentToken }))
      
      pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }))
        }
      }, 1000)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'pong') {
          setPing(Date.now() - data.timestamp)
        } else if (data.type === 'config') {
          setConfig({
            target_spread: data.target_spread,
            trade_amount: data.trade_amount,
            is_spatial_active: data.is_spatial_active,
            is_triangular_active: data.is_triangular_active,
            exchanges: data.exchanges || []
          })
        } else if (data.type === 'history') {
          setHistory(data.data || [])
        } else if (data.type === 'triangular_data') {
          setTriangularData(data.exchanges || [])
        } else if (data.type === 'new_trade') {
          setHistory(prev => [...prev, data.data])
        } else if (data.type === 'market_data') {
          setMarketData(data)
          if (data.net_spread !== undefined) {
            setChartData(prev => {
              const now = new Date().toLocaleTimeString('pt-BR', { hour12: false, minute: '2-digit', second: '2-digit' })
              const newData = [...prev, { time: now, net: data.net_spread, gross: data.gross_spread }]
              if (newData.length > 50) return newData.slice(newData.length - 50)
              return newData
            })
          }
        }
      } catch (e) {
        console.error("Erro ao parsear JSON do WS", e)
      }
    }

    ws.onclose = () => {
      setWsStatus('Offline')
      setPing(null)
    }

    return () => {
      clearInterval(pingInterval)
      ws.close()
    }
  }, [])

  const sendConfigUpdate = (newConfig) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'config_update', ...newConfig }))
    }
  }

  const sendCommand = (command, extraPayload = {}) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'command', command, ...extraPayload }))
    }
  }

  const handleLogin = (newToken, adminStatus = false) => {
    setToken(newToken)
    setIsAdmin(adminStatus)
    setIsAuthenticated(true)
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('is_admin')
    setToken(null)
    setIsAdmin(false)
    setIsAuthenticated(false)
  }

  const urlParams = new URLSearchParams(window.location.search);
  const inviteToken = urlParams.get('token');
  const isInviteRoute = window.location.pathname === '/register' && inviteToken;

  if (!isAuthenticated) {
    if (isInviteRoute) {
      return <Register inviteToken={inviteToken} onNavigateLogin={() => window.location.href = '/'} />
    }
    return <Login onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex font-sans text-zinc-100 overflow-x-hidden">
      <Sidebar 
        wsStatus={wsStatus} 
        ping={ping} 
        activeTab={activeTab} 
        setActiveTab={(tab) => {
          setActiveTab(tab)
          setIsMobileMenuOpen(false)
        }} 
        isOpen={isMobileMenuOpen}
        setIsOpen={setIsMobileMenuOpen}
        isAdmin={isAdmin}
      />

      {/* Main Content Area */}
      <main className="flex-1 md:ml-64 p-4 md:p-8 overflow-y-auto h-screen max-w-full overflow-x-hidden">
        {/* Mobile Header with Hamburger */}
        <div className="md:hidden flex items-center justify-between mb-6 pb-4 border-b border-zinc-800">
          <h2 className="text-2xl font-bold tracking-tight text-white">{activeTab}</h2>
          <div className="flex items-center gap-2">
            <button 
              onClick={handleLogout}
              className="text-xs font-semibold text-zinc-400 hover:text-white bg-zinc-900 px-3 py-1.5 rounded-lg border border-zinc-800"
            >
              Sair
            </button>
            <button 
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-2 bg-zinc-800 rounded-lg text-zinc-300 hover:text-white"
            >
              <Menu size={24} />
            </button>
          </div>
        </div>
        
        {/* Desktop Header */}
        <header className="hidden md:flex items-center justify-between mb-8 border-b border-zinc-800 pb-6">
          <h2 className="text-3xl font-bold tracking-tight text-white">{activeTab}</h2>
          <button 
            onClick={handleLogout}
            className="text-sm font-semibold text-zinc-400 hover:text-white bg-zinc-900 px-4 py-2 rounded-lg border border-zinc-800 transition-colors"
          >
            Encerrar Sessão
          </button>
        </header>

        {activeTab === 'Cotações' && <DashboardTab marketData={marketData} />}
        {activeTab === 'Configurações' && <ConfigTab config={config} sendConfigUpdate={sendConfigUpdate} />}
        {activeTab === 'Histórico' && <HistoryTab history={history} sendCommand={sendCommand} />}
        {activeTab === 'Analytics' && <AnalyticsTab chartData={chartData} targetSpread={config.target_spread} history={history} />}
        {activeTab === 'Oceano Azul' && <BlueOceanDesk triangularData={triangularData} isTriangularActive={config.is_triangular_active} sendCommand={sendCommand} />}
        {activeTab === 'Corretoras' && <ExchangesTab exchanges={config.exchanges} sendCommand={sendCommand} />}
        {activeTab === 'Autobot' && <AutobotTab isSpatialActive={config.is_spatial_active} sendCommand={sendCommand} />}
        {activeTab === 'Base Sniper' && <SniperDashboard />}
        {activeTab === 'Master Admin' && isAdmin && <AdminDashboard token={token} />}
        {activeTab === 'Minha Conta' && <AccountSettings token={token} />}

        {/* Fallback for other tabs */}
        {!['Cotações', 'Configurações', 'Histórico', 'Analytics', 'Autobot', 'Corretoras', 'Oceano Azul', 'Base Sniper', 'Master Admin', 'Minha Conta'].includes(activeTab) && (
          <div className="text-zinc-500 py-10">Módulo em desenvolvimento...</div>
        )}
      </main>
    </div>
  )
}

export default App
