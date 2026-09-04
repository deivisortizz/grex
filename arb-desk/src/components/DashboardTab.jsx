import ExchangeCard from './ExchangeCard'

const INITIAL_EXCHANGES = [
  { name: 'Binance', initialBid: 5.2105, initialAsk: 5.2115 },
  { name: 'Bitget', initialBid: 5.2120, initialAsk: 5.2130 },
  { name: 'KuCoin', initialBid: 5.2090, initialAsk: 5.2100 },
  { name: 'Mercado Bitcoin', initialBid: 5.2200, initialAsk: 5.2250 },
  { name: 'Bitso', initialBid: 5.2150, initialAsk: 5.2180 },
]

export default function DashboardTab({ marketData }) {
  return (
    <>
      <div className="flex gap-4 items-center mb-8">
        {marketData.net_spread !== undefined && (
          <div className="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-400">
            Best Net Spread: <strong className={marketData.net_spread > 0 ? "text-emerald-400" : "text-rose-400"}>{marketData.net_spread.toFixed(2)}%</strong>
          </div>
        )}
        {marketData.best_route && marketData.best_route !== "N/A" && (
          <div className="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-400">
            Route: <strong className="text-white">{marketData.best_route}</strong>
          </div>
        )}
        <div className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded-md text-xs text-zinc-400 font-medium ml-auto">
          Paridade: <strong className="text-white">USDT/BRL</strong>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {INITIAL_EXCHANGES.map((ex) => {
          const key = ex.name.toLowerCase()
          const realData = marketData[key] // {bid, ask}
          
          return (
            <ExchangeCard 
              key={ex.name}
              name={ex.name}
              initialBid={ex.initialBid}
              initialAsk={ex.initialAsk}
              realBid={realData?.bid}
              realAsk={realData?.ask}
            />
          )
        })}
      </div>
    </>
  )
}
