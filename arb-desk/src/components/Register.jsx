import { useState } from 'react'
import { Lock, Mail, Key, ShieldAlert, ArrowRight, LogIn } from 'lucide-react'

export default function Register({ onNavigateLogin, inviteToken }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    
    if (password !== confirmPassword) {
      setError('As senhas não coincidem.')
      return
    }

    setLoading(true)
    
    try {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, token: inviteToken })
      })

      const data = await response.json()

      if (response.ok) {
        setSuccess(true)
      } else {
        setError(data.detail || 'Erro ao criar conta.')
      }
    } catch (err) {
      setError('Erro ao conectar com o servidor.')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-4 font-sans text-center">
        <div className="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center mb-4">
          <Lock size={32} />
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">Conta Criada!</h2>
        <p className="text-zinc-400 mb-6 max-w-sm">Sua conta Multi-Tenant foi configurada com sucesso. Você já pode fazer login no painel HFT.</p>
        <button 
          onClick={onNavigateLogin}
          className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 px-8 rounded-xl transition-all shadow-[0_0_20px_rgba(16,185,129,0.2)]"
        >
          Ir para Login
        </button>
      </div>
    )
  }

  if (!inviteToken) {
    return (
      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-4 font-sans text-center">
        <div className="w-16 h-16 bg-rose-500/20 text-rose-400 rounded-full flex items-center justify-center mb-4">
          <ShieldAlert size={32} />
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">Acesso Restrito</h2>
        <p className="text-zinc-400 mb-6 max-w-sm">Link de convite inválido ou ausente. Você precisa de um convite do administrador para criar uma conta.</p>
        <button 
          onClick={onNavigateLogin}
          className="bg-zinc-800 hover:bg-zinc-700 text-white font-bold py-3 px-8 rounded-xl transition-all"
        >
          Voltar ao Login
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4 font-sans selection:bg-emerald-500/30">
      
      {/* Elementos de background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none flex justify-center">
        <div className="w-[800px] h-[500px] bg-emerald-500/10 blur-[120px] rounded-full absolute -top-40 opacity-50" />
        <div className="w-[600px] h-[400px] bg-blue-500/10 blur-[100px] rounded-full absolute -bottom-20 opacity-50" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#18181b_1px,transparent_1px),linear-gradient(to_bottom,#18181b_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20" />
      </div>

      <div className="w-full max-w-md relative z-10">
        
        <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-3xl shadow-2xl p-8 shadow-black/50">
          
          <div className="flex flex-col items-center mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">Criar Conta</h1>
            <p className="text-zinc-500 text-sm mt-2 text-center">
              Acesso ao Engine V2.0
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider ml-1">E-mail</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Mail size={18} className="text-zinc-600" />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono text-sm"
                  placeholder="usuario@dominio.com"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider ml-1">Senha</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Key size={18} className="text-zinc-600" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono text-sm tracking-widest"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider ml-1">Confirmar Senha</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Key size={18} className="text-zinc-600" />
                </div>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 text-white rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono text-sm tracking-widest"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 text-rose-400 p-3 rounded-lg text-sm animate-pulse mt-2">
                <ShieldAlert size={16} />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold py-3.5 rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_20px_rgba(16,185,129,0.2)] mt-6"
            >
              {loading ? 'REGISTRANDO...' : 'REGISTRAR'}
              {!loading && <ArrowRight size={18} />}
            </button>
            
            <button
              type="button"
              onClick={onNavigateLogin}
              className="w-full bg-transparent text-zinc-400 hover:text-white font-medium py-2 rounded-xl flex items-center justify-center gap-2 transition-all"
            >
              <LogIn size={16} />
              Já tem conta? Fazer Login
            </button>
          </form>

        </div>
      </div>
    </div>
  )
}
