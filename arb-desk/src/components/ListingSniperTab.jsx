import { useState } from 'react'
import { Rocket, Plus, Key, Shield, Power, Activity, Timer, Percent, Clock } from 'lucide-react'
import { useListingSniperWebSocket } from '../hooks/useListingSniperWebSocket'

const EXCHANGE_OPTIONS = [
  { value: 'MEXC', label: 'MEXC' },
]

const STATUS_LABELS = {
  open: { label: 'Aberto', color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20' },
  closed_tp: { label: 'Take Profit', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
  closed_sl: { label: 'Stop Loss', color: 'text-rose-400 bg-rose-500/10 border-rose-500/20' },
  closed_timeout: { label: 'Timeout', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
  closed_manual: { label: 'Manual', color: 'text-zinc-400 bg-zinc-800 border-zinc-700' },
  failed: { label: 'Falhou', color: 'text-rose-400 bg-rose-500/10 border-rose-500/20' },
}

const FEED_LABELS = {
  announcement: { label: 'Anúncio Detectado', color: 'text-zinc-300' },
  trade_opened: { label: 'Compra Executada', color: 'text-emerald-400' },
  trade_closed: { label: 'Posição Encerrada', color: 'text-cyan-400' },
  trade_failed: { label: 'Falha na Compra', color: 'text-rose-400' },
  exit_failed: { label: 'Falha na Saída', color: 'text-rose-500' },
  monitor_crashed: { label: 'Monitor Caiu', color: 'text-rose-500' },
}

export default function ListingSniperTab() {
  const { status, exchanges, trades, avgLatencyMs, feed, armExchange, disarmExchange } = useListingSniperWebSocket()
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    exchange: 'MEXC', apiKey: '', secret: '',
    trade_amount_quote: 20, tp_pct: 50, sl_pct: 15, max_hold_seconds: 300,
  })

  const isOnline = status === 'Online'
  const armedCount = exchanges.filter(e => e.is_armed).length
  const openTrades = trades.filter(t => t.status === 'open').length
  const closedTrades = trades.filter(t => t.status !== 'open')
  const wins = closedTrades.filter(t => (t.pnl_pct ?? 0) > 0).length
  const winRate = closedTrades.length > 0 ? (wins / closedTrades.length) * 100 : 0

  const handleConnect = (e) => {
    e.preventDefault()
    if (!formData.apiKey || !formData.secret) return
    armExchange(formData.exchange, { apiKey: formData.apiKey, secret: formData.secret }, {
      trade_amount_quote: Number(formData.trade_amount_quote),
      tp_pct: Number(formData.tp_pct),
      sl_pct: Number(formData.sl_pct),
      max_hold_seconds: Number(formData.max_hold_seconds),
    })
    setFormData({ ...formData, apiKey: '', secret: '' })
    setShowForm(false)
  }

  const handleDisarm = (ex) => {
    if (!window.confirm(`Desarmar ${ex}? Nenhum novo anúncio será operado nessa exchange.`)) return
    disarmExchange(ex)
  }

  return (
    <div className="space-y-6">
      {/* Master status */}
      <div className={`border rounded-2xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all ${
        isOnline ? 'bg-emerald-500/5 border-emerald-500/30 shadow-[0_0_25px_rgba(16,185,129,0.08)]' : 'bg-zinc-900 border-zinc-800'
      }`}>
        <div className="flex items-center gap-3.5">
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center border ${
            isOnline ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-zinc-800 border-zinc-700 text-zinc-500'
          }`}>
            <Rocket size={22} className={isOnline ? 'animate-pulse' : ''} />
          </div>
          <div>
            <h3 className="font-bold text-white tracking-tight">CEX Listing Sniper</h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Detecta anúncios de listagem Tier-2/3 (hoje: MEXC) e compra a mercado com TP/SL automático.
            </p>
          </div>
        </div>
        <span className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border ${
          isOnline ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5' : 'text-rose-400 border-rose-500/20 bg-rose-500/5'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`}></span>
          {isOnline ? 'Conectado' : 'Desconectado'}
        </span>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400 flex items-center gap-1.5"><Shield size={12} /> Exchanges Armadas</p>
          <p className="text-2xl font-bold font-mono text-white mt-1">{armedCount}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400 flex items-center gap-1.5"><Activity size={12} /> Posições Abertas</p>
          <p className="text-2xl font-bold font-mono text-cyan-400 mt-1">{openTrades}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400 flex items-center gap-1.5"><Percent size={12} /> Win Rate</p>
          <p className="text-2xl font-bold font-mono text-emerald-400 mt-1">{winRate.toFixed(0)}%</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-xs text-zinc-400 flex items-center gap-1.5"><Timer size={12} /> Latência Média de Detecção</p>
          <p className="text-2xl font-bold font-mono text-white mt-1">
            {avgLatencyMs !== null && avgLatencyMs !== undefined ? `${Math.round(avgLatencyMs)}ms` : '—'}
          </p>
        </div>
      </div>

      {/* Exchange management */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <h4 className="text-sm font-bold text-white mb-4">Exchanges Configuradas</h4>
          <div className="space-y-3">
            {exchanges.map((ex) => (
              <div key={ex.exchange} className="flex items-center justify-between bg-zinc-950/60 border border-zinc-800 rounded-xl px-4 py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${ex.is_armed ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'}`} />
                    <span className="text-sm font-bold text-white">
                      {EXCHANGE_OPTIONS.find(o => o.value === ex.exchange)?.label || ex.exchange}
                    </span>
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border text-zinc-400 bg-zinc-800 border-zinc-700">
                      {ex.is_armed ? 'Armada' : 'Desarmada'}
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-500 font-mono mt-1">
                    {ex.trade_amount_quote} por trade · TP {ex.tp_pct}% · SL {ex.sl_pct}% · timeout {ex.max_hold_seconds}s
                  </p>
                </div>
                {ex.is_armed && (
                  <button
                    onClick={() => handleDisarm(ex.exchange)}
                    className="p-1.5 rounded-lg bg-zinc-800/60 hover:bg-rose-500/10 text-zinc-400 hover:text-rose-400 transition-colors"
                    title="Desarmar"
                  >
                    <Power size={14} />
                  </button>
                )}
              </div>
            ))}
            {exchanges.length === 0 && (
              <p className="text-sm text-zinc-500">Nenhuma exchange configurada ainda.</p>
            )}
          </div>

          {!showForm ? (
            <button
              onClick={() => setShowForm(true)}
              className="mt-4 w-full flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-white font-semibold text-sm py-2.5 rounded-xl transition-colors"
            >
              <Plus size={16} /> Armar Exchange
            </button>
          ) : (
            <form onSubmit={handleConnect} className="mt-4 space-y-3 border-t border-zinc-800 pt-4">
              <select
                value={formData.exchange}
                onChange={e => setFormData({ ...formData, exchange: e.target.value })}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
              >
                {EXCHANGE_OPTIONS.map(o => (
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
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-zinc-500">Valor por trade (cotação)</label>
                  <input
                    type="number" step="0.01" value={formData.trade_amount_quote}
                    onChange={e => setFormData({ ...formData, trade_amount_quote: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-zinc-500 flex items-center gap-1"><Clock size={10} /> Timeout (s)</label>
                  <input
                    type="number" step="1" value={formData.max_hold_seconds}
                    onChange={e => setFormData({ ...formData, max_hold_seconds: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-zinc-500">Take Profit (%)</label>
                  <input
                    type="number" step="0.1" value={formData.tp_pct}
                    onChange={e => setFormData({ ...formData, tp_pct: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-zinc-500">Stop Loss (%)</label>
                  <input
                    type="number" step="0.1" value={formData.sl_pct}
                    onChange={e => setFormData({ ...formData, sl_pct: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <button type="submit" className="flex-1 bg-emerald-500 hover:bg-emerald-400 text-zinc-900 font-bold py-2 rounded-lg text-sm transition-colors">
                  Armar
                </button>
                <button type="button" onClick={() => setShowForm(false)} className="px-4 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition-colors">
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Live feed */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-zinc-800 flex items-center gap-2 bg-black/40">
            <Activity size={16} className="text-zinc-400" />
            <h4 className="text-sm font-bold text-white">Feed ao Vivo</h4>
          </div>
          <div className="overflow-y-auto max-h-[360px] divide-y divide-zinc-800/60">
            {feed.length === 0 ? (
              <p className="text-sm text-zinc-500 px-5 py-10 text-center">Aguardando anúncios de listagem...</p>
            ) : (
              feed.map((item, idx) => {
                const info = FEED_LABELS[item.kind] || { label: item.kind, color: 'text-zinc-400' }
                return (
                  <div key={idx} className="px-5 py-2.5 text-xs">
                    <div className="flex items-center justify-between">
                      <span className={`font-bold ${info.color}`}>{info.label}</span>
                      <span className="text-zinc-600 font-mono">{new Date(item.ts).toLocaleTimeString('pt-BR')}</span>
                    </div>
                    <p className="text-zinc-500 mt-0.5 truncate">
                      {item.ticker || item.symbol} {item.title ? `— ${item.title}` : ''}
                      {item.latency_ms !== undefined && item.latency_ms !== null && ` · ${item.latency_ms}ms`}
                      {item.pnl_pct !== undefined && ` · PnL ${item.pnl_pct >= 0 ? '+' : ''}${item.pnl_pct.toFixed(2)}%`}
                      {item.reason && ` · ${item.reason}`}
                    </p>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>

      {/* Trade history */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-zinc-800 flex items-center gap-2 bg-black/40">
          <Activity size={16} className="text-zinc-400" />
          <h4 className="text-sm font-bold text-white">Histórico de Trades</h4>
        </div>
        <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-zinc-900 z-10">
              <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                <th className="px-5 py-2.5 font-medium">Entrada</th>
                <th className="px-4 py-2.5 font-medium">Símbolo</th>
                <th className="px-4 py-2.5 font-medium text-right">Preço Compra</th>
                <th className="px-4 py-2.5 font-medium text-right">Latência Entrada</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-5 py-2.5 font-medium text-right">PnL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {trades.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-5 py-10 text-center text-zinc-500 text-sm">
                    Nenhum trade registrado ainda.
                  </td>
                </tr>
              ) : (
                trades.map((t) => {
                  const statusInfo = STATUS_LABELS[t.status] || { label: t.status, color: 'text-zinc-400 bg-zinc-800 border-zinc-700' }
                  const isPositive = (t.pnl_pct ?? 0) >= 0
                  return (
                    <tr key={t.id} className="hover:bg-zinc-800/20">
                      <td className="px-5 py-2.5 text-xs text-zinc-500 font-mono">
                        {t.entry_at ? new Date(t.entry_at).toLocaleTimeString('pt-BR') : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono text-zinc-300">{t.exchange}:{t.symbol}</td>
                      <td className="px-4 py-2.5 text-right text-xs font-mono text-zinc-300">{t.buy_price ?? '—'}</td>
                      <td className="px-4 py-2.5 text-right text-xs font-mono text-zinc-400">
                        {t.entry_latency_ms !== null && t.entry_latency_ms !== undefined ? `${t.entry_latency_ms}ms` : '—'}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${statusInfo.color}`}>
                          {statusInfo.label}
                        </span>
                      </td>
                      <td className="px-5 py-2.5 text-right">
                        {t.pnl_pct !== null && t.pnl_pct !== undefined ? (
                          <span className={`font-mono text-xs font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {isPositive ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                          </span>
                        ) : (
                          <span className="text-zinc-600 text-xs">—</span>
                        )}
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
