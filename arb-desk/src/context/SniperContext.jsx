import React, { createContext, useContext } from 'react'
import { useSniperWebSocket } from '../hooks/useSniperWebSocket'

const SniperContext = createContext(null)

export function SniperProvider({ children }) {
  const sniperState = useSniperWebSocket()

  return (
    <SniperContext.Provider value={sniperState}>
      {children}
    </SniperContext.Provider>
  )
}

export function useSniperContext() {
  const context = useContext(SniperContext)
  if (!context) {
    throw new Error('useSniperContext must be used within a SniperProvider')
  }
  return context
}
