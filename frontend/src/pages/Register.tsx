import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { Field, TopBar } from '../components'
import { GRADES } from '../constants'
import { useAuth, useToast } from '../store'

export default function Register() {
  const nav = useNavigate()
  const toast = useToast()
  const { refresh } = useAuth()
  const [identity, setIdentity] = useState<'student' | 'parent'>('student')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [grade, setGrade] = useState('初一')
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (password !== password2) return toast('两次密码不一致')
    setLoading(true)
    try {
      const res = await api.post<{ access_token: string }>('/api/auth/register', {
        username,
        password,
        display_name: username,
        grade: identity === 'student' ? grade : '',
        role: identity,
      })
      setToken(res.access_token)
      await refresh()
      toast('注册成功，欢迎加入！')
      nav('/')
    } catch (err: any) {
      toast(err.message || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 480, margin: '0 auto', paddingTop: 0 }}>
      <TopBar title="创建账号" back={() => nav('/login')} />

      <div className="caption" style={{ margin: '16px 2px 8px' }}>我是</div>
      <div className="row" style={{ gap: 10, marginBottom: 8 }}>
        {(
          [
            ['student', '🎓 学生', '记录错题、追踪进度'],
            ['parent', '👪 家长', '了解孩子的学习情况'],
          ] as ['student' | 'parent', string, string][]
        ).map(([key, label, desc]) => (
          <button
            key={key}
            className={`md-card ${identity === key ? 'md-card-filled' : 'md-card-outlined'} md-card-tappable`}
            style={{
              flex: 1,
              textAlign: 'center',
              borderColor: identity === key ? 'var(--md-primary)' : undefined,
              borderWidth: identity === key ? 2 : 1,
            }}
            onClick={() => setIdentity(key)}
          >
            <div style={{ fontSize: 26 }}>{label.split(' ')[0]}</div>
            <div className="title-strong" style={{ marginTop: 4 }}>{label.split(' ')[1]}</div>
            <div className="caption" style={{ marginTop: 2 }}>{desc}</div>
          </button>
        ))}
      </div>

      <form className="col" onSubmit={submit}>
        <Field label="用户名">
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="密码（至少 6 位）">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <Field label="确认密码">
          <input
            type="password"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            required
          />
        </Field>
        {identity === 'student' && (
          <Field label="年级">
            <select value={grade} onChange={(e) => setGrade(e.target.value)}>
              {GRADES.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </Field>
        )}
        <button className="md-btn md-btn-filled md-btn-block" disabled={loading}>
          {loading ? '注册中…' : '注册'}
        </button>
        <button type="button" className="md-btn md-btn-text md-btn-block" onClick={() => nav('/login')}>
          已有账号？去登录
        </button>
      </form>
    </div>
  )
}
