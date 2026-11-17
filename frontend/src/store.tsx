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
  widgets?: string[]
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

/** 对话生成完毕小红点（后台流完成时通知；进入对话页清除） */
let chatReadyFlag = false
const chatReadyListeners = new Set<(v: boolean) => void>()

export function notifyChatReady() {
  chatReadyFlag = true
  chatReadyListeners.forEach((fn) => fn(true))
}

export function clearChatReady() {
  if (!chatReadyFlag) return
  chatReadyFlag = false
  chatReadyListeners.forEach((fn) => fn(false))
}

export function useChatBadge() {
  const [ready, setReady] = useState(chatReadyFlag)
  useEffect(() => {
    chatReadyListeners.add(setReady)
    return () => {
      chatReadyListeners.delete(setReady)
    }
  }, [])
  return ready
}

/** 用户学科列表（隐藏学科生效的唯一来源），带全局缓存 */
let subjectsCache: string[] | null = null
const subjectsListeners = new Set<(s: string[]) => void>()

export async function refreshSubjects(): Promise<string[]> {
  try {
    const s = await api.get<any>('/api/settings')
    subjectsCache = s.subjects || []
  } catch {
    subjectsCache = subjectsCache || []
  }
  subjectsListeners.forEach((fn) => fn(subjectsCache!))
  return subjectsCache!
}

export function useSubjects(): string[] {
  const [subjects, setSubjects] = useState<string[]>(subjectsCache || [])
  useEffect(() => {
    if (!subjectsCache) refreshSubjects()
    else setSubjects(subjectsCache)
    subjectsListeners.add(setSubjects)
    return () => {
      subjectsListeners.delete(setSubjects)
    }
  }, [])
  return subjects
}
