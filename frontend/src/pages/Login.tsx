import { FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Field } from '../components'
import { useAuth, useToast } from '../store'

export default function Login() {
  const nav = useNavigate()
  const toast = useToast()
  const { login, user } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [needSetup, setNeedSetup] = useState(false)

  useEffect(() => {
    api
      .get<{ need_setup: boolean }>('/api/auth/status')
      .then((r) => setNeedSetup(r.need_setup))
      .catch(() => {})
    if (user) nav('/')
  }, [user, nav])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await login(username, password)
      nav('/')
    } catch (err: any) {
      toast(err.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 480, margin: '0 auto', paddingTop: 48 }}>
      <div className="hero" style={{ marginBottom: 28 }}>
        <h2>欢迎回来</h2>
        <p>登录后继续你的高效备考之旅</p>
      </div>
      <form className="col" onSubmit={submit}>
        <Field label="用户名">
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="密码">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <button className="md-btn md-btn-filled md-btn-block" disabled={loading}>
          {loading ? '登录中…' : '登录'}
        </button>
        <button
          type="button"
          className="md-btn md-btn-outlined md-btn-block"
          onClick={() => nav('/register')}
        >
          注册新账号
        </button>
        {needSetup && (
          <button
            type="button"
            className="md-btn md-btn-text md-btn-block"
            onClick={() => nav('/setup')}
          >
            首次部署？初始化管理员
          </button>
        )}
        <p className="caption" style={{ textAlign: 'center', marginTop: 8 }}>
          本系统部署在局域网内，学生与家长可自由注册
        </p>
      </form>
    </div>
  )
}
