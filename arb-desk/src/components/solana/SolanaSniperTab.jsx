import React, { useState, useEffect } from 'react';
import { Save, Crosshair, Wallet, Trash2, Users } from 'lucide-react';

export default function SolanaSniperTab({ isActive, sendCommand, onSwitchToCopy }) {


    const [formData, setFormData] = useState({
      target_token: '',
      trade_amount: 0.05,
      min_trade_amount_sol: 0.02,
      slippage: 15,
      jito_tip: 0.001,
      tp_pct: 100,
      sl_pct: 20,
      max_positions: 1,
      hardcore_mode: false,
      anti_delay_filter: true,
      socials_filter: true,
      momentum_filter: false,
      max_bonding_curve: 20.0
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
          trade_amount: data.trade_amount || 0.05,
          min_trade_amount_sol: data.min_trade_amount_sol || 0.02,
          slippage: data.slippage || 15,
          jito_tip: data.jito_tip || 0.001,
          tp_pct: data.tp_pct || 100,
          sl_pct: data.sl_pct || 20,
          max_positions: data.max_positions || 1,
          hardcore_mode: data.hardcore_mode || false,
          anti_delay_filter: data.anti_delay_filter !== undefined ? data.anti_delay_filter : true,
          socials_filter: data.socials_filter !== undefined ? data.socials_filter : true,
          momentum_filter: data.momentum_filter || false,
          max_bonding_curve: data.max_bonding_curve || 20.0
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
    
    if (['trade_amount', 'min_trade_amount_sol', 'slippage', 'jito_tip', 'tp_pct', 'sl_pct'].includes(name)) {
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
    } else if (['hardcore_mode', 'anti_delay_filter', 'socials_filter', 'momentum_filter', 'raydium_migration_filter', 'raydium_migrator_active'].includes(name)) {
      setFormData(prev => ({
        ...prev,
        [name]: e.target.checked
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
      trade_amount: parseNumber(formData.trade_amount),
      slippage: parseNumber(formData.slippage),
      jito_tip: parseNumber(formData.jito_tip),
      tp_pct: parseNumber(formData.tp_pct),
      sl_pct: parseNumber(formData.sl_pct),
      max_positions: parseInt(formData.max_positions) || 1,
      hardcore_mode: Boolean(formData.hardcore_mode),
      anti_delay_filter: Boolean(formData.anti_delay_filter),
      socials_filter: Boolean(formData.socials_filter),
      momentum_filter: Boolean(formData.momentum_filter),
      raydium_migration_filter: Boolean(formData.raydium_migration_filter),
      raydium_migrator_active: Boolean(formData.raydium_migrator_active),
      max_bonding_curve: parseNumber(formData.max_bonding_curve)
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
      {/* Smart Money Copy Trading Banner */}
      {onSwitchToCopy && (
        <div 
          onClick={onSwitchToCopy}
          className="bg-gradient-to-r from-cyan-950/40 via-zinc-900 to-zinc-900 border border-cyan-500/30 rounded-2xl p-4 flex items-center justify-between gap-4 cursor-pointer hover:border-cyan-500/50 hover:bg-zinc-800/40 transition-all group shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/25 flex items-center justify-center text-cyan-400 group-hover:scale-105 transition-transform shrink-0">
              <Users size={18} />
            </div>
            <div>
              <p className="text-xs font-bold text-white flex items-center gap-1.5">
                Copy Trading & Wallet Hunter
                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  SMART MONEY
                </span>
              </p>
              <p className="text-[11px] text-zinc-400 mt-0.5">
                Rastreie carteiras de insiders do Bloco 0 e replique compras automaticamente.
              </p>
            </div>
          </div>
          <button className="text-xs font-bold text-cyan-400 group-hover:text-cyan-300 flex items-center gap-1 shrink-0 font-mono">
            Abrir Painel →
          </button>
        </div>
      )}

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

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Buy Amount (SOL)</label>
              <input
                type="text"
                inputMode="decimal"
                name="trade_amount"
                value={formData.trade_amount}
                onChange={handleConfigChange}
                disabled={isActive}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-cyan-400 focus:outline-none focus:border-cyan-500/50 disabled:opacity-50 font-mono transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-2">Aporte Mín. (SOL)</label>
              <input
                type="text"
                inputMode="decimal"
                name="min_trade_amount_sol"
                value={formData.min_trade_amount_sol}
                onChange={handleConfigChange}
                disabled={isActive}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-3 text-sm text-amber-400 focus:outline-none focus:border-amber-500/50 disabled:opacity-50 font-mono transition-all"
              />
            </div>
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

          <div className="bg-black border border-zinc-800 rounded-xl p-4 flex flex-col gap-4 mt-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Crosshair size={16} className="text-violet-500" />
              Filtros de Qualidade (Camadas)
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
                <div>
                  <div className="text-xs font-bold text-white">Modo Hardcore / Cego</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Ignora redes sociais e limites</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" name="hardcore_mode" checked={formData.hardcore_mode} onChange={handleConfigChange} disabled={isActive} className="sr-only peer" />
                  <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-checked:after:translate-x-full after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-rose-600"></div>
                </label>
              </div>

              <div className="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
                <div>
                  <div className="text-xs font-bold text-white">Filtro Anti-Atraso</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Validar token fresco no bloco zero</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" name="anti_delay_filter" checked={formData.anti_delay_filter} onChange={handleConfigChange} disabled={isActive} className="sr-only peer" />
                  <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-checked:after:translate-x-full after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                </label>
              </div>

              <div className="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
                <div>
                  <div className="text-xs font-bold text-white">Exigir Redes Sociais</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">X/Twitter ou Telegram obrigatórios</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" name="socials_filter" checked={formData.socials_filter} onChange={handleConfigChange} disabled={isActive || formData.hardcore_mode} className="sr-only peer" />
                  <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-checked:after:translate-x-full after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                </label>
              </div>

              <div className="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
                <div>
                  <div className="text-xs font-bold text-white flex items-center gap-1">Filtro de Momentum (5s) <span className="text-[9px] bg-rose-500/20 text-rose-400 px-1 rounded">HOT</span></div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Acompanha o tape reading para confirmar alta</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" name="momentum_filter" checked={formData.momentum_filter} onChange={handleConfigChange} disabled={isActive} className="sr-only peer" />
                  <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-checked:after:translate-x-full after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-rose-500"></div>
                </label>
              </div>

              <div className="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
                <div>
                  <div className="text-xs font-bold text-white flex items-center gap-1">Migração Raydium <span className="text-[9px] bg-orange-500/20 text-orange-400 px-1 rounded">NEW</span></div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Foca em tokens quase completando a curva</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" name="raydium_migration_filter" checked={formData.raydium_migration_filter} onChange={handleConfigChange} disabled={isActive} className="sr-only peer" />
                  <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-checked:after:translate-x-full after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-orange-500"></div>
                </label>
              </div>

              <div className="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg border border-zinc-800">
                <div>
                  <div className="text-xs font-bold text-white flex items-center gap-1">Raydium Pool Sniper <span className="text-[9px] bg-indigo-500/20 text-indigo-400 px-1 rounded">PRO</span></div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Atira na abertura oficial da pool (Burned)</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" name="raydium_migrator_active" checked={formData.raydium_migrator_active} onChange={handleConfigChange} disabled={isActive} className="sr-only peer" />
                  <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-checked:after:translate-x-full after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-500"></div>
                </label>
              </div>

              <div className="bg-zinc-900/50 p-3 rounded-lg border border-zinc-800 flex flex-col justify-center md:col-span-2">
                <label className="block text-xs font-bold text-white mb-1">Trava Bonding Curve (SOL)</label>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-zinc-500">Bloqueia entrada se saldo virtual exceder X SOL:</span>
                  <input type="text" inputMode="decimal" name="max_bonding_curve" value={formData.max_bonding_curve} onChange={handleConfigChange} disabled={isActive} className="w-20 bg-black border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-violet-500" />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between mt-2 pt-4 border-t border-zinc-800">
              <label className="block text-xs font-semibold text-zinc-400">Máximo Posições Simultâneas</label>
              <input type="number" name="max_positions" min="1" max="20" value={formData.max_positions} onChange={handleConfigChange} disabled={isActive || formData.hardcore_mode} className="w-24 bg-black border border-zinc-800 rounded-lg px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-violet-500/50" />
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
