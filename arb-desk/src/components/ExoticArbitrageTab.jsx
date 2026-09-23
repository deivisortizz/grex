import { useState } from 'react'
import { Globe2, Plus, Key, Shield, Trash2, Power, TrendingUp, TrendingDown, ShieldAlert, Activity } from 'lucide-react'

const EXOTIC_EXCHANGE_OPTIONS = [
  { value: 'GATEIO', label: 'Gate.io' },
  { value: 'MERCADOBITCOIN', label: 'Mercado Bitcoin' },
]

const STATUS_LABELS = {
  executed: { label: 'Executado', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
  discarded_thin_book: { label: 'Livro Raso', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
  discarded_low_net: { label: 'Spread Insuficiente', color: 'text-zinc-400 bg-zinc-800 border-zinc-700' },
  discarded_risk_limit: { label: 'Limite de Risco', color: 'text-rose-400 bg-rose-500/10 border-rose-500/20' },
  discarded_cooldown: { label: 'Cooldown', color: 'text-zinc-500 bg-zinc-800 border-zinc-700' },
  discarded_paused: { label: 'Motor Pausado', color: 'text-zinc-500 bg-zinc-800 border-zinc-700' },
  leg_failure: { label: 'Falha de Execução', color: 'text-rose-400 bg-rose-500/10 border-rose-500/20' },
}

export default function ExoticArbitrageTab({ isExoticActive = false, exoticExchanges = [], opportunities = [], sendCommand }) {
  const [formData, setFormData] = useState({ exchange: 'GATEIO', apiKey: '', secret: '' })
  const [showForm, setShowForm] = useState(false)

  const handleToggle = () => {
    sendCommand(isExoticActive ? 'pause_exotic' : 'start_exotic')
  }

  const handleConnect = (e) => {
    e.preventDefault()
    if (!formData.apiKey || !formData.secret) return
    sendCommand('add_exotic_exchange', {
      exchange: formData.exchange,
      credentials: { apiKey: formData.apiKey, secret: formData.secret }
    })
    setFormData({ ...formData, apiKey: '', secret: '' })
    setShowForm(false)
  }

  const handleDelete = (ex) => {
    if (!window.confirm(`Remover ${ex} do motor de pares exóticos?`)) return
    sendCommand('delete_exotic_exchange', { exchange: ex })
  }

  const executedCount = opportunities.filter(o => o.status === 'executed').length
  const discardedCount = opportunities.length - executedCount

  return (
    <div className="space-y-6">
      {/* Master Control */}
      <div className={`border rounded-2xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all ${
        isExoticActive
          ? 'bg-emerald-500/5 border-emerald-500/30 shadow-[0_0_25px_rgba(16,185,129,0.08)]'
          : 'bg-zinc-900 border-zinc-800'
      }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center border ${
            isExoticActive ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-zinc-800 border-zinc-700 text-zinc-500'
          }`}>
            <Globe2 size={22} className={isExoticActive ? 'animate-pulse' : ''} />
          </div>
          <div>
            <h3 className="font-bold text-white tracking-tight">Motor de Pares Exóticos (Tier-2)</h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Gate.io / Mercado Bitcoin — spreads de 0,5% a 1,5% fora da rota disputada por HFT institucional.
            </p>
          </div>
        </div>
        <button
          onClick={handleToggle}
          className={`px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all cursor-pointer ${
            isExoticActive
              ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500/20'
              : 'bg-emerald-500 hover:bg-emerald-400 text-zinc-900'
          }`}
        >
          <Power size={16} />
          {isExoticActive ? 'Pausar Motor' : 'Ativar Motor'}
        </button>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400">Exchanges Conectadas</p>
          <p className="text-2xl font-bold font-mono text-white mt-1">{exoticExchanges.length}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400">Oportunidades Executadas</p>
          <p className="text-2xl font-bold font-mono text-emerald-400 mt-1">{executedCount}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400">Descartadas (custo/risco/livro)</p>
          <p className="text-2xl font-bold font-mono text-zinc-400 mt-1">{discardedCount}</p>
        </div>
      </div>

      {/* Exchange management */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <h4 className="text-sm font-bold text-white mb-4">Exchanges Conectadas</h4>
          <div className="space-y-3">
            {exoticExchanges.map((ex) => (
              <div key={ex} className="flex items-center justify-between bg-zinc-950/60 border border-zinc-800 rounded-xl px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-sm font-bold text-white">
                    {EXOTIC_EXCHANGE_OPTIONS.find(o => o.value === ex)?.label || ex}
                  </span>
                </div>
                <button
                  onClick={() => handleDelete(ex)}
                  className="p-1.5 rounded-lg bg-zinc-800/60 hover:bg-rose-500/10 text-zinc-400 hover:text-rose-400 transition-colors"
                  title="Remover"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {exoticExchanges.length === 0 && (
              <p className="text-sm text-zinc-500">Nenhuma exchange exótica conectada ainda.</p>
            )}
          </div>

          {!showForm ? (
            <button
              onClick={() => setShowForm(true)}
              className="mt-4 w-full flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-white font-semibold text-sm py-2.5 rounded-xl transition-colors"
            >
              <Plus size={16} /> Conectar Gate.io / Mercado Bitcoin
            </button>
          ) : (
            <form onSubmit={handleConnect} className="mt-4 space-y-3 border-t border-zinc-800 pt-4">
              <select
                value={formData.exchange}
                onChange={e => setFormData({ ...formData, exchange: e.target.value })}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
              >
                {EXOTIC_EXCHANGE_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <div className="relative">
                <Key className="absolute left-3 top-2.5 text-zinc-500" size={14} />
                <input
                  type="text"
                  value={formData.apiKey}
                  onChange={e => setFormData({ ...formData, apiKey: e.target.value })}
                  placeholder="API Key"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-9 pr-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  required
                />
              </div>
              <div className="relative">
                <Shield className="absolute left-3 top-2.5 text-zinc-500" size={14} />
                <input
                  type="password"
                  value={formData.secret}
                  onChange={e => setFormData({ ...formData, secret: e.target.value })}
                  placeholder="API Secret"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-9 pr-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  required
                />
              </div>
              <div className="flex gap-2">
                <button type="submit" className="flex-1 bg-emerald-500 hover:bg-emerald-400 text-zinc-900 font-bold py-2 rounded-lg text-sm transition-colors">
                  Conectar
                </button>
                <button type="button" onClick={() => setShowForm(false)} className="px-4 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition-colors">
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Info card */}
        <div className="bg-gradient-to-br from-zinc-900 to-zinc-950 border border-zinc-800 rounded-2xl p-5">
          <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
            <ShieldAlert size={16} className="text-amber-400" />
            Como funciona o filtro de custo
          </h4>
          <ul className="text-xs text-zinc-400 space-y-2 leading-relaxed">
            <li>• O spread é calculado andando o livro de ordens real (VWAP), não só o topo do book — evita entrar num spread que só existe pra um tamanho minúsculo de ordem.</li>
            <li>• Taxas de taker de cada ponta (Mercado Bitcoin ~0,7%, Gate.io ~0,2%) são descontadas antes de decidir executar.</li>
            <li>• Toda oportunidade avaliada é registrada — mesmo as descartadas — pra você auditar o que o motor está vendo.</li>
          </ul>
        </div>
      </div>

      {/* Live opportunities feed */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-zinc-800 flex items-center gap-2 bg-black/40">
          <Activity size={16} className="text-zinc-400" />
          <h4 className="text-sm font-bold text-white">Oportunidades Detectadas (ao vivo)</h4>
        </div>
        <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-zinc-900 z-10">
              <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                <th className="px-5 py-2.5 font-medium">Hora</th>
                <th className="px-4 py-2.5 font-medium">Par</th>
                <th className="px-4 py-2.5 font-medium">Rota</th>
                <th className="px-4 py-2.5 font-medium text-right">Spread Líquido</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-5 py-2.5 font-medium">Motivo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {opportunities.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-5 py-10 text-center text-zinc-500 text-sm">
                    Nenhuma oportunidade detectada ainda. Conecte uma exchange e ative o motor.
                  </td>
                </tr>
              ) : (
                opportunities.slice().reverse().map((op, idx) => {
                  const statusInfo = STATUS_LABELS[op.status] || { label: op.status, color: 'text-zinc-400 bg-zinc-800 border-zinc-700' }
                  const isPositive = op.net_spread_pct >= 0
                  return (
                    <tr key={idx} className="hover:bg-zinc-800/20">
                      <td className="px-5 py-2.5 text-xs text-zinc-500 font-mono">
                        {op.timestamp ? new Date(op.timestamp).toLocaleTimeString('pt-BR') : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono text-zinc-300">{op.symbol}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-zinc-400">
                        {op.buy_exchange} → {op.sell_exchange}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={`inline-flex items-center gap-1 font-mono text-xs font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                          {op.net_spread_pct?.toFixed(3)}%
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${statusInfo.color}`}>
                          {statusInfo.label}
                        </span>
                      </td>
                      <td className="px-5 py-2.5 text-xs text-zinc-500 max-w-xs truncate" title={op.reason}>
                        {op.reason}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
