import { useEffect } from 'react'

export default function HistoryTab({ history, sendCommand }) {
  useEffect(() => {
    // Solicita o histórico ao abrir a aba
    if (sendCommand) {
      sendCommand('get_history')
    }
  }, [sendCommand])

  if (history.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-zinc-500">Nenhum trade realizado ainda. O banco de dados trades.db está vazio.</p>
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <table className="w-full text-left text-sm text-zinc-400">
        <thead className="bg-zinc-950 text-zinc-500 uppercase text-xs font-semibold">
          <tr>
            <th className="px-6 py-4">Data/Hora</th>
            <th className="px-6 py-4">Status</th>
            <th className="px-6 py-4">Rota (Compra → Venda)</th>
            <th className="px-6 py-4 text-right">Spread Pego</th>
            <th className="px-6 py-4 text-right">Lucro BRL</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/50">
          {history.map((trade, idx) => (
            <tr key={idx} className="hover:bg-zinc-800/20 transition-colors">
              <td className="px-6 py-4 font-mono">{new Date(trade.timestamp).toLocaleString()}</td>
              <td className="px-6 py-4">
                <span className="px-2 py-1 bg-emerald-500/10 text-emerald-400 rounded-full text-[10px] font-bold">SUCCESS</span>
              </td>
              <td className="px-6 py-4 font-medium text-white">{trade.exchange_buy} → {trade.exchange_sell}</td>
              <td className="px-6 py-4 text-right font-mono text-emerald-400">+{trade.spread_bruto}%</td>
              <td className="px-6 py-4 text-right font-mono text-emerald-400">R$ {trade.lucro_liquido.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
