import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AuthProvider, ToastProvider, useAuth, useChatBadge, clearChatReady } from './store'
import { Btn, Field, Sheet } from './ui'
import { useState } from 'react'
import { Loading, BottomNav } from './ui'
import {
  IconBook,
  IconChat,
  IconHome,
  IconList,
  IconMap,
  IconUser,
} from './icons'
import Setup from './pages/Setup'
import Register from './pages/Register'
import Login from './pages/Login'
import Home from './pages/Home'
import Mindmap from './pages/Mindmap'
import Upload from './pages/Upload'
import WrongList from './pages/WrongList'
import WrongDetail from './pages/WrongDetail'
import ChatList from './pages/ChatList'
import ChatRoom from './pages/ChatRoom'
import Library from './pages/Library'
import BookDetail from './pages/BookDetail'
import Search from './pages/Search'
import Mine from './pages/Mine'
import Settings from './pages/Settings'

const NAV = [
  { path: '/', icon: <IconHome size={22} />, label: '首页' },
  { path: '/mindmap', icon: <IconMap size={22} />, label: '图谱' },
  { path: '/wrong', icon: <IconBook size={22} />, label: '错题' },
  { path: '/chat', icon: <IconChat size={22} />, label: '对话' },
  { path: '/library', icon: <IconList size={22} />, label: '档案' },
  { path: '/mine', icon: <IconUser size={22} />, label: '我的' },
]

const TAB_PATHS = ['/', '/mindmap', '/wrong', '/chat', '/library', '/mine']

function AppNav() {
  const { pathname } = useLocation()
  const nav = useNavigate()
  const chatReady = useChatBadge()
  if (!TAB_PATHS.includes(pathname)) return null
  return (
    <div className="app-nav">
      <BottomNav
        items={NAV.map((n) => ({
          value: n.path,
          label: n.label,
          icon: (
            <span style={{ position: 'relative', display: 'inline-flex' }}>
              {n.icon}
              {n.path === '/chat' && chatReady && (
                <span
                  style={{
                    position: 'absolute',
                    top: -2,
                    right: -4,
                    width: 9,
                    height: 9,
                    borderRadius: '50%',
                    background: 'var(--m3e-sys-color-error, #ba1a1a)',
                    boxShadow: '0 0 0 2px var(--m3e-sys-color-surface-container)',
                  }}
                />
              )}
            </span>
          ),
        }))}
        value={pathname}
        onChange={(v) => {
          if (v === '/chat') clearChatReady()
          nav(v)
        }}
      />
    </div>
  )
}



/** 全局 AI 浮球（需求 17）：任意页面唤起 AI，自动携带当前页面上下文 */
function pageLabel(pathname: string): string {
  if (pathname === '/') return '首页'
  if (pathname === '/mindmap') return '知识图谱'
  if (pathname === '/wrong') return '错题本'
  if (pathname === '/wrong/new') return '错题录入'
  if (pathname.startsWith('/wrong/')) return '错题详情'
  if (pathname === '/chat') return '对话列表'
  if (pathname.startsWith('/chat/')) return '对话'
  if (pathname === '/library') return '档案库'
  if (pathname.startsWith('/library/book/')) return '课本阅读'
  if (pathname === '/mine') return '我的'
  if (pathname === '/settings') return '设置'
  return '当前页面'
}

function GlobalAIBall() {
  const { pathname } = useLocation()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const label = pageLabel(pathname)
  if (pathname.startsWith('/chat/')) return null
  return (
    <>
      <button
        className="ai-ball"
        onClick={() => setOpen(true)}
        aria-label="问 AI"
      >
        ✦
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title={`问 AI · ${label}`}>
        <div className="col">
          <div className="caption">
            AI 会知道你在「{label}」并按需读取相关内容（图谱/错题/档案…）。
          </div>
          <Field label="想问什么" value={text} onChange={setText} multiline rows={3}
                 placeholder="例如：帮我分析这个知识点 / 总结我最近的弱点" />
          <Btn variant="filled" block onClick={() => {
            const prompt = text.trim() || `请结合我当前所在的「${label}」页面内容，帮我做一次分析并给出建议。`
            nav(`/chat?ctx=${encodeURIComponent(label)}&prompt=${encodeURIComponent(prompt)}`)
            setOpen(false)
            setText('')
          }}>
            发送给 AI
          </Btn>
          <div className="row-wrap">
            <Btn variant="tonal" sm onClick={() => {
              nav(`/chat?ctx=${encodeURIComponent(label)}&prompt=${encodeURIComponent('请读取我的图谱和档案，整理并精简我的弱点。')}`)
              setOpen(false)
            }}>
              整理弱点
            </Btn>
            <Btn variant="tonal" sm onClick={() => {
              nav(`/chat?ctx=${encodeURIComponent(label)}&prompt=${encodeURIComponent('请根据我的历史错题重新评估知识点掌握度并更新。')}`)
              setOpen(false)
            }}>
              按错题重评
            </Btn>
          </div>
        </div>
      </Sheet>
    </>
  )
}

function Guarded() {
  const { user, loading } = useAuth()
  const { pathname } = useLocation()
  const isAuthPage = ['/login', '/setup', '/register'].includes(pathname)
  if (loading) return <Loading text="正在进入…" />
  if (!user && !isAuthPage) return <Navigate to="/login" replace />
  return (
    <>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Home />} />
        <Route path="/mindmap" element={<Mindmap />} />
        <Route path="/wrong" element={<WrongList />} />
        <Route path="/wrong/new" element={<Upload />} />
        <Route path="/wrong/:id" element={<WrongDetail />} />
        <Route path="/chat" element={<ChatList />} />
        <Route path="/chat/:id" element={<ChatRoom />} />
        <Route path="/library" element={<Library />} />
        <Route path="/library/book/:id" element={<BookDetail />} />
        <Route path="/search" element={<Search />} />
        <Route path="/mine" element={<Mine />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <GlobalAIBall />
      <AppNav />
    </>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <HashRouter>
          <Guarded />
        </HashRouter>
      </AuthProvider>
    </ToastProvider>
  )
}
