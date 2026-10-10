import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { Snackbar } from '@language-lit/material3-expressive'
import { api, getToken, setToken } from './api'

export interface UserInfo {
  id: number
  username: string
  display_name: string
  role: string
  grade: string
  identity?: string
}

interface AuthCtx {
  user: UserInfo | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const Ctx = createContext<AuthCtx>(null as any)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    if (!getToken()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await api.get<UserInfo>('/api/auth/me')
      setUser(me)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const login = async (username: string, password: string) => {
    const res = await api.post<{ access_token: string; user: UserInfo }>('/api/auth/login', {
      username,
      password,
    })
    setToken(res.access_token)
    setUser(res.user)
  }

  const logout = () => {
    setToken('')
    setUser(null)
  }

  return <Ctx.Provider value={{ user, loading, login, logout, refresh }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

/** 消息提示（M3 Snackbar） */
const ToastCtx = createContext<(text: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null)
  const show = (text: string) => {
    const id = Date.now()
    setToast({ id, text })
    setTimeout(() => setToast((t) => (t && t.id === id ? null : t)), 3000)
  }
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <Snackbar
          open
          message={toast.text}
          onOpenChange={(o: boolean) => {
            if (!o) setToast(null)
          }}
          style={{ position: 'fixed', left: 16, right: 16, bottom: 24, zIndex: 300, maxWidth: 520, margin: '0 auto' }}
        />
      )}
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
