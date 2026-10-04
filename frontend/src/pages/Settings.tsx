import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Dialog, Field, Loading, TopBar } from '../components'
import { GRADES } from '../constants'
import { useAuth, useToast } from '../store'

export default function Settings() {
  const nav = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'personal' | 'global' | 'users'>(
    user?.role === 'admin' ? 'global' : 'personal',
  )
  const [dark, setDark] = useState(document.documentElement.dataset.theme === 'dark')

  // 全局设置表单
  const [g, setG] = useState<any>({})
  // 个人设置表单
  const [p, setP] = useState<any>({})
  // 用户管理
  const [users, setUsers] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', grade: '初一', display_name: '' })

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get<any>('/api/settings')
      setData(res)
      setG({
        api_base_url: res.global.api_base_url,
        api_key: '',
        chat_model: res.global.chat_model,
        vision_model: res.global.vision_model,
        temperature: res.global.temperature,
        system_extra_prompt: res.global.system_extra_prompt,
      })
      setP({
        api_base_url: res.personal.api_base_url,
        api_key: '',
        chat_model: res.personal.chat_model,
        vision_model: res.personal.vision_model,
        grade: res.personal.grade || user?.grade || '初一',
      })
      if (user?.role === 'admin') {
        setUsers(await api.get<any[]>('/api/auth/users'))
      }
    } catch (e: any) {
      toast(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const toggleTheme = () => {
    const next = dark ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    localStorage.setItem('st_theme', next)
    setDark(!dark)
  }

  const saveGlobal = async () => {
    await api.put('/api/settings/global', g)
    toast('全局 AI 配置已保存')
    load()
  }

  const savePersonal = async () => {
    await api.put('/api/settings/personal', p)
    toast('个人配置已保存')
    load()
  }

  const addUser = async () => {
    try {
      await api.post('/api/auth/users', newUser)
      toast('用户创建成功')
      setShowAdd(false)
      setNewUser({ username: '', password: '', grade: '初一', display_name: '' })
      load()
    } catch (e: any) {
      toast(e.message || '创建失败')
    }
  }

  if (loading) return <Loading />

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar title="设置" back={() => nav(-1)} />

      <div className="md-tabs" style={{ margin: '12px 0' }}>
        {user?.role === 'admin' && (
          <button
            className={`md-tab ${tab === 'global' ? 'active' : ''}`}
            onClick={() => setTab('global')}
          >
            🌐 全局 AI
          </button>
        )}
        <button
          className={`md-tab ${tab === 'personal' ? 'active' : ''}`}
          onClick={() => setTab('personal')}
        >
          👤 个人 AI
        </button>
        {user?.role === 'admin' && (
          <button
            className={`md-tab ${tab === 'users' ? 'active' : ''}`}
            onClick={() => setTab('users')}
          >
            👥 用户
          </button>
        )}
      </div>

      <div className="md-card row">
        <div style={{ flex: 1 }}>
          <div className="title-strong">深色模式</div>
          <div className="caption">Material You 跟随系统质感</div>
        </div>
        <button className="md-btn md-btn-tonal md-btn-sm" onClick={toggleTheme}>
          {dark ? '🌙 已开启' : '☀️ 未开启'}
        </button>
      </div>

      {tab === 'global' && (
        <div className="col" style={{ marginTop: 12 }}>
          <div className="md-card md-card-filled">
            <div className="title-strong">OpenAI 兼容接口</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              支持 DeepSeek / Kimi / 通义千问 / 智谱 / OpenRouter 等所有 OpenAI 兼容 API。
              填 Base URL（含 /v1）、API Key 和模型名即可；分析图片需配置支持视觉的模型。
            </p>
            {data?.effective?.api_base_url && (
              <div className="caption">
                当前生效：{data.effective.api_base_url} · {data.effective.chat_model || '未配置'}
                {data.effective.vision_model ? ` · 视觉 ${data.effective.vision_model}` : ''}
              </div>
            )}
          </div>
          <Field label="Base URL（如 https://api.deepseek.com/v1）">
            <input
              value={g.api_base_url}
              onChange={(e) => setG({ ...g, api_base_url: e.target.value })}
              placeholder="https://api.openai.com/v1"
            />
          </Field>
          <Field
            label={
              data?.global?.api_key_masked
                ? `API Key（已保存：${data.global.api_key_masked}，留空不改）`
                : 'API Key'
            }
          >
            <input
              type="password"
              value={g.api_key}
              onChange={(e) => setG({ ...g, api_key: e.target.value })}
              placeholder="sk-..."
            />
          </Field>
          <Field label="对话模型">
            <input
              value={g.chat_model}
              onChange={(e) => setG({ ...g, chat_model: e.target.value })}
              placeholder="如 deepseek-chat / kimi-k2-0905-preview"
            />
          </Field>
          <Field label="视觉模型（拍照识别用，留空则用对话模型）">
            <input
              value={g.vision_model}
              onChange={(e) => setG({ ...g, vision_model: e.target.value })}
              placeholder="如 glm-4v-plus / qwen-vl-max / gpt-4o-mini"
            />
          </Field>
          <Field label={`温度（越低越严谨）：${(g.temperature ?? 0.7).toFixed(2)}`}>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={g.temperature}
              onChange={(e) => setG({ ...g, temperature: parseFloat(e.target.value) })}
            />
          </Field>
          <Field label="全局附加提示词（可选，追加到系统提示词）">
            <textarea
              value={g.system_extra_prompt}
              onChange={(e) => setG({ ...g, system_extra_prompt: e.target.value })}
              placeholder="例如：请严格使用苏教版教材的术语…"
            />
          </Field>
          <button className="md-btn md-btn-filled md-btn-block" onClick={saveGlobal}>
            保存全局配置
          </button>
        </div>
      )}

      {tab === 'personal' && (
        <div className="col" style={{ marginTop: 12 }}>
          <div className="md-card md-card-filled">
            <div className="title-strong">个人覆盖配置</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              留空表示使用全局共享配置；填写后只对你自己生效（用自己的 API 额度）。
            </p>
          </div>
          <Field label="我的年级">
            <select value={p.grade} onChange={(e) => setP({ ...p, grade: e.target.value })}>
              {GRADES.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </Field>
          <Field label="Base URL（留空用全局）">
            <input
              value={p.api_base_url}
              onChange={(e) => setP({ ...p, api_base_url: e.target.value })}
              placeholder="留空 = 使用全局配置"
            />
          </Field>
          <Field
            label={
              data?.personal?.api_key_masked
                ? `API Key（已保存：${data.personal.api_key_masked}）`
                : 'API Key（留空用全局）'
            }
          >
            <input
              type="password"
              value={p.api_key}
              onChange={(e) => setP({ ...p, api_key: e.target.value })}
              placeholder="留空 = 使用全局配置"
            />
          </Field>
          <Field label="对话模型（留空用全局）">
            <input
              value={p.chat_model}
              onChange={(e) => setP({ ...p, chat_model: e.target.value })}
            />
          </Field>
          <Field label="视觉模型（留空用全局）">
            <input
              value={p.vision_model}
              onChange={(e) => setP({ ...p, vision_model: e.target.value })}
            />
          </Field>
          <button className="md-btn md-btn-filled md-btn-block" onClick={savePersonal}>
            保存个人配置
          </button>
        </div>
      )}

      {tab === 'users' && (
        <div className="col" style={{ marginTop: 12 }}>
          <button className="md-btn md-btn-filled" onClick={() => setShowAdd(true)}>
            ＋ 创建用户
          </button>
          {(users || []).map((u) => (
            <div key={u.id} className="md-card row">
              <div style={{ flex: 1 }}>
                <div className="title-strong">
                  {u.display_name || u.username}
                  {u.role === 'admin' && <span className="badge badge-primary" style={{ marginLeft: 8 }}>管理员</span>}
                  {!u.is_active && <span className="badge badge-weak" style={{ marginLeft: 8 }}>已停用</span>}
                </div>
                <div className="caption">
                  {u.username} · {u.grade}
                </div>
              </div>
              <button
                className="md-btn md-btn-tonal md-btn-sm"
                onClick={async () => {
                  await api.put(`/api/auth/users/${u.id}`, { is_active: !u.is_active })
                  load()
                }}
              >
                {u.is_active ? '停用' : '启用'}
              </button>
              <button
                className="md-btn md-btn-text md-btn-sm"
                onClick={async () => {
                  const pwd = prompt(`为 ${u.username} 设置新密码（至少 6 位）`)
                  if (!pwd) return
                  if (pwd.length < 6) return toast('密码至少 6 位')
                  await api.put(`/api/auth/users/${u.id}`, { password: pwd })
                  toast('密码已重置')
                }}
              >
                重置密码
              </button>
            </div>
          ))}
        </div>
      )}

      <Dialog open={showAdd} onClose={() => setShowAdd(false)} title="创建用户">
        <div className="col">
          <Field label="用户名">
            <input
              value={newUser.username}
              onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
            />
          </Field>
          <Field label="昵称（可选）">
            <input
              value={newUser.display_name}
              onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })}
            />
          </Field>
          <Field label="密码（至少 6 位）">
            <input
              type="password"
              value={newUser.password}
              onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
            />
          </Field>
          <Field label="年级">
            <select
              value={newUser.grade}
              onChange={(e) => setNewUser({ ...newUser, grade: e.target.value })}
            >
              {GRADES.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </Field>
          <div className="row">
            <button className="md-btn md-btn-text" onClick={() => setShowAdd(false)}>
              取消
            </button>
            <span className="spacer" />
            <button className="md-btn md-btn-filled" onClick={addUser}>
              创建
            </button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
