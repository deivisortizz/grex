import { useState, useEffect, useCallback, useRef } from 'react';

// Conexão dedicada com o CEX Listing Sniper (listing_sniper_service.py, :8769).
// Protocolo próprio (não reaproveita useSolanaWebSocket): o servidor manda
// {type:"state", exchanges, trades, avg_detection_latency_ms} logo após o
// handshake JWT, depois eventos ao vivo (announcement_detected/trade_opened/
// trade_closed/trade_failed/exit_failed/monitor_crashed) e responde comandos
// save_and_arm/disarm/get_history.
const WS_PORT = 8769;

export function useListingSniperWebSocket() {
  const [status, setStatus] = useState('Disconnected');
  const [exchanges, setExchanges] = useState([]);
  const [trades, setTrades] = useState([]);
  const [avgLatencyMs, setAvgLatencyMs] = useState(null);
  const [feed, setFeed] = useState([]);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn('Nenhum token encontrado. WS do Listing Sniper não será conectado.');
      setStatus('Disconnected');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    let wsUrl = import.meta.env.VITE_LISTING_SNIPER_WS_URL;
    if (!wsUrl) {
      wsUrl = `${protocol}//${host}:${WS_PORT}`;
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('Online');
      ws.send(JSON.stringify({ type: 'auth', token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'state') {
          setExchanges(data.exchanges || []);
          if (data.trades) setTrades(data.trades);
          if (data.avg_detection_latency_ms !== undefined) setAvgLatencyMs(data.avg_detection_latency_ms);
        } else if (data.type === 'history') {
          setTrades(data.data || []);
        } else if (data.type === 'announcement_detected') {
          setFeed(prev => [{ kind: 'announcement', ts: Date.now(), ...data.data }, ...prev].slice(0, 200));
        } else if (data.type === 'trade_opened') {
          setFeed(prev => [{ kind: 'trade_opened', ts: Date.now(), ...data.data }, ...prev].slice(0, 200));
        } else if (data.type === 'trade_closed') {
          setFeed(prev => [{ kind: 'trade_closed', ts: Date.now(), ...data.data }, ...prev].slice(0, 200));
        } else if (data.type === 'trade_failed' || data.type === 'exit_failed' || data.type === 'monitor_crashed') {
          setFeed(prev => [{ kind: data.type, ts: Date.now(), ...data.data }, ...prev].slice(0, 200));
        }
      } catch (e) {
        console.error('Erro no WS Listing Sniper:', e);
      }
    };

    ws.onclose = (event) => {
      setStatus('Disconnected');
      if (event.code !== 4001) {
        setTimeout(connect, 3000);
      } else {
        console.warn('Conexão do Listing Sniper recusada por falha de autenticação (4001).');
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

  const sendCommand = (command, extra = {}) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'command', command, ...extra }));
    } else {
      console.warn('Listing Sniper WS não está conectado');
    }
  };

  const armExchange = (exchange, credentials, config) => {
    sendCommand('save_and_arm', { exchange, credentials, config });
  };

  const disarmExchange = (exchange) => {
    sendCommand('disarm', { exchange });
  };

  const refreshHistory = () => {
    sendCommand('get_history');
  };

  return { status, exchanges, trades, avgLatencyMs, feed, armExchange, disarmExchange, refreshHistory };
}
