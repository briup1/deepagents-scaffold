import { createContext, useContext } from 'react'

export interface GenerativeUIContextValue {
  dispatch: (action: unknown) => void
}

export const GenerativeUIContext = createContext<GenerativeUIContextValue>({
  dispatch: () => {
    // no-op fallback
  },
})

export function useGenerativeUIDispatch(): GenerativeUIContextValue {
  return useContext(GenerativeUIContext)
}
