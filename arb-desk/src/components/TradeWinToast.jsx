import React, { useEffect, useState, useRef } from 'react';
import { PartyPopper, X } from 'lucide-react';

export default function TradeWinToast() {
  const [toast, setToast] = useState(null);
  const audioRef = useRef(null);

  useEffect(() => {
    // Pré-carrega o áudio
    audioRef.current = new Audio('https://assets.mixkit.co/active_storage/sfx/2000/2000-preview.mp3');
    audioRef.current.volume = 0.5;

    const handleWin = (e) => {
      const data = e.detail;
      const toastId = Date.now();
      setToast({
        id: toastId,
        profit: data.profit_sol,
        pnl_pct: data.pnl_pct,
        token: data.token_mint
      });

      // Toca o som de Cha-Ching!
      if (audioRef.current) {
        audioRef.current.currentTime = 0;
        audioRef.current.play().catch(err => console.error("Áudio bloqueado pelo navegador:", err));
      }

      // Auto fechar após 5 segundos
      setTimeout(() => {
        setToast(current => current?.id === toastId ? null : current);
      }, 5000);
    };

    window.addEventListener('trade_win', handleWin);
    return () => window.removeEventListener('trade_win', handleWin);
  }, []);

  if (!toast) return null;

  return (
    <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-top-10 fade-in duration-300">
      <div className="bg-gradient-to-r from-emerald-900/90 to-emerald-800/90 backdrop-blur-md border border-emerald-500/50 rounded-2xl p-4 shadow-2xl shadow-emerald-900/50 flex items-center gap-4 min-w-[320px]">
        
        <div className="bg-emerald-500/20 p-3 rounded-xl flex-shrink-0">
          <PartyPopper size={24} className="text-emerald-400" />
        </div>
        
        <div className="flex-1">
          <h4 className="text-emerald-400 font-black text-lg drop-shadow-sm">WIN DETECTADO! 🚀</h4>
          <div className="flex items-baseline gap-2 mt-0.5">
            <span className="text-white font-bold text-xl">+{toast.profit?.toFixed(5)} SOL</span>
            <span className="text-emerald-400 text-sm font-semibold">({toast.pnl_pct > 0 ? '+' : ''}{toast.pnl_pct?.toFixed(2)}%)</span>
          </div>
          <div className="text-emerald-200/70 text-xs font-mono mt-1 truncate max-w-[200px]">
            {toast.token}
          </div>
        </div>

        <button 
          onClick={() => setToast(null)}
          className="text-emerald-400 hover:text-white transition-colors p-1"
        >
          <X size={20} />
        </button>
      </div>
    </div>
  );
}
