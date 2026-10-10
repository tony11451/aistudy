import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, ChipFilter, ChipRow, DialogBox, Field, Loading, SelectField, TabsBar, TopBar, IconBtn } from '../ui'
import { GRADES, SUBJECTS } from '../constants'
import { useAuth, useToast } from '../store'
import { useThemeMode } from '../ui'
import { IconClose, IconPlus } from '../icons'

type Tab = 'personal' | 'global' | 'users' | 'subjects' | 'models'

export default function Settings() {
  const nav = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const { mode: themeMode, setMode: setThemeMode } = useThemeMode()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>(user?.role === 'admin' ? 'global' : 'personal')
  const [g, setG] = useState<any>({})
  const [p, setP] = useState<any>({})
  const [users, setUsers] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', grade: '初一', display_name: '' })
  // 学科管理
  const [subjects, setSubjects] = useState<string[]>([...SUBJECTS])
  const [customSubject, setCustomSubject] = useState('')
  // 模型管理
  const [modelList, setModelList] = useState<string[]>([])
  const [newModel, setNewModel] = useState('')
  const [assign, setAssign] = useState<any>({ chat: '', vision: '', analysis: '' })

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get<any>('/api/settings')
      setData(res)
      setG({
        api_base_url: res.global?.api_base_url || '',
        api_key: '',
        chat_model: res.global?.chat_model || '',
        vision_model: res.global?.vision_model || '',
        temperature: res.global?.temperature ?? 0.7,
        system_extra_prompt: res.global?.system_extra_prompt || '',
      })
      setP({
        api_base_url: res.personal?.api_base_url || '',
        api_key: '',
        chat_model: res.personal?.chat_model || '',
        vision_model: res.personal?.vision_model || '',
        grade: res.personal?.grade || user?.grade || '初一',
      })
      setModelList(res.models || [])
      setAssign(
        res.assign || {
          chat: res.global?.chat_model || '',
          vision: res.global?.vision_model || '',
          analysis: res.global?.chat_model || '',
        },
      )
      setSubjects(res.subjects || [...SUBJECTS])
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const saveModels = async () => {
    await api.put('/api/settings/models', { models: modelList, assign })
    toast('模型配置已保存')
    load()
  }

  const saveSubjects = async () => {
    await api.put('/api/settings/subjects', { subjects })
    toast('学科列表已保存')
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

      <TabsBar<Tab>
        tabs={[
          ...(user?.role === 'admin' ? [{ value: 'global' as Tab, label: 'AI 接口' }] : []),
          { value: 'personal' as Tab, label: '个人' },
          { value: 'models' as Tab, label: '模型' },
          { value: 'subjects' as Tab, label: '学科' },
          ...(user?.role === 'admin' ? [{ value: 'users' as Tab, label: '用户' }] : []),
        ]}
        value={tab}
        onChange={setTab}
      />

      <CardView variant="filled" style={{ marginTop: 12 }}>
        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="title-strong">外观</div>
            <div className="caption">Material You 跟随系统质感</div>
          </div>
          <ChipRow>
            {(['light', 'dark', 'system'] as const).map((m) => (
              <ChipFilter
                key={m}
                label={m === 'light' ? '浅色' : m === 'dark' ? '深色' : '跟随系统'}
                selected={themeMode === m}
                onClick={() => setThemeMode(m)}
              />
            ))}
          </ChipRow>
        </div>
      </CardView>

      {tab === 'global' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">OpenAI 兼容接口</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              支持 DeepSeek / Kimi / 通义千问 / 智谱 / OpenRouter 等。填 Base URL（含 /v1）、API Key 和模型名。
            </p>
          </CardView>
          <Field label="Base URL（如 https://api.deepseek.com/v1）" value={g.api_base_url} onChange={(v) => setG({ ...g, api_base_url: v })} placeholder="https://api.openai.com/v1" />
          <Field
            label={data?.global?.api_key_masked ? `API Key（已保存：${data.global.api_key_masked}，留空不改）` : 'API Key'}
            value={g.api_key}
            onChange={(v) => setG({ ...g, api_key: v })}
            type="password"
            placeholder="sk-..."
          />
          <Field label="对话模型" value={g.chat_model} onChange={(v) => setG({ ...g, chat_model: v })} placeholder="deepseek-chat" />
          <Field label="视觉模型（拍照识别用）" value={g.vision_model} onChange={(v) => setG({ ...g, vision_model: v })} placeholder="glm-4v-plus" />
          <Field label={`温度：${(g.temperature ?? 0.7).toFixed(2)}`} value={String(g.temperature ?? 0.7)} onChange={(v) => setG({ ...g, temperature: parseFloat(v) || 0.7 })} />
          <Field label="全局附加提示词（可选）" value={g.system_extra_prompt} onChange={(v) => setG({ ...g, system_extra_prompt: v })} multiline />
          <Btn variant="filled" block onClick={saveGlobal}>保存全局配置</Btn>
        </div>
      )}

      {tab === 'personal' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">个人覆盖配置</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              留空表示使用全局共享配置；填写后只对你自己生效（用自己的 API 额度）。
            </p>
          </CardView>
          <SelectField label="我的年级" value={p.grade} options={GRADES} onChange={(v) => setP({ ...p, grade: v })} />
          <Field label="Base URL（留空用全局）" value={p.api_base_url} onChange={(v) => setP({ ...p, api_base_url: v })} />
          <Field
            label={data?.personal?.api_key_masked ? `API Key（已保存：${data.personal.api_key_masked}）` : 'API Key（留空用全局）'}
            value={p.api_key}
            onChange={(v) => setP({ ...p, api_key: v })}
            type="password"
          />
          <Field label="对话模型（留空用全局）" value={p.chat_model} onChange={(v) => setP({ ...p, chat_model: v })} />
          <Field label="视觉模型（留空用全局）" value={p.vision_model} onChange={(v) => setP({ ...p, vision_model: v })} />
          <Btn variant="filled" block onClick={savePersonal}>保存个人配置</Btn>
        </div>
      )}

      {tab === 'models' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">模型管理</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              添加多个模型名称，然后为不同用途指派；对话页还可以在会话内临时切换。
            </p>
          </CardView>

          <div className="row-wrap">
            {modelList.map((m) => (
              <span key={m} className="badge badge-primary" style={{ minHeight: 34 }}>
                {m}
                <button
                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'inherit', marginLeft: 4 }}
                  onClick={() => setModelList(modelList.filter((x) => x !== m))}
                >
                  <IconClose size={13} />
                </button>
              </span>
            ))}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <div style={{ flex: 1 }}>
              <Field label="添加模型名" value={newModel} onChange={setNewModel} placeholder="如 kimi-k2-0905-preview" />
            </div>
            <Btn
              variant="tonal"
              onClick={() => {
                const name = newModel.trim()
                if (name && !modelList.includes(name)) setModelList([...modelList, name])
                setNewModel('')
              }}
            >
              <IconPlus size={16} /> 添加
            </Btn>
          </div>

          <div className="divider" />
          <div className="title-strong">用途指派</div>
          <SelectField label="对话 / 日常问答" value={assign.chat} options={['', ...modelList]} onChange={(v) => setAssign({ ...assign, chat: v })} />
          <SelectField label="识图 / 错题分析" value={assign.vision} options={['', ...modelList]} onChange={(v) => setAssign({ ...assign, vision: v })} />
          <SelectField label="总结 / 报告" value={assign.analysis} options={['', ...modelList]} onChange={(v) => setAssign({ ...assign, analysis: v })} />

          <Btn variant="filled" block onClick={saveModels}>保存模型配置</Btn>
        </div>
      )}

      {tab === 'subjects' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">学科管理</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              点击学科可隐藏/恢复（例如初三没有地理、生物）。隐藏后错题录入和图谱中不再显示。
            </p>
          </CardView>
          <ChipRow>
            {SUBJECTS.map((s) => (
              <ChipFilter
                key={s}
                label={subjects.includes(s) ? `✓ ${s}` : `${s}（已隐藏）`}
                selected={subjects.includes(s)}
                onClick={() =>
                  setSubjects(
                    subjects.includes(s) ? subjects.filter((x) => x !== s) : [...subjects, s],
                  )
                }
              />
            ))}
          </ChipRow>
          <div className="row" style={{ gap: 8 }}>
            <div style={{ flex: 1 }}>
              <Field label="添加自定义学科" value={customSubject} onChange={setCustomSubject} placeholder="如 综合实践" />
            </div>
            <Btn
              variant="tonal"
              onClick={() => {
                const name = customSubject.trim()
                if (name && !subjects.includes(name)) setSubjects([...subjects, name])
                setCustomSubject('')
              }}
            >
              <IconPlus size={16} /> 添加
            </Btn>
          </div>
          <Btn variant="filled" block onClick={saveSubjects}>保存学科列表</Btn>
        </div>
      )}

      {tab === 'users' && (
        <div className="col" style={{ marginTop: 12 }}>
          <Btn variant="filled" onClick={() => setShowAdd(true)}>
            <IconPlus size={16} /> 创建用户
          </Btn>
          {(users || []).map((u) => (
            <CardView key={u.id} variant="filled">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <div className="title-strong">
                    {u.display_name || u.username}
                    {u.role === 'admin' && <Badge>管理员</Badge>}
                    {!u.is_active && <Badge>已停用</Badge>}
                  </div>
                  <div className="caption">
                    {u.username} · {u.grade || '—'}
                  </div>
                </div>
                <Btn
                  variant="tonal"
                  sm
                  onClick={async () => {
                    await api.put(`/api/auth/users/${u.id}`, { is_active: !u.is_active })
                    load()
                  }}
                >
                  {u.is_active ? '停用' : '启用'}
                </Btn>
                <Btn
                  variant="text"
                  sm
                  onClick={async () => {
                    const pwd = prompt(`为 ${u.username} 设置新密码（至少 6 位）`)
                    if (!pwd) return
                    if (pwd.length < 6) return toast('密码至少 6 位')
                    await api.put(`/api/auth/users/${u.id}`, { password: pwd })
                    toast('密码已重置')
                  }}
                >
                  重置密码
                </Btn>
              </div>
            </CardView>
          ))}
        </div>
      )}

      <DialogBox open={showAdd} onClose={() => setShowAdd(false)} title="创建用户">
        <div className="col">
          <Field label="用户名" value={newUser.username} onChange={(v) => setNewUser({ ...newUser, username: v })} />
          <Field label="昵称（可选）" value={newUser.display_name} onChange={(v) => setNewUser({ ...newUser, display_name: v })} />
          <Field label="密码（至少 6 位）" value={newUser.password} onChange={(v) => setNewUser({ ...newUser, password: v })} type="password" />
          <SelectField label="年级" value={newUser.grade} options={GRADES} onChange={(v) => setNewUser({ ...newUser, grade: v })} />
          <div className="row">
            <Btn variant="text" onClick={() => setShowAdd(false)}>取消</Btn>
            <span className="spacer" />
            <Btn variant="filled" onClick={addUser}>创建</Btn>
          </div>
        </div>
      </DialogBox>
    </div>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="badge badge-primary" style={{ marginLeft: 8 }}>
      {children}
    </span>
  )
}
