import { useState } from 'react'
import { Key, AlertCircle, CheckCircle2 } from 'lucide-react'

export default function AccountSettings({ token }) {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage(null)
    setError(null)

    if (newPassword !== confirmPassword) {
      setError("As novas senhas não coincidem.")
      return
    }
    if (newPassword.length < 6) {
      setError("A nova senha deve ter pelo menos 6 caracteres.")
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
      })

      const data = await res.json()

      if (res.ok) {
        setMessage("Senha alterada com sucesso!")
        setOldPassword('')
        setNewPassword('')
        setConfirmPassword('')
      } else {
        setError(data.detail || "Erro ao alterar a senha.")
      }
    } catch (err) {
      setError("Erro de comunicação com o servidor.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl shadow-xl overflow-hidden">
        <div className="p-6 border-b border-zinc-800">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <Key size={20} className="text-emerald-400" />
            Alterar Senha
          </h3>
          <p className="text-zinc-400 text-sm mt-1">Atualize sua senha de acesso ao painel HFT.</p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-lg flex items-center gap-3">
              <AlertCircle size={20} />
              <p className="text-sm">{error}</p>
            </div>
          )}
          
          {message && (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg flex items-center gap-3">
              <CheckCircle2 size={20} />
              <p className="text-sm">{message}</p>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-300">Senha Atual</label>
            <input
              type="password"
              required
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 transition-all"
              placeholder="Digite sua senha atual"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-300">Nova Senha</label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 transition-all"
              placeholder="Digite a nova senha"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-300">Confirmar Nova Senha</label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-3 text-white placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 transition-all"
              placeholder="Confirme a nova senha"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-4 bg-emerald-500 hover:bg-emerald-600 text-white font-semibold py-3 px-4 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Salvando...' : 'Atualizar Senha'}
          </button>
        </form>
      </div>
    </div>
  )
}
