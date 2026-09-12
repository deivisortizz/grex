import { useState, useEffect, useRef } from 'react'
import Sidebar from './components/Sidebar'
import DashboardTab from './components/DashboardTab'
import ConfigTab from './components/ConfigTab'
import HistoryTab from './components/HistoryTab'
import AnalyticsTab from './components/AnalyticsTab'
import AutobotTab from './components/AutobotTab'
import ExchangesTab from './components/ExchangesTab'
import TriangularTab from './components/TriangularTab'
import BlueOceanDesk from './components/BlueOceanDesk'
import Login from './components/Login'
import SniperDashboard from './components/sniper/SniperDashboard'

function App() {
  // Estado de autenticação persistido
  const [isAuthenticated, setIsAuthenticated] = useState(
    localStorage.getItem('arb_auth') === 'true'
  )

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
    // Detecta se está local, ou usa WSS em produção dinamicamente
    const currentHost = window.location.hostname
    const defaultWsUrl = currentHost === 'localhost' || currentHost === '127.0.0.1' 
      ? 'ws://localhost:8765' 
      : `wss://${currentHost}/ws` // ou wss://api.seudominio.com dependendo do Easypanel

    const wsUrl = import.meta.env.VITE_WS_URL || defaultWsUrl
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    let pingInterval;

    ws.onopen = () => {
      setWsStatus('Online')
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

  const handleLogin = () => {
    localStorage.setItem('arb_auth', 'true')
    setIsAuthenticated(true)
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex font-sans text-zinc-100">
      <Sidebar wsStatus={wsStatus} ping={ping} activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Area */}
      <main className="flex-1 ml-64 p-8 overflow-y-auto h-screen">
        <header className="mb-8 border-b border-zinc-800 pb-6">
          <h2 className="text-3xl font-bold tracking-tight text-white">{activeTab}</h2>
        </header>

        {activeTab === 'Cotações' && <DashboardTab marketData={marketData} />}
        {activeTab === 'Configurações' && <ConfigTab config={config} sendConfigUpdate={sendConfigUpdate} />}
        {activeTab === 'Histórico' && <HistoryTab history={history} sendCommand={sendCommand} />}
        {activeTab === 'Analytics' && <AnalyticsTab chartData={chartData} targetSpread={config.target_spread} history={history} />}
        {activeTab === 'Oceano Azul' && <BlueOceanDesk triangularData={triangularData} isTriangularActive={config.is_triangular_active} sendCommand={sendCommand} />}
        {activeTab === 'Corretoras' && <ExchangesTab exchanges={config.exchanges} sendCommand={sendCommand} />}
        {activeTab === 'Autobot' && <AutobotTab isSpatialActive={config.is_spatial_active} sendCommand={sendCommand} />}
        {activeTab === 'Base Sniper' && <SniperDashboard />}

        {/* Fallback for other tabs */}
        {!['Cotações', 'Configurações', 'Histórico', 'Analytics', 'Autobot', 'Corretoras', 'Oceano Azul', 'Base Sniper'].includes(activeTab) && (
          <div className="text-zinc-500 py-10">Módulo em desenvolvimento...</div>
        )}
      </main>
    </div>
  )
}

export default App
