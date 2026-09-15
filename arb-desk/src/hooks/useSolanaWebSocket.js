import { useState, useEffect, useCallback, useRef } from 'react';

export function useSolanaWebSocket() {
  const [status, setStatus] = useState('Disconnected');
  const [config, setConfig] = useState({});
  const [logs, setLogs] = useState([]);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const dynamicWsUrl = `${wsProtocol}//${window.location.hostname}:8767`;
    const wsUrl = import.meta.env.VITE_SOLANA_WS_URL || dynamicWsUrl;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setStatus('Online');
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'config') {
          setConfig(data);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.log].slice(-100)); // Keep last 100 logs
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

  return { status, config, logs, sendCommand };
}
