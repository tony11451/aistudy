import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { Btn, CardView, Field, SelectField, TopBar } from '../ui'
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
          <CardView
            key={key}
            variant={identity === key ? 'elevated' : 'outlined'}
            onClick={() => setIdentity(key)}
            style={{
              flex: 1,
              textAlign: 'center',
              outline: identity === key ? '2px solid var(--m3e-sys-color-primary)' : undefined,
            }}
          >
            <div style={{ fontSize: 26 }}>{label.split(' ')[0]}</div>
            <div className="title-strong" style={{ marginTop: 4 }}>{label.split(' ')[1]}</div>
            <div className="caption" style={{ marginTop: 2 }}>{desc}</div>
          </CardView>
        ))}
      </div>

      <form className="col" onSubmit={submit}>
        <Field label="用户名" value={username} onChange={setUsername} required />
        <Field label="密码（至少 6 位）" value={password} onChange={setPassword} type="password" required />
        <Field label="确认密码" value={password2} onChange={setPassword2} type="password" required />
        {identity === 'student' && (
          <SelectField label="年级" value={grade} options={GRADES} onChange={setGrade} />
        )}
        <Btn variant="filled" block type="submit" disabled={loading}>
          {loading ? '注册中…' : '注册'}
        </Btn>
        <Btn variant="text" block onClick={() => nav('/login')}>
          已有账号？去登录
        </Btn>
      </form>
    </div>
  )
}
