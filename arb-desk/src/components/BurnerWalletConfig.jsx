import { useState, useEffect, useRef } from 'react'
import { Wallet, Key, CheckCircle2, AlertCircle, Save } from 'lucide-react'

export default function BurnerWalletConfig() {
  const [address, setAddress] = useState('')
  const [privateKey, setPrivateKey] = useState('')
  const [walletStatus, setWalletStatus] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  
  const wsRef = useRef(null)

  useEffect(() => {
    // Configura a URL dinamicamente via ENV ou fallback para localhost
    const wsUrl = import.meta.env.VITE_SNIPER_WS_URL || 'ws://localhost:8766'
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'wallet_status') {
          setWalletStatus(data.wallet_address)
        }
      } catch (err) {
        console.error('Erro ao fazer parse do WS Sniper:', err)
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
    }

    return () => {
      ws.close()
    }
  }, [])

  const handleSaveWallet = (e) => {
    e.preventDefault()
    if (!address || !privateKey) return
    
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'add_wallet',
        address: address,
        private_key: privateKey
      }))
      
      // Limpar formulário por segurança visual
      setAddress('')
      setPrivateKey('')
    }
  }

  // Função para mascarar a carteira (ex: 0x1234...ABCD)
  const maskAddress = (addr) => {
    if (!addr) return ''
    return `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-xl">
      <div className="flex items-center justify-between mb-6 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Wallet size={20} className="text-emerald-500" />
            Cofre da Burner Wallet
          </h2>
          <p className="text-zinc-500 text-sm mt-1">Configure a carteira de execução HFT para a rede Base.</p>
        </div>
        
        {/* Indicador de Conexão WS do Sniper */}
        <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold font-mono ${isConnected ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
          {isConnected ? 'SNIPER WS ON' : 'SNIPER WS OFF'}
        </div>
      </div>

      {/* Status Atual */}
      {walletStatus ? (
        <div className="mb-6 p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/20 flex items-center gap-3 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
          <CheckCircle2 size={24} className="text-emerald-500" />
          <div>
            <p className="text-sm font-bold text-emerald-400">Carteira Ativa e Criptografada</p>
            <p className="text-xs text-zinc-400 font-mono mt-0.5">{maskAddress(walletStatus)}</p>
          </div>
        </div>
      ) : (
        <div className="mb-6 p-4 rounded-xl bg-amber-950/30 border border-amber-500/20 flex items-center gap-3">
          <AlertCircle size={24} className="text-amber-500" />
          <div>
            <p className="text-sm font-bold text-amber-400">Nenhuma carteira configurada</p>
            <p className="text-xs text-zinc-400 mt-0.5">O Sniper rodará apenas no modo leitura do Mempool.</p>
          </div>
        </div>
      )}

      {/* Formulário */}
      <form onSubmit={handleSaveWallet} className="space-y-4">
        <div>
          <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1.5 ml-1">Endereço Público (0x)</label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Wallet size={16} className="text-zinc-600" />
            </div>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="0x..."
              className="w-full bg-zinc-950 border border-zinc-800 text-zinc-300 rounded-xl py-3 pl-10 pr-4 focus:outline-none focus:border-emerald-500 font-mono text-sm"
              required
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1.5 ml-1">Private Key (PK)</label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Key size={16} className="text-zinc-600" />
            </div>
            <input
              type="password"
              value={privateKey}
              onChange={(e) => setPrivateKey(e.target.value)}
              placeholder="Sua chave privada HFT..."
              className="w-full bg-zinc-950 border border-zinc-800 text-zinc-300 rounded-xl py-3 pl-10 pr-4 focus:outline-none focus:border-emerald-500 font-mono text-sm"
              required
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={!isConnected}
          className="w-full mt-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-white font-bold py-3.5 rounded-xl flex items-center justify-center gap-2 transition-all"
        >
          <Save size={16} />
          Criptografar e Salvar no Cofre
        </button>
      </form>
    </div>
  )
}
