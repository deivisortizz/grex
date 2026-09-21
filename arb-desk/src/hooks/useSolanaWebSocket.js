import { useState, useEffect, useCallback, useRef } from 'react';

// Funções de Sintetização de Áudio (Web Audio API)
const playBeep = (freq, type, duration, vol) => {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const audioCtx = new AudioContext();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(freq, audioCtx.currentTime);
    
    gainNode.gain.setValueAtTime(vol, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + duration);
    
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    
    oscillator.start();
    oscillator.stop(audioCtx.currentTime + duration);
  } catch (e) {
    console.error("Web Audio API bloqueada ou com erro:", e);
  }
};

const playRadarSound = () => {
  // Som de radar furtivo: duplo bip agudo e rápido
  playBeep(880, 'sine', 0.1, 0.05);
  setTimeout(() => playBeep(1760, 'sine', 0.2, 0.05), 100);
};

const playSuccessSound = () => {
  // Som de moeda de videogame / confirmação de lucro
  playBeep(987.77, 'sine', 0.1, 0.1); // B5
  setTimeout(() => playBeep(1318.51, 'sine', 0.4, 0.15), 100); // E6
};

const playFishAlertSound = () => {
  // Som náutico / sonar indicando baleia/peixe grande
  playBeep(440, 'triangle', 0.15, 0.1);
  setTimeout(() => playBeep(660, 'sine', 0.3, 0.15), 150);
  setTimeout(() => playBeep(880, 'sine', 0.5, 0.1), 400);
};

// [FIX] Parametrizado por porta para poder reutilizar o mesmo hook (mesmo
// protocolo de mensagens, herdado de SolanaCore.ws_handler) tanto para o
// sniper global (solana_sniper.py, :8767) quanto para o motor de Copy
// Trading (copy_sniper.py, :8768) — são dois processos/conexões independentes.
export function useSolanaWebSocket(port = 8767) {
  const [status, setStatus] = useState('Disconnected');
  const [config, setConfig] = useState({});
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState({ total_trades: 0, wins: 0, losses: 0, daily_pnl_usd: 0, daily_pnl_sol: 0, win_rate: 0 });
  const [positions, setPositions] = useState([]);
  const [pools, setPools] = useState([]);
  const [history, setHistory] = useState([]);
  const [priceHistory, setPriceHistory] = useState({});
  const [smartAlert, setSmartAlert] = useState(null);
  const wsRef = useRef(null);
  const prevStatusRef = useRef('idle'); // Rastrear mudanças de estado

  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn("Nenhum token encontrado. WS não será conectado.");
      setStatus('Disconnected');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;

    // Conexão dinâmica: Prioriza a variável de ambiente específica da porta,
    // depois cai para host:porta diretamente.
    const envKey = port === 8768 ? 'VITE_COPY_SNIPER_WS_URL' : 'VITE_SOLANA_WS_URL';
    let wsUrl = import.meta.env[envKey];

    if (!wsUrl) {
      wsUrl = `${protocol}//${host}:${port}`;
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
        if (data.type === 'config') {
          // Detectar transição para "sniping" ou "monitoring_position" (Radar detectou alvo!)
          if (prevStatusRef.current !== data.status && (data.status === 'sniping' || data.status === 'monitoring_position')) {
            playRadarSound();
          }
          prevStatusRef.current = data.status || 'idle';
          setConfig(data);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.log].slice(-100)); // Keep last 100 logs
        } else if (data.type === 'STATS_UPDATE') {
          setMetrics(data.data);
        } else if (data.type === 'open_positions') {
          setPositions(data.positions);
          setPriceHistory(prev => {
            const next = { ...prev };
            Object.values(data.positions || {}).forEach(pos => {
              if (pos.current_price) {
                if (!next[pos.token]) next[pos.token] = [];
                next[pos.token] = [...next[pos.token], pos.current_price].slice(-40); // Keep last 40 ticks
              }
            });
            return next;
          });
        } else if (data.type === 'new_pool') {
          const vol = data.volume || data.v_sol || 0;
          const mcap = data.usd_market_cap || data.market_cap || data.mcap || 0;
          
          if (vol >= 3.0 || mcap >= 15000) {
            playFishAlertSound();
            setSmartAlert({
              token: data.token,
              symbol: data.symbol || '???',
              reason: vol >= 3.0 ? `Volume Forte (${vol.toFixed(2)} SOL)` : `MCap Alto ($${(mcap/1000).toFixed(1)}k)`,
              timestamp: Date.now()
            });
          }

          setPools(prev => {
            const newPool = { 
              id: data.token + '-' + Date.now(), 
              token: data.token, 
              timestamp: data.timestamp,
              name: data.name,
              symbol: data.symbol,
              image_uri: data.image_uri,
              usd_market_cap: data.usd_market_cap,
              volume: data.volume,
              reply_count: data.reply_count
            };
            return [newPool, ...prev].slice(0, 50); // Keep last 50
          });
        } else if (data.type === 'HISTORY_UPDATE') {
          setHistory(data.history);
        } else if (data.type === 'trade_win') {
          playSuccessSound();
          window.dispatchEvent(new CustomEvent('trade_win', { detail: data }));
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
  }, [port]);

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

  return { status, config, logs, metrics, positions, pools, history, priceHistory, smartAlert, setSmartAlert, sendCommand };
}
