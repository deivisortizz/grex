import { useState } from 'react'

export default function ConfigTab({ config, sendConfigUpdate }) {
  const [spread, setSpread] = useState(config.target_spread)
  const [amount, setAmount] = useState(config.trade_amount)

  const handleSave = (e) => {
    e.preventDefault()
    sendConfigUpdate({ target_spread: spread, trade_amount: amount })
  }

  return (
    <div className="max-w-xl">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <h3 className="text-lg font-bold text-white mb-6">Configurações do Robô (Ao Vivo)</h3>
        
        <form onSubmit={handleSave} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-2">TARGET_SPREAD (%)</label>
            <input 
              type="number" 
              step="0.01"
              value={spread}
              onChange={e => setSpread(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500"
            />
            <p className="text-xs text-zinc-500 mt-1.5">O robô só enviará a boleta quando o Spread Líquido cruzar esse valor.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-2">TRADE_AMOUNT (USDT)</label>
            <input 
              type="number" 
              step="1"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-emerald-500"
            />
            <p className="text-xs text-zinc-500 mt-1.5">Volume enviado para ambas as pontas na execução.</p>
          </div>

          <button 
            type="submit"
            className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-bold px-6 py-2.5 rounded-lg transition-colors"
          >
            Salvar e Sincronizar
          </button>
        </form>
      </div>
    </div>
  )
}
