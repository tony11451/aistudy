import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AuthProvider, ToastProvider, useAuth } from './store'
import { Loading } from './components'
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
  { path: '/', icon: '🏠', label: '首页' },
  { path: '/mindmap', icon: '🧠', label: '图谱' },
  { path: '/wrong', icon: '📝', label: '错题' },
  { path: '/chat', icon: '💬', label: '对话' },
  { path: '/mine', icon: '👤', label: '我的' },
]

/** 一级 Tab 页才显示底部导航；二级页（聊天室/详情/上传/设置）隐藏，
 *  避免 fixed 导航栏遮挡聊天输入框等底部控件 */
const TAB_PATHS = ['/', '/mindmap', '/wrong', '/chat', '/mine']

function BottomNav() {
  const { pathname } = useLocation()
  const nav = useNavigate()
  const isTabPage = TAB_PATHS.includes(pathname)
  if (!isTabPage) return null
  return (
    <nav className="md-bottomnav">
      {NAV.map((item) => {
        const active = item.path === pathname
        return (
          <button
            key={item.path}
            className={`md-navitem ${active ? 'active' : ''}`}
            onClick={() => nav(item.path)}
          >
            <span className="md-navicon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        )
      })}
    </nav>
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
      <BottomNav />
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
