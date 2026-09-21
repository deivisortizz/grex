import React, { useState, useEffect } from 'react';
import {
  Users,
  UserPlus,
  Crosshair,
  Radar,
  Copy,
  Check,
  ExternalLink,
  Trash2,
  Power,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  AlertCircle,
  Search,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
  Wifi,
  WifiOff,
  Terminal,
  Activity
} from 'lucide-react';
import { useSolanaWebSocket } from '../../hooks/useSolanaWebSocket';
import SolanaMetrics from './SolanaMetrics';
import SolanaPositionsTable from './SolanaPositionsTable';

export default function SolanaCopyTrading() {
  // Conexão dedicada com o motor de Copy Trading (copy_sniper.py, porta 8768) —
  // processo e WebSocket completamente separados do sniper global (:8767).
  const {
    status: engineStatus,
    metrics: copyMetrics,
    positions: copyPositions,
    history: copyHistory,
    logs: copyLogs,
    sendCommand: copySendCommand
  } = useSolanaWebSocket(8768);

  const handlePanicSell = (token) => {
    copySendCommand('force_sell', { token, is_panic: true });
  };

  const [wallets, setWallets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Form State para Adicionar Carteira
  const [newWalletAddress, setNewWalletAddress] = useState('');
  const [newWalletLabel, setNewWalletLabel] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  // Form State para Wallet Hunter
  const [huntMint, setHuntMint] = useState('');
  const [isHunting, setIsHunting] = useState(false);
  const [huntStatus, setHuntStatus] = useState(null);

  // Copied state mapping
  const [copiedAddress, setCopiedAddress] = useState(null);

  // Feedback Notification Toast
  const [toast, setToast] = useState(null);

  const showToast = (type, message) => {
    setToast({ type, message });
    setTimeout(() => {
      setToast((current) => (current?.message === message ? null : current));
    }, 4500);
  };

  const getAuthHeader = () => {
    const token = localStorage.getItem('token');
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    };
  };

  // Carregar Carteiras Rastreadas
  const fetchTrackedWallets = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/solana/tracked-wallets', {
        headers: getAuthHeader()
      });
      if (res.ok) {
        const data = await res.json();
        setWallets(data.wallets || []);
      } else {
        const err = await res.json().catch(() => ({}));
        showToast('error', err.detail || 'Erro ao carregar carteiras rastreadas.');
      }
    } catch (err) {
      console.error(err);
      showToast('error', 'Falha na conexão com o servidor.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrackedWallets();
  }, []);

  // Adicionar Nova Carteira
  const handleAddWallet = async (e) => {
    e.preventDefault();
    const address = newWalletAddress.trim();
    if (!address) {
      showToast('error', 'Informe o endereço público da carteira.');
      return;
    }

    try {
      setIsAdding(true);
      const res = await fetch('/api/solana/tracked-wallets', {
        method: 'POST',
        headers: getAuthHeader(),
        body: JSON.stringify({
          wallet_address: address,
          label: newWalletLabel.trim() || 'Smart Wallet'
        })
      });

      const data = await res.json();
      if (res.ok) {
        showToast('success', data.message || 'Carteira adicionada ao Copy Trading com sucesso!');
        setNewWalletAddress('');
        setNewWalletLabel('');
        fetchTrackedWallets();
      } else {
        showToast('error', data.detail || 'Erro ao adicionar carteira.');
      }
    } catch (err) {
      console.error(err);
      showToast('error', 'Erro ao comunicar com o servidor.');
    } finally {
      setIsAdding(false);
    }
  };

  // Alternar Status (Ativa / Inativa)
  const handleToggleWallet = async (walletId) => {
    try {
      const res = await fetch(`/api/solana/tracked-wallets/${walletId}/toggle`, {
        method: 'PUT',
        headers: getAuthHeader()
      });

      if (res.ok) {
        setWallets(prev =>
          prev.map(w => (w.id === walletId ? { ...w, is_active: !w.is_active } : w))
        );
        showToast('success', 'Status da carteira atualizado!');
      } else {
        const err = await res.json().catch(() => ({}));
        showToast('error', err.detail || 'Erro ao alternar status.');
      }
    } catch (err) {
      console.error(err);
      showToast('error', 'Falha ao alterar status da carteira.');
    }
  };

  // Excluir Carteira
  const handleDeleteWallet = async (walletId, address) => {
    const masked = `${address.slice(0, 6)}...${address.slice(-4)}`;
    if (!window.confirm(`Remover carteira ${masked} do rastreamento de cópia?`)) return;

    try {
      const res = await fetch(`/api/solana/tracked-wallets/${walletId}`, {
        method: 'DELETE',
        headers: getAuthHeader()
      });

      if (res.ok) {
        setWallets(prev => prev.filter(w => w.id !== walletId));
        showToast('success', 'Carteira removida com sucesso.');
      } else {
        const err = await res.json().catch(() => ({}));
        showToast('error', err.detail || 'Erro ao remover carteira.');
      }
    } catch (err) {
      console.error(err);
      showToast('error', 'Falha de conexão ao remover carteira.');
    }
  };

  // Acionar Wallet Hunter (Caçar Insiders do Bloco Zero)
  const handleHuntWallets = async (e) => {
    e.preventDefault();
    const mint = huntMint.trim();
    if (!mint) {
      showToast('error', 'Cole o Mint do token vencedor para caçar.');
      return;
    }

    try {
      setIsHunting(true);
      setHuntStatus({ phase: 'scanning', message: 'Iniciando Time Machine no RPC... buscando bloco zero...' });

      const res = await fetch('/api/solana/hunt-wallets', {
        method: 'POST',
        headers: getAuthHeader(),
        body: JSON.stringify({ mint })
      });

      const data = await res.json();
      if (res.ok) {
        const count = data.approved_count ?? 0;
        const total = data.total_buyers ?? 0;
        setHuntStatus({
          phase: 'completed',
          message: count > 0 
            ? `🎉 Sucesso! ${count} Smart Wallets de Elite encontradas (${total} analisadas) e adicionadas à lista!`
            : `ℹ️ ${total} compradores analisados no bloco zero, mas nenhum atendeu ao filtro de saldo/anti-burner.`
        });
        showToast('success', data.message || `${count} carteiras importadas com sucesso!`);
        fetchTrackedWallets();
      } else {
        setHuntStatus({
          phase: 'error',
          message: data.detail || 'Falha ao caçar compradores do bloco zero.'
        });
        showToast('error', data.detail || 'Erro ao executar Wallet Hunter.');
      }
    } catch (err) {
      console.error(err);
      setHuntStatus({
        phase: 'error',
        message: 'Erro na conexão com o RPC da Solana ou timeout.'
      });
      showToast('error', 'Falha de comunicação com o Wallet Hunter.');
    } finally {
      setIsHunting(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedAddress(text);
    setTimeout(() => setCopiedAddress(null), 2000);
  };

  const activeCount = wallets.filter(w => w.is_active).length;

  const filteredWallets = wallets.filter(w => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      w.wallet_address.toLowerCase().includes(q) ||
      (w.label && w.label.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex flex-col gap-6 w-full animate-fadeIn">
      
      {/* ── Toast de Feedback Flutuante ── */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border shadow-2xl transition-all duration-300 backdrop-blur-md ${
          toast.type === 'success' 
            ? 'bg-emerald-950/90 border-emerald-500/40 text-emerald-300 shadow-emerald-950/50'
            : toast.type === 'error'
            ? 'bg-rose-950/90 border-rose-500/40 text-rose-300 shadow-rose-950/50'
            : 'bg-zinc-900/90 border-zinc-700 text-zinc-300 shadow-black/50'
        }`}>
          {toast.type === 'success' ? (
            <CheckCircle2 size={20} className="text-emerald-400 shrink-0" />
          ) : (
            <XCircle size={20} className="text-rose-400 shrink-0" />
          )}
          <span className="text-sm font-medium">{toast.message}</span>
          <button 
            onClick={() => setToast(null)}
            className="text-xs text-zinc-400 hover:text-white ml-2 p-1"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Top Metric Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-zinc-900/90 border border-zinc-800/80 rounded-2xl p-4 flex items-center gap-3.5 shadow-sm">
          <div className="w-11 h-11 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400 shrink-0">
            <Users size={22} />
          </div>
          <div>
            <p className="text-xs text-zinc-400 font-medium">Total de Carteiras</p>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold font-mono text-white">{wallets.length}</span>
              <span className="text-[11px] text-zinc-500 font-mono">cadastradas</span>
            </div>
          </div>
        </div>

        <div className="bg-zinc-900/90 border border-zinc-800/80 rounded-2xl p-4 flex items-center gap-3.5 shadow-sm">
          <div className="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
            <Zap size={22} />
          </div>
          <div>
            <p className="text-xs text-zinc-400 font-medium">Carteiras Ativas (Cópia)</p>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold font-mono text-emerald-400">{activeCount}</span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-500 font-medium font-mono">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                monitorando
              </span>
            </div>
          </div>
        </div>

        <div className="bg-zinc-900/90 border border-zinc-800/80 rounded-2xl p-4 flex items-center gap-3.5 shadow-sm">
          <div className={`w-11 h-11 rounded-xl border flex items-center justify-center shrink-0 ${
            engineStatus === 'Online'
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
              : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
          }`}>
            {engineStatus === 'Online' ? <Wifi size={22} /> : <WifiOff size={22} />}
          </div>
          <div>
            <p className="text-xs text-zinc-400 font-medium">Smart Money Engine</p>
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold ${engineStatus === 'Online' ? 'text-emerald-300' : 'text-rose-400'}`}>
                Copy Sniper WSS
              </span>
              <span className="text-[10px] bg-cyan-500/20 text-cyan-300 font-mono px-1.5 py-0.5 rounded border border-cyan-500/30">
                :8768
              </span>
              <span className={`flex items-center gap-1 text-[11px] font-mono font-medium ${
                engineStatus === 'Online' ? 'text-emerald-500' : 'text-rose-500'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${engineStatus === 'Online' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
                {engineStatus === 'Online' ? 'online' : 'offline'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Métricas Reais do Copy Sniper (copy_sniper_history) ── */}
      <SolanaMetrics metrics={copyMetrics} />

      {/* ── Posições Abertas via Copy Trading ── */}
      <SolanaPositionsTable positions={copyPositions} onPanicSell={handlePanicSell} />

      {/* ── CARD: Wallet Hunter (Bloco Zero / Insiders) ── */}
      <div className="bg-gradient-to-br from-zinc-900 via-zinc-900 to-zinc-950 border border-cyan-500/20 rounded-2xl p-6 relative overflow-hidden shadow-[0_0_30px_rgba(6,182,212,0.05)]">
        <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Radar size={18} className={isHunting ? 'animate-spin' : ''} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Wallet Hunter
                <span className="text-[10px] font-mono font-semibold uppercase px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-300">
                  Bloco Zero / Insiders
                </span>
              </h3>
              <p className="text-xs text-zinc-400 mt-0.5">
                Varredura temporal profunda (Time Machine) na Helius RPC: identifica os primeiros compradores da história do token e filtra Smart Wallets de elite.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setHuntMint('POOP4Z58tU76F4vP8Kj5Y3bU8G6W2m1vP9Z7xX4pump')}
            className="text-[11px] text-zinc-400 hover:text-cyan-300 bg-zinc-800/80 hover:bg-zinc-800 border border-zinc-700/60 px-2.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 self-start sm:self-auto cursor-pointer font-mono"
            title="Preencher com exemplo de token"
          >
            <Sparkles size={12} className="text-cyan-400" />
            Exemplo POOP
          </button>
        </div>

        <form onSubmit={handleHuntWallets} className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <input
              type="text"
              value={huntMint}
              onChange={(e) => setHuntMint(e.target.value)}
              disabled={isHunting}
              placeholder="Cole o endereço do contrato (Mint) do token vencedor da Pump.fun..."
              className="w-full bg-black/80 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/40 disabled:opacity-50 font-mono transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={isHunting || !huntMint.trim()}
            className="px-6 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2.5 transition-all shadow-lg cursor-pointer bg-gradient-to-r from-cyan-600 to-cyan-500 hover:from-cyan-500 hover:to-cyan-400 text-zinc-950 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 shrink-0"
          >
            {isHunting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Varrendo Bloco Zero...
              </>
            ) : (
              <>
                <Crosshair size={16} />
                Caçar Insiders (Wallet Hunter)
              </>
            )}
          </button>
        </form>

        {/* Status de Varredura / Progresso */}
        {huntStatus && (
          <div className={`mt-4 p-3.5 rounded-xl border text-xs font-mono flex items-start gap-2.5 transition-all ${
            huntStatus.phase === 'completed'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : huntStatus.phase === 'error'
              ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
              : 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300 animate-pulse'
          }`}>
            {huntStatus.phase === 'completed' && <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />}
            {huntStatus.phase === 'error' && <AlertCircle size={16} className="text-rose-400 shrink-0 mt-0.5" />}
            {huntStatus.phase === 'scanning' && <Loader2 size={16} className="text-cyan-400 animate-spin shrink-0 mt-0.5" />}
            <div className="flex-1">
              <p>{huntStatus.message}</p>
            </div>
            <button 
              type="button" 
              onClick={() => setHuntStatus(null)}
              className="text-zinc-500 hover:text-zinc-300 text-[10px]"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* ── CARD: Copy Trading - Carteiras Rastreadas ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden flex flex-col shadow-lg">
        
        {/* Header da Seção */}
        <div className="px-6 py-5 border-b border-zinc-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-black/40">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-violet-500/10 border border-violet-500/25 flex items-center justify-center text-violet-400 shrink-0">
              <Users size={20} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Copy Trading - Carteiras Rastreadas
                <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 border border-zinc-700">
                  {wallets.length}
                </span>
              </h3>
              <p className="text-xs text-zinc-400">
                O bot <code className="text-violet-300">copy_sniper.py</code> copia ordens de compra destas carteiras em tempo real com seu position sizing.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={fetchTrackedWallets}
              disabled={loading}
              className="p-2 rounded-xl bg-zinc-800/80 hover:bg-zinc-800 border border-zinc-700/60 text-zinc-300 hover:text-white transition-colors cursor-pointer"
              title="Atualizar lista"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* Formulário de Adição Rápida */}
        <div className="p-6 border-b border-zinc-800/80 bg-zinc-900/40">
          <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <UserPlus size={14} className="text-violet-400" />
            Cadastrar Nova Carteira Alvo (Smart Wallet)
          </p>

          <form onSubmit={handleAddWallet} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
            <div className="md:col-span-6">
              <input
                type="text"
                value={newWalletAddress}
                onChange={(e) => setNewWalletAddress(e.target.value)}
                placeholder="Endereço da Carteira Solana (Base58)..."
                disabled={isAdding}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-violet-500/60 focus:ring-1 focus:ring-violet-500/40 font-mono transition-all"
              />
            </div>

            <div className="md:col-span-4">
              <input
                type="text"
                value={newWalletLabel}
                onChange={(e) => setNewWalletLabel(e.target.value)}
                placeholder="Rótulo / Label (ex: Whale Alpha, Insider POOP)..."
                disabled={isAdding}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-violet-500/60 focus:ring-1 focus:ring-violet-500/40 transition-all"
              />
            </div>

            <div className="md:col-span-2">
              <button
                type="submit"
                disabled={isAdding || !newWalletAddress.trim()}
                className="w-full bg-violet-600 hover:bg-violet-500 text-white font-bold py-2.5 px-4 rounded-xl text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-violet-600/20 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer active:scale-95"
              >
                {isAdding ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <UserPlus size={16} />
                )}
                Adicionar
              </button>
            </div>
          </form>
        </div>

        {/* Barra de Busca / Filtro */}
        {wallets.length > 3 && (
          <div className="px-6 py-3 border-b border-zinc-800/60 bg-zinc-950/40 flex items-center gap-2">
            <Search size={15} className="text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filtrar por endereço ou rótulo..."
              className="bg-transparent border-none text-xs text-zinc-300 placeholder-zinc-500 focus:outline-none w-full font-mono"
            />
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery('')}
                className="text-xs text-zinc-500 hover:text-zinc-300 px-1"
              >
                Limpar
              </button>
            )}
          </div>
        )}

        {/* Tabela Interativa de Carteiras */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-zinc-900/80 text-[10px] uppercase tracking-wider text-zinc-400 font-semibold border-b border-zinc-800">
                <th className="py-3 px-6 font-medium">Carteira Solana</th>
                <th className="py-3 px-4 font-medium">Rótulo / Tag</th>
                <th className="py-3 px-4 font-medium text-center">Status</th>
                <th className="py-3 px-6 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {loading ? (
                <tr>
                  <td colSpan="4" className="py-12 text-center text-xs text-zinc-500">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Loader2 size={24} className="animate-spin text-violet-400" />
                      <span>Carregando carteiras rastreadas...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredWallets.length === 0 ? (
                <tr>
                  <td colSpan="4" className="py-12 text-center text-xs text-zinc-500">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <div className="w-12 h-12 rounded-full bg-zinc-800/50 flex items-center justify-center text-zinc-600">
                        <Users size={24} />
                      </div>
                      <p className="text-zinc-400 font-medium">
                        {searchQuery ? 'Nenhuma carteira corresponde à busca.' : 'Nenhuma carteira cadastrada ainda.'}
                      </p>
                      {!searchQuery && (
                        <p className="text-[11px] text-zinc-600 max-w-sm">
                          Adicione um endereço manualmente acima ou use o <strong>Wallet Hunter</strong> para varrer compradores do bloco zero.
                        </p>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                filteredWallets.map((wallet) => {
                  const isActive = Boolean(wallet.is_active);
                  const isCopied = copiedAddress === wallet.wallet_address;

                  return (
                    <tr 
                      key={wallet.id} 
                      className={`hover:bg-zinc-800/30 transition-colors group ${
                        !isActive ? 'opacity-60 bg-zinc-950/20' : ''
                      }`}
                    >
                      {/* Endereço */}
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2.5">
                          <div className={`w-2 h-2 rounded-full shrink-0 ${
                            isActive ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]' : 'bg-zinc-600'
                          }`} />
                          
                          <div className="flex items-center gap-1.5 font-mono text-xs">
                            <span className="text-zinc-200 group-hover:text-white font-medium" title={wallet.wallet_address}>
                              {wallet.wallet_address.slice(0, 6)}...{wallet.wallet_address.slice(-6)}
                            </span>
                            
                            {/* Botão Copiar */}
                            <button
                              onClick={() => copyToClipboard(wallet.wallet_address)}
                              className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
                              title="Copiar endereço completo"
                            >
                              {isCopied ? (
                                <Check size={13} className="text-emerald-400" />
                              ) : (
                                <Copy size={13} />
                              )}
                            </button>

                            {/* Link Solscan */}
                            <a
                              href={`https://solscan.io/account/${wallet.wallet_address}`}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-cyan-400 transition-colors"
                              title="Ver na Solscan"
                            >
                              <ExternalLink size={13} />
                            </a>
                          </div>
                        </div>
                      </td>

                      {/* Rótulo / Tag */}
                      <td className="py-4 px-4">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium ${
                          wallet.label?.toLowerCase().includes('insider')
                            ? 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 font-mono'
                            : 'bg-zinc-800 text-zinc-300 border border-zinc-700/60'
                        }`}>
                          {wallet.label?.toLowerCase().includes('insider') && (
                            <Sparkles size={11} className="text-cyan-400" />
                          )}
                          {wallet.label || 'Sem rótulo'}
                        </span>
                      </td>

                      {/* Status (Ativa / Inativa) */}
                      <td className="py-4 px-4 text-center">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border ${
                          isActive
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                            : 'bg-zinc-800/80 border-zinc-700 text-zinc-500'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
                          {isActive ? 'Ativa' : 'Inativa'}
                        </span>
                      </td>

                      {/* Ações (Alternar e Excluir) */}
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-2">
                          
                          {/* Toggle Switch / Button */}
                          <button
                            onClick={() => handleToggleWallet(wallet.id)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold font-mono flex items-center gap-1.5 transition-all cursor-pointer border ${
                              isActive
                                ? 'bg-zinc-800/90 hover:bg-zinc-800 text-zinc-300 border-zinc-700 hover:border-zinc-600'
                                : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border-emerald-500/30'
                            }`}
                            title={isActive ? 'Pausar rastreamento' : 'Ativar rastreamento'}
                          >
                            <Power size={12} className={isActive ? 'text-zinc-400' : 'text-emerald-400'} />
                            {isActive ? 'Pausar' : 'Ativar'}
                          </button>

                          {/* Delete Button */}
                          <button
                            onClick={() => handleDeleteWallet(wallet.id, wallet.wallet_address)}
                            className="p-1.5 rounded-lg bg-zinc-800/60 hover:bg-rose-500/10 border border-zinc-700/60 hover:border-rose-500/30 text-zinc-400 hover:text-rose-400 transition-all cursor-pointer"
                            title="Remover carteira do banco de dados"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer com Dicas / Informações de Execução */}
        <div className="px-6 py-3 border-t border-zinc-800/80 bg-zinc-950/60 flex flex-col sm:flex-row items-center justify-between text-[11px] text-zinc-500 gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck size={14} className="text-emerald-500 shrink-0" />
            <span>
              O <strong className="text-zinc-400">copy_sniper.py</strong> replica as compras instantaneamente usando Jito Tips e slippage da sua configuração.
            </span>
          </div>
          <span className="font-mono text-[10px] text-zinc-600">
            Helius RPC WebSocket Filter: v1.0
          </span>
        </div>

      </div>

      {/* ── CARD: Histórico de Trades do Copy Sniper ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-lg">
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center gap-3 bg-black/40">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400 shrink-0">
            <Activity size={18} />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">Histórico de Trades (Copy Trading)</h3>
            <p className="text-xs text-zinc-400">
              Registrado separadamente do Sniper global, na tabela <code className="text-emerald-300">copy_sniper_history</code>.
            </p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-zinc-900/80 text-[10px] uppercase tracking-wider text-zinc-400 font-semibold border-b border-zinc-800">
                <th className="py-3 px-6 font-medium">Data/Hora</th>
                <th className="py-3 px-4 font-medium">Token</th>
                <th className="py-3 px-4 font-medium">Investido (SOL)</th>
                <th className="py-3 px-4 font-medium">Retorno (SOL)</th>
                <th className="py-3 px-6 font-medium text-right">Resultado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {(!copyHistory || copyHistory.length === 0) ? (
                <tr>
                  <td colSpan="5" className="py-10 text-center text-xs text-zinc-500">
                    Nenhum trade de copy trading registrado ainda.
                  </td>
                </tr>
              ) : (
                copyHistory.map((trade, idx) => {
                  const netPnl = trade.net_pnl_sol || 0;
                  return (
                    <tr key={idx} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="py-3 px-6 text-xs text-zinc-400 font-mono">
                        {trade.created_at ? new Date(trade.created_at + 'Z').toLocaleString() : 'N/A'}
                      </td>
                      <td className="py-3 px-4 font-mono text-xs text-emerald-400">
                        {trade.token_mint ? `${trade.token_mint.slice(0, 6)}...${trade.token_mint.slice(-4)}` : '—'}
                      </td>
                      <td className="py-3 px-4 text-zinc-300 font-mono text-xs">
                        {(trade.sol_spent || 0).toFixed(4)}
                      </td>
                      <td className="py-3 px-4 text-zinc-300 font-mono text-xs">
                        {(trade.sol_received || 0).toFixed(4)}
                      </td>
                      <td className="py-3 px-6 text-right">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-bold text-xs ${
                          trade.is_win
                            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                            : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
                        }`}>
                          {netPnl > 0 ? '+' : ''}{netPnl.toFixed(4)} SOL
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Terminal de Logs ao Vivo do Copy Sniper ── */}
      <div className="bg-black border border-zinc-800 rounded-2xl p-5 font-mono text-sm h-64 overflow-y-auto">
        <div className="text-zinc-500 mb-2 flex items-center gap-2">
          <Terminal size={14} />
          // Logs do Copy Sniper (:8768)
        </div>
        {copyLogs.map((log, i) => (
          <div key={i} className="text-zinc-300 mb-1">{log}</div>
        ))}
        {copyLogs.length === 0 && <div className="text-zinc-700">Nenhum log capturado ainda...</div>}
      </div>

    </div>
  );
}
