import React, { useState, useEffect } from 'react';
import { Save, Crosshair, Wallet, Trash2 } from 'lucide-react';

export default function SolanaSniperTab({ isActive, sendCommand }) {

  const [formData, setFormData] = useState({
    target_token: '',
    slippage: 15,
    jito_tip: 0.001,
    tp_pct: 100,
    sl_pct: 20
  });

  const [walletKey, setWalletKey] = useState('');
  const [walletAddress, setWalletAddress] = useState(null);

  useEffect(() => {
    fetchConfig();
    fetchWallet();
  }, []);

  const fetchConfig = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/user/solana_config', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setFormData({
          target_token: data.target_token || '',
          slippage: data.slippage || 15,
          jito_tip: data.jito_tip || 0.001,
          tp_pct: data.tp_pct || 100,
          sl_pct: data.sl_pct || 20
        });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchWallet = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/user/solana_wallet', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setWalletAddress(data.address);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleConfigChange = (e) => {
    const { name, value } = e.target;
    
    if (['slippage', 'jito_tip', 'tp_pct', 'sl_pct'].includes(name)) {
      // Aceita apenas números, ponto e vírgula, e substitui vírgula por ponto
      let sanitized = value.replace(/,/g, '.').replace(/[^0-9.]/g, '');
      
      // Impede múltiplos pontos
      const parts = sanitized.split('.');
      if (parts.length > 2) {
        sanitized = parts[0] + '.' + parts.slice(1).join('');
      }
      
      setFormData(prev => ({
        ...prev,
        [name]: sanitized
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };

  const parseNumber = (val) => {
    const num = parseFloat(val);
    return isNaN(num) ? 0 : num;
  };

  const handleConfigSubmit = async (e) => {
    e.preventDefault();
    if (isActive) {
      alert("⚠️ Pare o sniper antes de alterar a configuração!");
      return;
    }
    
    const payload = {
      ...formData,
      slippage: parseNumber(formData.slippage),
      jito_tip: parseNumber(formData.jito_tip),
      tp_pct: parseNumber(formData.tp_pct),
      sl_pct: parseNumber(formData.sl_pct)
    };
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/user/solana_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        sendCommand('reset_config');
        alert(data.message);
      } else {
        alert(data.detail || "Erro ao salvar config.");
      }
    } catch (err) {
      console.error(err);
      alert("Erro de conexão.");
    }
  };

  const handleWalletSubmit = async (e) => {
    e.preventDefault();
    if (isActive) {
      alert("⚠️ Pare o sniper antes de cadastrar carteira!");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/user/solana_wallet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ private_key: walletKey })
      });
      const data = await res.json();
      
      if (res.ok) {
        const walletRes = await fetch('/api/user/solana_wallet', { headers: { 'Authorization': `Bearer ${token}` } });
        if (walletRes.ok) {
          const walletData = await walletRes.json();
          setWalletAddress(walletData.address);
        }
        setWalletKey('');
        alert(data.message);
      } else {
        alert(data.detail || "Erro ao salvar carteira.");
      }
    } catch (err) {
      console.error(err);
      alert("Erro de conexão.");
    }
  };

  const handleDeleteWallet = async () => {
    if (!window.confirm("Atenção! Isso apagará sua Burner Wallet do banco de dados. Tem certeza?")) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/user/solana_wallet', {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setWalletAddress(null);
        sendCommand('reset_wallet');
        alert(data.message);
      } else {
        alert(data.detail || "Erro ao apagar carteira.");
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Configurações */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
        <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-2">
          <Crosshair size={18} className="text-violet-400" />
          Alvo e Risco (Solana)
        </h3>
        
        <form onSubmit={handleConfigSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold text-zinc-400 mb-2">Target Token (Pump.fun Mint)</label>
            <input
              type="text"
              name="target_token"
              value={formData.target_token}
              onChange={handleConfigChange}
              disabled={isActive}
              placeholder="Cole o endereço do contrato (Mint)"
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/50 disabled:opacity-50 font-mono transition-all"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Jito Tip (SOL)</label>
              <input
                type="text"
                inputMode="decimal"
                name="jito_tip"
                value={formData.jito_tip}
                onChange={handleConfigChange}
                disabled={isActive}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-violet-500/50 disabled:opacity-50 font-mono transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Slippage (%)</label>
              <input
                type="text"
                inputMode="decimal"
                name="slippage"
                value={formData.slippage}
                onChange={handleConfigChange}
                disabled={isActive}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-violet-500/50 disabled:opacity-50 font-mono transition-all"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Take Profit (%)</label>
              <input
                type="text"
                inputMode="decimal"
                name="tp_pct"
                value={formData.tp_pct}
                onChange={handleConfigChange}
                disabled={isActive}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-emerald-400 focus:outline-none focus:border-emerald-500/50 disabled:opacity-50 font-mono transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Stop Loss (%)</label>
              <input
                type="text"
                inputMode="decimal"
                name="sl_pct"
                value={formData.sl_pct}
                onChange={handleConfigChange}
                disabled={isActive}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-rose-400 focus:outline-none focus:border-rose-500/50 disabled:opacity-50 font-mono transition-all"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isActive}
            className="w-full bg-violet-600 hover:bg-violet-500 text-white font-bold py-3 px-4 rounded-xl text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-violet-500/20 active:scale-95"
          >
            <Save size={16} />
            Salvar Configurações
          </button>
        </form>
      </div>

      {/* Burner Wallet */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 relative overflow-hidden group">
        <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/5 rounded-full blur-3xl -mr-16 -mt-16 group-hover:bg-amber-500/10 transition-colors pointer-events-none" />
        
        <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-2">
          <Wallet size={18} className="text-amber-400" />
          Burner Wallet (Solana)
        </h3>

        {walletAddress ? (
          <div className="space-y-4">
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4">
              <p className="text-xs font-semibold text-amber-500/80 mb-1">Carteira Ativa</p>
              <p className="font-mono text-sm text-amber-400 break-all">{walletAddress}</p>
            </div>
            <button
              onClick={handleDeleteWallet}
              disabled={isActive}
              className="w-full bg-black border border-rose-500/30 hover:bg-rose-500/10 hover:border-rose-500/50 text-rose-400 font-bold py-3 px-4 rounded-xl text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed group/btn"
            >
              <Trash2 size={16} className="group-hover/btn:scale-110 transition-transform" />
              Apagar Carteira
            </button>
          </div>
        ) : (
          <form onSubmit={handleWalletSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Chave Privada (Base58 ou Array)</label>
              <input
                type="password"
                value={walletKey}
                onChange={(e) => setWalletKey(e.target.value)}
                disabled={isActive}
                placeholder="Insira a Private Key"
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-200 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50 disabled:opacity-50 font-mono transition-all"
                required
              />
            </div>
            <button
              type="submit"
              disabled={isActive || !walletKey}
              className="w-full bg-amber-500 hover:bg-amber-400 text-zinc-900 font-bold py-3 px-4 rounded-xl text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-amber-500/20 active:scale-95"
            >
              <Save size={16} />
              Vincular Carteira Segura
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
