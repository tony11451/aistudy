import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import {
  Dialog,
  Empty,
  Loading,
  Markdown,
  MASTERY_LABEL,
  STATE_LABEL,
  useAsync,
} from '../components'
import { SUBJECTS } from '../constants'
import { useAuth, useToast } from '../store'

type Tab = 'profile' | 'progress' | 'methods' | 'goals' | 'reports'

export default function Mine() {
  const nav = useNavigate()
  const toast = useToast()
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('progress')

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14 }}>
        <div
          style={{
            width: 54,
            height: 54,
            borderRadius: 'var(--md-shape-lg)',
            background: 'var(--md-primary)',
            color: 'var(--md-on-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 24,
            fontWeight: 700,
          }}
        >
          {(user?.display_name || '同')[0]}
        </div>
        <div style={{ flex: 1 }}>
          <div className="title-strong">{user?.display_name}</div>
          <div className="caption">
            {user?.grade || '—'} · {user?.identity || (user?.role === 'admin' ? '管理员' : '学生')}
          </div>
        </div>
        <button className="md-iconbtn" onClick={() => nav('/settings')} title="设置">
          ⚙️
        </button>
        <button
          className="md-iconbtn"
          onClick={() => {
            logout()
            nav('/login')
          }}
          title="退出"
        >
          🚪
        </button>
      </div>

      <div className="md-tabs" style={{ marginBottom: 14 }}>
        {(
          [
            ['progress', '进度看板'],
            ['profile', '学习档案'],
            ['methods', '方法库'],
            ['goals', '刷题目标'],
            ['reports', '报告'],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={`md-tab ${tab === key ? 'active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'progress' && <ProgressTab />}
      {tab === 'profile' && <ProfileTab />}
      {tab === 'methods' && <MethodsTab />}
      {tab === 'goals' && <GoalsTab />}
      {tab === 'reports' && <ReportsTab />}
    </div>
  )
}

function ProgressTab() {
  const nav = useNavigate()
  const { data, loading, reload } = useAsync(
    () => api.get<Record<string, any>>('/api/knowledge/progress'),
    [],
  )
  if (loading) return <Loading />
  const entries = Object.entries(data || {})
  const totalWeak = entries.reduce((n, [, d]: any) => n + (d.weak?.length || 0), 0)

  return (
    <div className="col">
      <div className="hero" style={{ padding: 18 }}>
        <h2 style={{ fontSize: '1.35rem' }}>学习进度总览</h2>
        <p>
          薄弱知识点 <strong>{totalWeak}</strong> 个 · 覆盖 {entries.length} 个学科。
          掌握度由 AI 根据错题与对话自动更新。
        </p>
      </div>
      {!entries.length && (
        <Empty
          icon="🔭"
          title="还没有进度数据"
          desc="上传作业让 AI 识别你正在学什么，或录入错题开始积累"
          action={
            <button className="md-btn md-btn-filled" onClick={() => nav('/wrong/new')}>
              去录入
            </button>
          }
        />
      )}
      {entries.map(([subject, d]: any) => {
        const total = d.total || 1
        return (
          <div key={subject} className="md-card">
            <div className="row">
              <div className="title-strong">{subject}</div>
              <span className="spacer" />
              <button
                className="md-btn md-btn-text md-btn-sm"
                onClick={() => nav(`/mindmap`)}
              >
                图谱 →
              </button>
            </div>
            <div className="row" style={{ gap: 8, margin: '10px 0', height: 10 }}>
              {(
                [
                  ['weak', 'var(--md-mastery-weak)'],
                  ['improving', 'var(--md-mastery-improving)'],
                  ['mastered', 'var(--md-mastery-mastered)'],
                  ['unknown', 'var(--md-mastery-unknown)'],
                ] as const
              ).map(([k, color]) =>
                (d[k]?.length || 0) > 0 ? (
                  <div
                    key={k}
                    style={{
                      width: `${((d[k].length / total) * 100).toFixed(1)}%`,
                      background: color,
                      borderRadius: 999,
                      height: '100%',
                    }}
                  />
                ) : null,
              )}
            </div>
            <div className="row-wrap">
              {['weak', 'improving', 'mastered'].map((k) =>
                (d[k] || []).slice(0, 4).map((kp: string) => (
                  <span key={k + kp} className={`badge badge-${k === 'unknown' ? '' : k}`}>
                    <span className={`mastery-dot mastery-${k}`} />
                    {kp}
                  </span>
                )),
              )}
            </div>
            <div className="caption" style={{ marginTop: 8 }}>
              学习中 {d.learning || 0} · 已学完 {d.learned || 0} · 未接触 {d.not_started || 0}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ProfileTab() {
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => api.get<any[]>('/api/profile'), [])
  const [editSubject, setEditSubject] = useState('')
  const [editText, setEditText] = useState('')
  const [busy, setBusy] = useState('')

  const save = async () => {
    await api.post('/api/profile', { subject: editSubject, content: editText })
    setEditSubject('')
    toast('档案已保存')
    reload()
  }

  const refreshAI = async (subject: string) => {
    setBusy(subject)
    try {
      await api.post('/api/profile/refresh', { subject })
      toast(`${subject} 档案已由 AI 更新`)
      reload()
    } catch (e: any) {
      toast(e.message || '更新失败')
    } finally {
      setBusy('')
    }
  }

  if (loading) return <Loading />
  return (
    <div className="col">
      <div className="md-card md-card-filled">
        <div className="title-strong">🧠 AI 第二大脑</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          学习档案记录你的薄弱点、常错类型与学习建议（不含原题），每次错题分析后 AI
          会自动增量更新，对话时 AI 会带着这些记忆了解你。
        </p>
      </div>
      {(data || []).map((p) => (
        <div key={p.subject} className="md-card">
          <div className="row">
            <div className="title-strong">{p.subject}</div>
            <span className="caption">{(p.updated_at || '').slice(0, 10)}</span>
            <span className="spacer" />
            <button
              className="md-btn md-btn-tonal md-btn-sm"
              disabled={busy === p.subject}
              onClick={() => refreshAI(p.subject)}
            >
              {busy === p.subject ? 'AI 更新中…' : 'AI 更新'}
            </button>
            <button
              className="md-btn md-btn-text md-btn-sm"
              onClick={() => {
                setEditSubject(p.subject)
                setEditText(p.content)
              }}
            >
              编辑
            </button>
          </div>
          <Markdown text={p.content} />
        </div>
      ))}
      {!data?.length && (
        <Empty
          icon="🧠"
          title="还没有学习档案"
          desc="录入几道错题后，AI 会自动为你建立档案"
          action={
            <button
              className="md-btn md-btn-filled"
              onClick={() => {
                setEditSubject(SUBJECTS[1])
                setEditText('')
              }}
            >
              手动新建档案
            </button>
          }
        />
      )}
      <Dialog open={!!editSubject} onClose={() => setEditSubject('')} title={`编辑 ${editSubject} 档案`}>
        <textarea
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          style={{
            width: '100%',
            minHeight: 180,
            padding: 12,
            borderRadius: 'var(--md-shape-md)',
            border: '1.5px solid var(--md-outline-variant)',
            background: 'var(--md-surface)',
            outline: 'none',
          }}
        />
        <div className="row" style={{ marginTop: 14 }}>
          <button className="md-btn md-btn-text" onClick={() => setEditSubject('')}>
            取消
          </button>
          <span className="spacer" />
          <button className="md-btn md-btn-filled" onClick={save}>
            保存
          </button>
        </div>
      </Dialog>
    </div>
  )
}

function MethodsTab() {
  const [subject, setSubject] = useState('')
  const { data, loading, reload } = useAsync(
    () => api.get<any[]>(`/api/methods${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`),
    [subject],
  )
  const toast = useToast()
  const [ask, setAsk] = useState('')
  const [askSubject, setAskSubject] = useState('道德与法治')
  const [busy, setBusy] = useState(false)

  const summarize = async () => {
    if (!ask.trim()) return toast('请粘贴题目')
    setBusy(true)
    try {
      await api.post('/api/methods/summarize', {
        subject: askSubject,
        question: ask,
        ask: '请总结这道题的具体方法和通用答题方法',
      })
      toast('方法已总结并入库')
      setAsk('')
      reload()
    } catch (e: any) {
      toast(e.message || '总结失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="col">
      <div className="md-card md-card-filled">
        <div className="title-strong">🧭 答题方法库</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          AI 结合你的题目总结「具体方法 + 通用方法」（尤其政治、历史、地理等文科主观题），
          错题分析时也会自动积累。
        </p>
        <textarea
          value={ask}
          onChange={(e) => setAsk(e.target.value)}
          placeholder="粘贴一道文科题，让 AI 总结答题方法…"
          style={{
            width: '100%',
            minHeight: 90,
            marginTop: 10,
            padding: 12,
            borderRadius: 'var(--md-shape-md)',
            border: '1.5px solid var(--md-outline-variant)',
            background: 'var(--md-surface)',
            outline: 'none',
          }}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <select
            value={askSubject}
            onChange={(e) => setAskSubject(e.target.value)}
            style={{
              minHeight: 40,
              padding: '0 12px',
              borderRadius: 'var(--md-shape-full)',
              border: '1.5px solid var(--md-outline-variant)',
              background: 'var(--md-surface)',
            }}
          >
            {SUBJECTS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <span className="spacer" />
          <button className="md-btn md-btn-filled md-btn-sm" disabled={busy} onClick={summarize}>
            {busy ? 'AI 总结中…' : 'AI 总结方法'}
          </button>
        </div>
      </div>

      <div className="md-chip-row">
        {SUBJECTS.map((s) => (
          <button
            key={s}
            className={`md-chip ${subject === s ? 'active' : ''}`}
            onClick={() => setSubject(subject === s ? '' : s)}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty icon="🧭" title="方法库还是空的" desc="分析文科错题或手动总结，方法会自动归档到这里" />
      )}
      {(data || []).map((m) => (
        <div key={m.id} className="md-card">
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            <span className="badge badge-primary">{m.subject}</span>
            {m.knowledge_point && <span className="badge">{m.knowledge_point}</span>}
            {m.question_type && <span className="badge">{m.question_type}</span>}
            <span className="spacer" />
            <button
              className="md-iconbtn"
              onClick={async () => {
                if (!confirm('删除这条方法？')) return
                await api.del(`/api/methods/${m.id}`)
                reload()
              }}
            >
              ×
            </button>
          </div>
          {m.specific_method && (
            <div style={{ marginTop: 8 }}>
              <div className="caption">具体方法</div>
              <Markdown text={m.specific_method} />
            </div>
          )}
          {m.general_method && (
            <div style={{ marginTop: 8 }}>
              <div className="caption">通用方法</div>
              <Markdown text={m.general_method} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function GoalsTab() {
  const toast = useToast()
  const [status, setStatus] = useState('active')
  const { data, loading, reload } = useAsync(
    () => api.get<any[]>(`/api/goals?status=${status}`),
    [status],
  )
  const [busy, setBusy] = useState(false)

  const generate = async () => {
    setBusy(true)
    try {
      const res = await api.post<{ items: any[] }>('/api/goals/generate', {})
      toast(`AI 已生成 ${res.items.length} 个刷题目标`)
      setStatus('active')
      reload()
    } catch (e: any) {
      toast(e.message || '生成失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="col">
      <div className="md-card md-card-filled">
        <div className="title-strong">🎯 刷题目标</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          不做题海战术 —— AI 根据你的弱点给出「专攻哪一类题」的目标方向、题量建议和验收标准。
        </p>
        <button
          className="md-btn md-btn-filled md-btn-block"
          style={{ marginTop: 10 }}
          disabled={busy}
          onClick={generate}
        >
          {busy ? 'AI 规划中…' : '✨ 让 AI 帮我定目标'}
        </button>
      </div>

      <div className="md-chip-row">
        {[
          ['active', '进行中'],
          ['done', '已完成'],
          ['archived', '已归档'],
          ['', '全部'],
        ].map(([v, label]) => (
          <button
            key={v}
            className={`md-chip ${status === v ? 'active' : ''}`}
            onClick={() => setStatus(v)}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty icon="🎯" title="还没有刷题目标" desc="点上方按钮，让 AI 按你的弱点规划刷题方向" />
      )}
      {(data || []).map((g) => (
        <div key={g.id} className="md-card">
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            <span className="badge badge-primary">{g.subject}</span>
            {g.question_type && <span className="badge">🎯 {g.question_type}</span>}
            <span className="spacer" />
            {g.due_date && <span className="caption">{g.due_date}</span>}
          </div>
          <div className="title-strong" style={{ margin: '8px 0 4px' }}>
            {g.title}
          </div>
          <Markdown text={g.description} />
          {g.reason && <div className="caption" style={{ marginTop: 6 }}>💡 {g.reason}</div>}
          <div className="row" style={{ marginTop: 10, gap: 8 }}>
            {g.status === 'active' && (
              <>
                <button
                  className="md-btn md-btn-tonal md-btn-sm"
                  onClick={async () => {
                    await api.put(`/api/goals/${g.id}`, { status: 'done' })
                    toast('已标记完成 🎉')
                    reload()
                  }}
                >
                  ✓ 完成
                </button>
                <button
                  className="md-btn md-btn-text md-btn-sm"
                  onClick={async () => {
                    await api.put(`/api/goals/${g.id}`, { status: 'archived' })
                    reload()
                  }}
                >
                  归档
                </button>
              </>
            )}
            {g.status === 'done' && <span className="badge badge-mastered">已完成 🎉</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function ReportsTab() {
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => api.get<any[]>('/api/reports'), [])
  const [busy, setBusy] = useState(false)
  const [openId, setOpenId] = useState(0)

  const generate = async () => {
    setBusy(true)
    try {
      await api.post('/api/reports/generate', {})
      toast('学习报告已生成')
      reload()
    } catch (e: any) {
      toast(e.message || '生成失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="col">
      <button className="md-btn md-btn-filled" disabled={busy} onClick={generate}>
        {busy ? 'AI 分析中…' : '✨ 生成学习报告'}
      </button>
      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty icon="📊" title="还没有学习报告" desc="点击上方按钮，AI 会分析你的错题与进度生成报告" />
      )}
      {(data || []).map((r) => (
        <div key={r.id} className="md-card">
          <div className="row">
            <div className="title-strong" style={{ flex: 1 }}>
              {r.title}
            </div>
            <span className="caption">{(r.created_at || '').slice(0, 10)}</span>
          </div>
          <Markdown text={openId === r.id ? r.content : r.content.slice(0, 160) + '…'} />
          <button
            className="md-btn md-btn-text md-btn-sm"
            onClick={() => setOpenId(openId === r.id ? 0 : r.id)}
          >
            {openId === r.id ? '收起' : '展开全文'}
          </button>
        </div>
      ))}
    </div>
  )
}
