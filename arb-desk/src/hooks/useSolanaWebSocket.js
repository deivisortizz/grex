import { useState, useEffect, useCallback, useRef } from 'react';

export function useSolanaWebSocket() {
  const [status, setStatus] = useState('Disconnected');
  const [config, setConfig] = useState({});
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState({ total_trades: 0, win_trades: 0, daily_pnl_usd: 0 });
  const [positions, setPositions] = useState([]);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const wsUrl = `${protocol}//${host}:8767`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('Online');
      const token = localStorage.getItem('token');
      if (token) {
        ws.send(JSON.stringify({ type: 'auth', token }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'config') {
          setConfig(data);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.log].slice(-100)); // Keep last 100 logs
        } else if (data.type === 'metrics_updated') {
          setMetrics(data.metrics);
        } else if (data.type === 'open_positions') {
          setPositions(data.positions);
        }
      } catch (e) {
        console.error("Erro no WS Solana:", e);
      }
    };

    ws.onclose = () => {
      setStatus('Disconnected');
      setTimeout(connect, 3000);
    };

    ws.onerror = () => setStatus('Error');
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendCommand = (type, payload = {}) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...payload }));
    } else {
      console.warn("Solana WS não está conectado");
    }
  };

  return { status, config, logs, metrics, positions, sendCommand };
}
