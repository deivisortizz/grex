import { useState, useEffect, useRef, useCallback } from 'react'

export function useSniperWebSocket() {
  const [isConnected, setIsConnected] = useState(false)
  const [walletStatus, setWalletStatus] = useState(null)
  const [isActive, setIsActive] = useState(true)
  const [pools, setPools] = useState([])
  const [logs, setLogs] = useState([])
  const [openPositions, setOpenPositions] = useState([])
  const [metrics, setMetrics] = useState({ total_trades: 0, win_trades: 0, daily_pnl_usd: 0 })
  const [config, setConfig] = useState({ snipe_size_eth: 0.0005, min_pool_weth: 0.05, tp_pct: 100, sl_pct: 20 })
  const wsRef = useRef(null)

  const connect = useCallback(() => {
    const wsUrl = import.meta.env.VITE_SNIPER_WS_URL || 'ws://localhost:8766'
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        switch (data.type) {
          case 'wallet_status':
            setWalletStatus(data.wallet_address)
            if (typeof data.is_active === 'boolean') {
              setIsActive(data.is_active)
            }
            break

          case 'sniper_status':
            if (typeof data.is_active === 'boolean') {
              setIsActive(data.is_active)
            }
            break
            
          case 'new_pool':
            setPools(prev => [{
              token: data.token,
              pairedWith: data.paired_with,
              timestamp: data.timestamp,
              skipped: Boolean(data.skipped),
              id: `${data.token}-${data.timestamp}`
            }, ...prev].slice(0, 50)) // Keep last 50
            break
            
          case 'log':
            setLogs(prev => [...prev, {
              level: data.level,
              message: data.message,
              timestamp: data.timestamp,
              id: `${Date.now()}-${Math.random()}`
            }].slice(-100)) // Keep last 100 logs
            break
            
          case 'open_positions':
            if (Array.isArray(data.positions)) {
              setOpenPositions(data.positions)
            }
            break

          case 'metrics_updated':
            if (data.metrics) {
              setMetrics(data.metrics)
            }
            break
            
          case 'config_updated':
            if (data.config) {
              setConfig(data.config)
            }
            break
            
          default:
            break
        }
      } catch (err) {
        console.error('Erro no parser do WS Sniper:', err)
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      // Tenta reconectar após 3s
      setTimeout(connect, 3000)
    }

    ws.onerror = (err) => {
      console.error('WebSocket Error:', err)
      ws.close()
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        // Prevenir reconexão no unmount
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendCommand = useCallback((payload) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload))
    }
  }, [])

  const toggleSniper = useCallback((targetState) => {
    const nextState = typeof targetState === 'boolean' ? targetState : !isActive
    setIsActive(nextState)
    sendCommand({
      type: 'toggle_sniper',
      is_active: nextState
    })
  }, [isActive, sendCommand])

  const updateConfig = useCallback((newConfig) => {
    sendCommand({
      type: 'update_config',
      config: newConfig
    })
  }, [sendCommand])

  const forceSell = useCallback((token) => {
    sendCommand({
      type: 'force_sell',
      token: token
    })
  }, [sendCommand])

  return {
    isConnected,
    walletStatus,
    isActive,
    toggleSniper,
    pools,
    logs,
    sendCommand,
    openPositions,
    metrics,
    config,
    updateConfig,
    forceSell
  }
}
