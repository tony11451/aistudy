import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AuthProvider, ToastProvider, useAuth } from './store'
import { Loading, BottomNav } from './ui'
import {
  IconBook,
  IconChat,
  IconHome,
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
import Mine from './pages/Mine'
import Settings from './pages/Settings'

const NAV = [
  { path: '/', icon: <IconHome size={22} />, label: '首页' },
  { path: '/mindmap', icon: <IconMap size={22} />, label: '图谱' },
  { path: '/wrong', icon: <IconBook size={22} />, label: '错题' },
  { path: '/chat', icon: <IconChat size={22} />, label: '对话' },
  { path: '/mine', icon: <IconUser size={22} />, label: '我的' },
]

const TAB_PATHS = ['/', '/mindmap', '/wrong', '/chat', '/mine']

function AppNav() {
  const { pathname } = useLocation()
  const nav = useNavigate()
  if (!TAB_PATHS.includes(pathname)) return null
  return (
    <div className="app-nav">
      <BottomNav
        items={NAV.map((n) => ({ value: n.path, label: n.label, icon: n.icon }))}
        value={pathname}
        onChange={(v) => nav(v)}
      />
    </div>
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
        <Route path="/mine" element={<Mine />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
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
