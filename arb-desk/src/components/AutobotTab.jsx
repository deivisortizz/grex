import { Power } from 'lucide-react'

export default function AutobotTab({ isSpatialActive, sendCommand }) {
  const toggleBot = () => {
    if (isSpatialActive) {
      sendCommand('pause_spatial')
    } else {
      sendCommand('start_spatial')
    }
  }

  return (
    <div className="max-w-xl">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <h3 className="text-lg font-bold text-white mb-2">Controle do Autobot</h3>
        <div className={`p-8 rounded-xl border flex flex-col items-center text-center transition-colors ${
        isSpatialActive ? 'bg-emerald-950/20 border-emerald-500/20' : 'bg-zinc-900 border-zinc-800'
      }`}>
        <div className={`w-20 h-20 rounded-full flex items-center justify-center mb-6 transition-colors ${
          isSpatialActive ? 'bg-emerald-500/20 text-emerald-400 animate-pulse' : 'bg-zinc-800 text-zinc-500'
        }`}>
          <Power size={40} />
        </div>
        <h3 className="text-2xl font-bold text-white mb-2">
          {isSpatialActive ? 'Motor Espacial Ativo' : 'Motor Espacial Pausado'}
        </h3>
        <p className="text-zinc-400 mb-8 max-w-md">
          {isSpatialActive 
            ? 'O HFT está escaneando múltiplas corretoras e executará ordens cruzadas automaticamente ao encontrar spread favorável.'
            : 'O scanner de mercado espacial está monitorando os dados, mas a execução de ordens está desativada.'}
        </p>
        <button
          onClick={toggleBot}
          className={`px-8 py-4 rounded-lg font-bold flex items-center gap-2 transition-all ${
            isSpatialActive
              ? 'bg-rose-500 hover:bg-rose-600 text-white shadow-lg shadow-rose-500/20'
              : 'bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/20'
          }`}
        >
          {isSpatialActive ? (
            <>Pausar Autobot Espacial</>
          ) : (
            <>Ligar Autobot Espacial</>
          )}
        </button>
        </div>
      </div>
    </div>
  )
}
