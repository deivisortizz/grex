import { useState } from 'react'
import { Lock, Mail, Key, ShieldAlert, ArrowRight } from 'lucide-react'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)

  const handleSubmit = (e) => {
    e.preventDefault()
    
    // Verificação de credenciais Master
    if (email === 'digitalgrex@gmail.com' && password === '@Grex9899') {
      setError(false)
      onLogin()
    } else {
      setError(true)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4 font-sans selection:bg-emerald-500/30">
      
      {/* Elementos de background para estética HFT */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none flex justify-center">
        <div className="w-[800px] h-[500px] bg-emerald-500/10 blur-[120px] rounded-full absolute -top-40 opacity-50" />
        <div className="w-[600px] h-[400px] bg-blue-500/10 blur-[100px] rounded-full absolute -bottom-20 opacity-50" />
        
        {/* Grid de fundo */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#18181b_1px,transparent_1px),linear-gradient(to_bottom,#18181b_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20" />
      </div>

      <div className="w-full max-w-md relative z-10">
        
        {/* Card Principal */}
        <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-3xl shadow-2xl p-8 shadow-black/50">
          
          <div className="flex flex-col items-center mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-2xl flex items-center justify-center shadow-[0_0_30px_rgba(16,185,129,0.3)] mb-6">
              <Lock size={32} className="text-zinc-950" />
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Acesso Restrito</h1>
            <p className="text-zinc-500 text-sm mt-2 text-center">
              Painel de Controle Institucional HFT<br />
              <span className="text-emerald-500 font-mono text-xs mt-1 block">AXOLOTE ENGINE V2.0</span>
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider ml-1">E-mail Master</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Mail size={18} className="text-zinc-600" />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white rounded-xl py-3.5 pl-12 pr-4 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono text-sm"
                  placeholder="admin@grex.com"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider ml-1">Senha de Acesso</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Key size={18} className="text-zinc-600" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white rounded-xl py-3.5 pl-12 pr-4 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono text-sm tracking-widest"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 text-rose-400 p-3 rounded-lg text-sm animate-pulse">
                <ShieldAlert size={16} />
                <span>Acesso negado. Credenciais inválidas.</span>
              </div>
            )}

            <button
              type="submit"
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-4 rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_20px_rgba(16,185,129,0.2)] hover:shadow-[0_0_30px_rgba(16,185,129,0.4)] group mt-4"
            >
              AUTENTICAR
              <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
            </button>
          </form>

        </div>

        {/* Footer info */}
        <p className="text-center text-zinc-600 text-xs mt-8 font-mono">
          © {new Date().getFullYear()} Grex Capital. All systems operational.
        </p>

      </div>
    </div>
  )
}
