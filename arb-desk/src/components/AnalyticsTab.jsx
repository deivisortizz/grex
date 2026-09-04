import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { DollarSign } from 'lucide-react'

export default function AnalyticsTab({ chartData, targetSpread, history }) {
  // Analytics and P&L Cumulative Calculation using reduce
  const totalPnL = history.reduce((acc, curr) => acc + (curr.lucro_liquido || 0), 0)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 flex items-center justify-between shadow-lg">
          <div>
            <h3 className="text-zinc-400 text-sm font-medium mb-1">P&L Cumulativo (Lucro Total)</h3>
            <div className="text-3xl font-mono font-bold text-emerald-400">
              R$ {totalPnL.toFixed(2)}
            </div>
          </div>
          <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
            <DollarSign className="text-emerald-500" size={24} />
          </div>
        </div>
        
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 flex items-center justify-between shadow-lg">
          <div>
            <h3 className="text-zinc-400 text-sm font-medium mb-1">Total de Trades</h3>
            <div className="text-3xl font-mono font-bold text-white">
              {history.length}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 shadow-lg">
        <h3 className="text-lg font-bold text-white mb-6">Dispersão de Spread Líquido (Live)</h3>
        {chartData.length === 0 ? (
          <div className="text-zinc-500 py-10 text-center">Aguardando dados da engine HFT...</div>
        ) : (
          <div className="h-96 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="time" stroke="#71717a" fontSize={12} tickMargin={10} />
                <YAxis stroke="#71717a" fontSize={12} domain={['auto', 'auto']} tickFormatter={val => `${val}%`} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#fff' }}
                  itemStyle={{ color: '#34d399' }}
                />
                <ReferenceLine y={targetSpread} stroke="#f43f5e" strokeDasharray="3 3" label={{ position: 'top', value: 'Gatilho de Execução', fill: '#f43f5e', fontSize: 12 }} />
                <Line type="monotone" dataKey="net" stroke="#34d399" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
