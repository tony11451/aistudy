import { FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Btn, Field } from '../ui'
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
    // 兜底：已登录用户误入登录页（如历史返回），直接送回主界面
    if (user) nav('/', { replace: true })
  }, [user, nav])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await login(username, password)
      nav('/', { replace: true })
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
        <Field label="用户名" value={username} onChange={setUsername} required />
        <Field label="密码" value={password} onChange={setPassword} type="password" required />
        <Btn variant="filled" block type="submit" disabled={loading}>
          {loading ? '登录中…' : '登录'}
        </Btn>
        <Btn variant="outlined" block onClick={() => nav('/register')}>
          注册新账号
        </Btn>
        {needSetup && (
          <Btn variant="text" block onClick={() => nav('/setup')}>
            首次部署？初始化管理员
          </Btn>
        )}
        <p className="caption" style={{ textAlign: 'center', marginTop: 8 }}>
          本系统部署在局域网内，学生与家长可自由注册
        </p>
      </form>
    </div>
  )
}
