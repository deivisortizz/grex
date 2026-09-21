import React, { createContext, useContext } from 'react'
import { useSniperWebSocket } from '../hooks/useSniperWebSocket'

const SniperContext = createContext(null)

// eslint-disable-next-line react-refresh/only-export-components
export function SniperProvider({ children }) {
  const sniperState = useSniperWebSocket()

  return (
    <SniperContext.Provider value={sniperState}>
      {children}
    </SniperContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSniperContext() {
  const context = useContext(SniperContext)
  if (!context) {
    throw new Error('useSniperContext must be used within a SniperProvider')
  }
  return context
}
