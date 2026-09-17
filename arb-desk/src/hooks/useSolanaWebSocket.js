import { useState, useEffect, useCallback, useRef } from 'react';

export function useSolanaWebSocket() {
  const [status, setStatus] = useState('Disconnected');
  const [config, setConfig] = useState({});
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState({ total_trades: 0, wins: 0, losses: 0, daily_pnl_usd: 0, daily_pnl_sol: 0, win_rate: 0 });
  const [positions, setPositions] = useState([]);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn("Nenhum token encontrado. WS não será conectado.");
      setStatus('Disconnected');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const wsUrl = `${protocol}//${host}:8767`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('Online');
      ws.send(JSON.stringify({ type: 'auth', token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'config') {
          setConfig(data);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.log].slice(-100)); // Keep last 100 logs
        } else if (data.type === 'STATS_UPDATE') {
          setMetrics(data.data);
        } else if (data.type === 'open_positions') {
          setPositions(data.positions);
        }
      } catch (e) {
        console.error("Erro no WS Solana:", e);
      }
    };

    ws.onclose = (event) => {
      setStatus('Disconnected');
      if (event.code !== 4001) {
        setTimeout(connect, 3000);
      } else {
        console.warn("Conexão recusada por falha de autenticação (4001). Parando tentativas.");
      }
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
