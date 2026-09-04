import { useState } from 'react'
import { Plus, Server, Key, Shield, EyeOff } from 'lucide-react'

export default function ExchangesTab({ exchanges = [], sendCommand }) {
  const [formData, setFormData] = useState({
    exchange: '',
    apiKey: '',
    secret: '',
    password: ''
  })

  const handleConnect = (e) => {
    e.preventDefault()
    if (!formData.apiKey || !formData.secret) return

    sendCommand('add_exchange', {
      exchange: formData.exchange,
      credentials: {
        apiKey: formData.apiKey,
        secret: formData.secret,
        password: formData.password || undefined
      }
    })

    setFormData({ ...formData, apiKey: '', secret: '', password: '' })
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      {/* Lista de Ativas */}
      <div>
        <h3 className="text-lg font-bold text-white mb-6">Corretoras Ativas (HFT)</h3>
        <div className="space-y-4">
          {exchanges.map((ex) => (
            <div key={ex} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center">
                  <Server size={20} className="text-zinc-400" />
                </div>
                <div>
                  <h4 className="text-white font-bold">{ex}</h4>
                  <p className="text-xs text-zinc-500">Conectado via WebSocket</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]"></span>
                <span className="text-xs font-bold text-emerald-500 uppercase">Live</span>
              </div>
            </div>
          ))}
          {exchanges.length === 0 && (
            <p className="text-zinc-500 text-sm">Nenhuma corretora conectada.</p>
          )}
        </div>
      </div>

      {/* Formulário de Adição */}
      <div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-emerald-500/10 rounded-lg">
              <Plus className="text-emerald-500" size={20} />
            </div>
            <h3 className="text-lg font-bold text-white">Adicionar Corretora</h3>
          </div>
          
          <form onSubmit={handleConnect} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">
                Corretora (CCXT Pro)
              </label>
              <input 
                type="text" 
                value={formData.exchange}
                onChange={e => setFormData({...formData, exchange: e.target.value.toLowerCase()})}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-2.5 text-white outline-none focus:border-emerald-500 transition-colors"
                placeholder="Ex: mexc, bybit, phemex, okx..."
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">
                API Key
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-3 text-zinc-500" size={16} />
                <input 
                  type="text" 
                  value={formData.apiKey}
                  onChange={e => setFormData({...formData, apiKey: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-10 pr-4 py-2 text-white outline-none focus:border-emerald-500 transition-colors"
                  placeholder="Cole sua API Key pública"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">
                API Secret
              </label>
              <div className="relative">
                <Shield className="absolute left-3 top-3 text-zinc-500" size={16} />
                <input 
                  type="password" 
                  value={formData.secret}
                  onChange={e => setFormData({...formData, secret: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-10 pr-4 py-2 text-white outline-none focus:border-emerald-500 transition-colors"
                  placeholder="Cole sua Chave Privada (Secret)"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">
                API Password / Passphrase <span className="lowercase text-zinc-600">(opcional)</span>
              </label>
              <div className="relative">
                <EyeOff className="absolute left-3 top-3 text-zinc-500" size={16} />
                <input 
                  type="password" 
                  value={formData.password}
                  onChange={e => setFormData({...formData, password: e.target.value})}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-10 pr-4 py-2 text-white outline-none focus:border-emerald-500 transition-colors"
                  placeholder="Apenas para KuCoin, OKX e Bitget"
                />
              </div>
            </div>

            <div className="pt-4">
              <button 
                type="submit"
                className="w-full bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                Conectar Stream WS
              </button>
            </div>
            <p className="text-xs text-zinc-500 text-center mt-4">
              A chave será injetada diretamente na memória Viva (RAM) do motor Python e será esquecida ao desligar o robô.
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}
