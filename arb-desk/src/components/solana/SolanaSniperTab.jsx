import React, { useState } from 'react';
import { useSolanaWebSocket } from '../../hooks/useSolanaWebSocket';
import { Wifi, Power, Play, Pause, Save, Crosshair, Wallet } from 'lucide-react';

export default function SolanaSniperTab() {
  const { status, config, logs, sendCommand } = useSolanaWebSocket();
  const isConnected = status === 'Online';
  const isActive = config.status === 'watching' || config.status === 'sniping';

  const [formData, setFormData] = useState({
    target_token: '',
    slippage: 15,
    jito_tip: 0.001
  });

  const [walletKey, setWalletKey] = useState('');
  const [walletAddress, setWalletAddress] = useState(null);

  const toggleSniper = (activate) => {
    if (activate) {
      sendCommand('start', formData);
    } else {
      sendCommand('stop');
    }
  };

  const handleSaveWallet = async () => {
    if (!walletKey) return;
    try {
      const token = localStorage.getItem('token');
      // No backend, enviamos a chave privada, e ele tenta extrair o address. 
      // Mas a rota espera address e private_key. Para Solana, a chave privada em Base58 pode ser usada pra derivar a pubkey.
      // Neste MVP simples, enviaremos a chave. O backend deverá lidar, ou o usuário insere a pubkey tbm.
      // O endpoint original da base espera req.address e req.private_key.
      alert("A funcionalidade de salvar carteira será totalmente integrada na próxima fase do backend. A API requer o endereço da carteira gerado a partir da chave.");
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Master Control Banner */}
      <div className={`border rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all duration-300 ${
        isActive
          ? 'bg-zinc-900/90 border-emerald-500/30 shadow-[0_0_25px_rgba(16,185,129,0.08)]'
          : 'bg-zinc-900/90 border-violet-500/30 shadow-[0_0_25px_rgba(139,92,246,0.08)]'
      }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center border transition-all shrink-0 ${
            isActive
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-violet-500/10 border-violet-500/30 text-violet-400'
          }`}>
            <Power size={24} className={isActive ? 'animate-pulse' : ''} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-lg font-bold text-white tracking-tight">Solana Sniper Engine</h2>
              <span className={`px-2.5 py-0.5 text-xs font-bold font-mono rounded-full border flex items-center gap-1.5 ${
                isActive
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                  : 'bg-violet-500/15 border-violet-500/40 text-violet-400'
              }`}>
                <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400 animate-ping' : 'bg-violet-500'}`} />
                {isActive ? 'EXECUÇÃO ATIVA' : 'SNIPER PAUSADO'}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {isActive
                ? 'Monitorando criação de liquidez na Solana em tempo real (Pump.fun / Raydium).'
                : 'Pausado: Insira o token alvo e ative o sniper.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
          <button
            onClick={() => toggleSniper(!isActive)}
            disabled={!isConnected}
            className={`w-full sm:w-auto px-6 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2.5 transition-all shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
              isActive
                ? 'bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/50 hover:border-rose-400 shadow-rose-500/10 active:scale-95'
                : 'bg-violet-600 hover:bg-violet-500 text-white shadow-violet-500/20 active:scale-95'
            }`}
          >
            {isActive ? (
              <>
                <Pause size={18} className="fill-current" />
                <span>Pausar Sniper</span>
              </>
            ) : (
              <>
                <Play size={18} className="fill-current" />
                <span>Ativar Sniper</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Configurações */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
          <h3 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
            <Crosshair size={20} className="text-violet-500" />
            Configuração de Alvo (Solana)
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-bold text-zinc-400 mb-1.5">Endereço do Token (Mint)</label>
              <input
                type="text"
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-violet-500 transition-colors font-mono text-sm"
                placeholder="Ex: 7jnC... pump"
                value={formData.target_token}
                onChange={(e) => setFormData({ ...formData, target_token: e.target.value })}
                disabled={isActive}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold text-zinc-400 mb-1.5">Slippage (%)</label>
                <input
                  type="number"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-violet-500 transition-colors"
                  value={formData.slippage}
                  onChange={(e) => setFormData({ ...formData, slippage: Number(e.target.value) })}
                  disabled={isActive}
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-zinc-400 mb-1.5">Jito Tip (SOL)</label>
                <input
                  type="number"
                  step="0.0001"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-violet-500 transition-colors"
                  value={formData.jito_tip}
                  onChange={(e) => setFormData({ ...formData, jito_tip: e.target.value })}
                  disabled={isActive}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Burner Wallet */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
          <h3 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
            <Wallet size={20} className="text-violet-500" />
            Solana Burner Wallet
          </h3>
          <div className="space-y-4">
            {walletAddress ? (
              <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-400">
                Carteira ativa: {walletAddress}
              </div>
            ) : (
              <div>
                <label className="block text-sm font-bold text-zinc-400 mb-1.5">Private Key (Base58)</label>
                <input
                  type="password"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-violet-500 transition-colors font-mono text-sm"
                  placeholder="Insira sua chave privada Base58"
                  value={walletKey}
                  onChange={(e) => setWalletKey(e.target.value)}
                />
                <button
                  onClick={handleSaveWallet}
                  className="mt-4 w-full bg-violet-600 hover:bg-violet-500 text-white font-bold py-2.5 rounded-xl transition-colors"
                >
                  Salvar Carteira Solana
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Terminal Logs */}
      <div className="bg-[#0c0c0c] border border-zinc-800 rounded-2xl overflow-hidden flex flex-col h-[400px]">
        <div className="bg-zinc-900 border-b border-zinc-800 px-4 py-3 flex items-center justify-between">
          <h3 className="text-sm font-bold text-zinc-300 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
            Terminal Solana WSS
          </h3>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold px-2 py-1 rounded-md ${isConnected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
              {status}
            </span>
          </div>
        </div>
        <div className="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1.5 flex flex-col-reverse">
          {[...logs].reverse().map((log, i) => (
            <div key={i} className="text-zinc-400 break-words border-b border-zinc-800/50 pb-1.5">
              {log}
            </div>
          ))}
          {logs.length === 0 && (
            <div className="text-zinc-600 text-center mt-10">
              Aguardando conexão WSS da Solana...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
