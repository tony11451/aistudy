import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { Btn, Field, SelectField } from '../ui'
import { useAuth, useToast } from '../store'
import { GRADES } from '../constants'

export default function Setup() {
  const nav = useNavigate()
  const toast = useToast()
  const { refresh } = useAuth()
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
      const res = await api.post<{ access_token: string }>('/api/auth/setup', {
        username,
        password,
        display_name: username,
        grade,
      })
      setToken(res.access_token)
      await refresh()
      toast('管理员创建成功')
      nav('/settings')
    } catch (err: any) {
      toast(err.message || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 480, margin: '0 auto', paddingTop: 40 }}>
      <div className="hero" style={{ marginBottom: 24 }}>
        <h2>智学错题本</h2>
        <p>拍照解析错题 · 弱点图谱 · AI 第二大脑，陪伴你从初一到高三</p>
      </div>
      <div className="section-title">初始化 · 创建管理员</div>
      <form className="col" onSubmit={submit}>
        <Field label="用户名" value={username} onChange={setUsername} required />
        <Field label="密码（至少 6 位）" value={password} onChange={setPassword} type="password" required />
        <Field label="确认密码" value={password2} onChange={setPassword2} type="password" required />
        <SelectField label="年级" value={grade} options={GRADES} onChange={setGrade} />
        <Btn variant="filled" block type="submit" disabled={loading}>
          {loading ? '创建中…' : '创建并开始使用'}
        </Btn>
      </form>
    </div>
  )
}
