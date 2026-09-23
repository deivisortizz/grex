import { useState, useEffect } from 'react'
import { Shield, Users, Activity, Lock, Unlock, CalendarPlus } from 'lucide-react'

export default function AdminDashboard({ token }) {
  const [stats, setStats] = useState({ total_users: 0, active_users: 0 })
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  const [inviteLink, setInviteLink] = useState('')
  const [loadingInvite, setLoadingInvite] = useState(false)
  const [systemStatus, setSystemStatus] = useState({
    solana_sniper_enabled: true,
    base_sniper_enabled: true
  })

  const fetchData = async () => {
    try {
      const headers = { 'Authorization': `Bearer ${token}` }
      
      const [statsRes, usersRes, listeningRes] = await Promise.all([
        fetch('/api/admin/stats', { headers }),
        fetch('/api/admin/users', { headers }),
        fetch('/api/admin/system/listening_status', { headers })
      ])

      if (!statsRes.ok || !usersRes.ok) throw new Error('Acesso negado ou erro no servidor')

      const statsData = await statsRes.json()
      const usersData = await usersRes.json()
      
      if (listeningRes.ok) {
        const listeningData = await listeningRes.json()
        setSystemStatus({
          solana_sniper_enabled: listeningData.solana_sniper_enabled ?? true,
          base_sniper_enabled: listeningData.base_sniper_enabled ?? true
        })
      }

      setStats(statsData)
      setUsers(usersData.users || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (token) fetchData()
  }, [token])

  const handleToggleStatus = async (userId, currentStatus) => {
    try {
      const res = await fetch(`/api/admin/user/${userId}/toggle-status`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        setUsers(users.map(u => u.id === userId ? { ...u, is_active: !currentStatus } : u))
        fetchData() // refresh stats
      }
    } catch (err) {
      alert("Erro ao alterar status.")
    }
  }

  const handleExtend = async (userId) => {
    const days = parseInt(window.prompt("Quantos dias deseja adicionar? (ex: 30)"), 10)
    if (isNaN(days) || days <= 0) return

    try {
      const res = await fetch(`/api/admin/user/${userId}/extend`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ days })
      })
      if (res.ok) {
        fetchData()
        alert("Assinatura estendida com sucesso!")
      }
    } catch (err) {
      alert("Erro ao estender assinatura.")
    }
  }

  const handleDelete = async (userId) => {
    if (!window.confirm(`Tem certeza que deseja excluir o usuário #${userId}? Esta ação é irreversível.`)) return;

    try {
      const res = await fetch(`/api/admin/user/${userId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        setUsers(users.filter(u => u.id !== userId))
        fetchData() // refresh stats
        alert("Usuário removido com sucesso!")
      } else {
        const errorData = await res.json()
        alert(errorData.detail || "Erro ao remover usuário.")
      }
    } catch (err) {
      alert("Erro ao remover usuário.")
    }
  }

  const handleGenerateInvite = async () => {
    setLoadingInvite(true)
    setInviteLink('')
    try {
      const res = await fetch('/api/admin/generate-invite', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const link = `${window.location.origin}/register?token=${data.invite_token}`
        setInviteLink(link)
        navigator.clipboard.writeText(link)
        alert("Link gerado e copiado para a área de transferência!")
      } else {
        alert("Erro ao gerar convite.")
      }
    } catch (err) {
      alert("Erro de conexão ao gerar convite.")
    } finally {
      setLoadingInvite(false)
    }
  }

  const handleToggleListening = async (key) => {
    const currentState = systemStatus[key];
    try {
      const res = await fetch('/api/admin/system/listening_toggle', {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ key, enabled: !currentState })
      })
      if (res.ok) {
        const data = await res.json()
        setSystemStatus(prev => ({ ...prev, [key]: data[key] }))
      } else {
        alert("Erro ao alterar chave de escuta.")
      }
    } catch (err) {
      alert("Erro de conexão ao alterar chave de escuta.")
    }
  }

  if (loading) {
    return <div className="p-8 text-zinc-400">Carregando painel de administração...</div>
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-4 rounded-xl flex items-center gap-3">
          <Shield size={24} />
          <div>
            <h3 className="font-bold">Acesso Bloqueado</h3>
            <p className="text-sm">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
          <div className="flex items-center justify-between mb-4 relative z-10">
            <h3 className="text-zinc-400 font-medium tracking-wide">Total de Contas</h3>
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Users size={20} className="text-purple-400" />
            </div>
          </div>
          <p className="text-4xl font-bold text-white relative z-10">{stats.total_users}</p>
        </div>

        <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
          <div className="flex items-center justify-between mb-4 relative z-10">
            <h3 className="text-zinc-400 font-medium tracking-wide">Assinantes Ativos</h3>
            <div className="p-2 bg-emerald-500/10 rounded-lg">
              <Activity size={20} className="text-emerald-400" />
            </div>
          </div>
          <p className="text-4xl font-bold text-white relative z-10">{stats.active_users}</p>
        </div>

        <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
          <div className="flex items-center justify-between mb-4 relative z-10">
            <h3 className="text-zinc-400 font-medium tracking-wide">Status de Escuta (WebSockets)</h3>
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <Activity size={20} className="text-blue-400" />
            </div>
          </div>
          
          <div className="space-y-4">
            {/* Solana Sniper */}
            <div className="relative z-10 flex items-center justify-between bg-black/20 p-3 rounded-xl border border-zinc-800/50">
              <div className="flex flex-col">
                <span className="text-sm text-zinc-300 font-semibold">Rede Solana</span>
                <span className={`text-xs font-bold ${systemStatus.solana_sniper_enabled ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {systemStatus.solana_sniper_enabled ? 'LIGADO' : 'HIBERNANDO'}
                </span>
              </div>
              <button
                onClick={() => handleToggleListening('solana_sniper_enabled')}
                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors ${
                  systemStatus.solana_sniper_enabled 
                    ? 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30' 
                    : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                }`}
              >
                {systemStatus.solana_sniper_enabled ? 'Desligar' : 'Ligar'}
              </button>
            </div>

            {/* Base Sniper */}
            <div className="relative z-10 flex items-center justify-between bg-black/20 p-3 rounded-xl border border-zinc-800/50">
              <div className="flex flex-col">
                <span className="text-sm text-zinc-300 font-semibold">Rede Base</span>
                <span className={`text-xs font-bold ${systemStatus.base_sniper_enabled ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {systemStatus.base_sniper_enabled ? 'LIGADO' : 'HIBERNANDO'}
                </span>
              </div>
              <button
                onClick={() => handleToggleListening('base_sniper_enabled')}
                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors ${
                  systemStatus.base_sniper_enabled 
                    ? 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30' 
                    : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                }`}
              >
                {systemStatus.base_sniper_enabled ? 'Desligar' : 'Ligar'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-2xl shadow-xl overflow-hidden">
        <div className="p-6 border-b border-zinc-800 flex justify-between items-center">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <Shield size={20} className="text-purple-400" />
            Gestão de Clientes
          </h3>
          
          <div className="flex items-center gap-3">
            {inviteLink && (
              <input 
                type="text" 
                readOnly 
                value={inviteLink} 
                className="bg-zinc-950 border border-zinc-700 text-zinc-300 text-xs rounded-lg px-3 py-2 w-64 focus:outline-none"
                onClick={(e) => {
                  e.target.select();
                  navigator.clipboard.writeText(inviteLink);
                  alert("Copiado!");
                }}
              />
            )}
            <button
              onClick={handleGenerateInvite}
              disabled={loadingInvite}
              className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold py-2 px-4 rounded-lg flex items-center gap-2 transition-colors"
            >
              {loadingInvite ? 'Gerando...' : 'Gerar Convite'}
            </button>
          </div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-zinc-950/50">
                <th className="p-4 text-xs font-semibold text-zinc-400 uppercase tracking-wider border-b border-zinc-800">ID</th>
                <th className="p-4 text-xs font-semibold text-zinc-400 uppercase tracking-wider border-b border-zinc-800">E-mail</th>
                <th className="p-4 text-xs font-semibold text-zinc-400 uppercase tracking-wider border-b border-zinc-800">Status</th>
                <th className="p-4 text-xs font-semibold text-zinc-400 uppercase tracking-wider border-b border-zinc-800">Expira em</th>
                <th className="p-4 text-xs font-semibold text-zinc-400 uppercase tracking-wider border-b border-zinc-800">Admin</th>
                <th className="p-4 text-xs font-semibold text-zinc-400 uppercase tracking-wider border-b border-zinc-800">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="p-4 text-sm font-mono text-zinc-500">#{user.id}</td>
                  <td className="p-4 text-sm text-zinc-200">{user.email}</td>
                  <td className="p-4">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                      user.is_active 
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                        : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                    }`}>
                      {user.is_active ? 'Ativo' : 'Bloqueado'}
                    </span>
                  </td>
                  <td className="p-4 text-sm font-mono text-zinc-400">
                    {user.subscription_expires ? new Date(user.subscription_expires + 'Z').toLocaleString('pt-BR') : 'Sem Assinatura'}
                  </td>
                  <td className="p-4">
                    {user.is_admin ? (
                      <span className="text-purple-400 border border-purple-500/30 bg-purple-500/10 px-2 py-1 rounded text-xs font-bold uppercase tracking-wider">
                        Master
                      </span>
                    ) : (
                      <span className="text-zinc-600">-</span>
                    )}
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleToggleStatus(user.id, user.is_active)}
                        className={`p-2 rounded-lg transition-colors border ${
                          user.is_active 
                            ? 'bg-zinc-800 hover:bg-rose-500/20 hover:border-rose-500/30 border-zinc-700 text-zinc-400 hover:text-rose-400' 
                            : 'bg-zinc-800 hover:bg-emerald-500/20 hover:border-emerald-500/30 border-zinc-700 text-zinc-400 hover:text-emerald-400'
                        }`}
                        title={user.is_active ? 'Bloquear Acesso' : 'Desbloquear Acesso'}
                      >
                        {user.is_active ? <Lock size={16} /> : <Unlock size={16} />}
                      </button>
                      
                      <button 
                        onClick={() => handleExtend(user.id)}
                        className="p-2 bg-zinc-800 hover:bg-blue-500/20 hover:border-blue-500/30 border border-zinc-700 rounded-lg text-zinc-400 hover:text-blue-400 transition-colors"
                        title="Estender Assinatura"
                      >
                        <CalendarPlus size={16} />
                      </button>

                      {!user.is_admin && (
                        <button 
                          onClick={() => handleDelete(user.id)}
                          className="p-2 bg-zinc-800 hover:bg-rose-500/20 hover:border-rose-500/30 border border-zinc-700 rounded-lg text-zinc-400 hover:text-rose-400 transition-colors"
                          title="Remover Usuário"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              
              {users.length === 0 && (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-zinc-500">
                    Nenhum usuário encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Danger Zone: Reset System */}
      <div className="bg-rose-950/20 border border-rose-500/20 rounded-2xl p-6 mt-8">
        <h3 className="text-rose-500 font-bold mb-2 flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>
          Zona de Perigo
        </h3>
        <p className="text-sm text-zinc-400 mb-6">
          Isso apagará o cofre de chaves, histórico de trades, todos os usuários e resetará completamente o banco de dados da aplicação. Esta ação é IRREVERSÍVEL.
        </p>
        <button
          onClick={async () => {
            if (!window.confirm("Tem certeza absoluta que deseja ZERAR todo o sistema? Esta ação é IRREVERSÍVEL.")) return;
            try {
              localStorage.clear();
              sessionStorage.clear();
              const response = await fetch('/api/admin/reset-system', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
              });
              if (response.ok) {
                alert("Sistema zerado com sucesso! A página será recarregada.");
                window.location.reload();
              } else {
                alert("Erro ao resetar o sistema pelo servidor.");
              }
            } catch (error) {
              console.error("Erro na requisição de reset:", error);
              alert("Falha de conexão ao tentar resetar.");
            }
          }}
          className="px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white font-bold rounded-lg transition-colors flex items-center gap-2"
        >
          🗑️ Zerar Tudo / Resetar Sistema
        </button>
      </div>
    </div>
  )
}
