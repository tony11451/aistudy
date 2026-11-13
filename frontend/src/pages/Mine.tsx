import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, changesApi, libraryApi } from '../api'
import {
  Btn,
  CardView,
  ChipFilter,
  ChipRow,
  DialogBox,
  Empty,
  Field,
  Loading,
  TabsBar,
  Badge,
  IconBtn,
} from '../ui'
import { Markdown, MASTERY_LABEL, masteryTone, useAsync } from '../components'
import { useAuth, useToast, useSubjects } from '../store'
import {
  IconCheck,
  IconClose,
  IconDelete,
  IconEdit,
  IconLogout,
  IconRefresh,
  IconSettings,
  IconSparkle,
  IconTarget,
} from '../icons'

type Tab = 'progress' | 'profile' | 'methods' | 'goals' | 'reports' | 'changes' | 'bookmarks'

export default function Mine() {
  const nav = useNavigate()
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('progress')

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14 }}>
        <div
          style={{
            width: 54,
            height: 54,
            borderRadius: 18,
            background: 'var(--m3e-sys-color-primary)',
            color: 'var(--m3e-sys-color-on-primary)',
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
        <IconBtn icon={<IconSettings size={20} />} label="设置" onClick={() => nav('/settings')} />
        <IconBtn
          icon={<IconLogout size={20} />}
          label="退出"
          onClick={() => {
            logout()
            nav('/login')
          }}
        />
      </div>

      <TabsBar<Tab>
        tabs={[
          { value: 'progress', label: '进度' },
          { value: 'profile', label: '档案' },
          { value: 'methods', label: '方法' },
          { value: 'goals', label: '目标' },
          { value: 'reports', label: '报告' },
          { value: 'changes', label: '变更' },
          { value: 'bookmarks', label: '书签' },
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === 'progress' && <ProgressTab />}
      {tab === 'profile' && <ProfileTab />}
      {tab === 'methods' && <MethodsTab />}
      {tab === 'goals' && <GoalsTab />}
      {tab === 'reports' && <ReportsTab />}
      {tab === 'changes' && <ChangesTab />}
      {tab === 'bookmarks' && <BookmarksTab />}
    </div>
  )
}

function ProgressTab() {
  const nav = useNavigate()
  const { data, loading } = useAsync(
    () => api.get<Record<string, any>>('/api/knowledge/progress'),
    [],
  )
  if (loading) return <Loading />
  const entries = Object.entries(data || {})
  const totalWeak = entries.reduce((n, [, d]: any) => n + (d.weak?.length || 0), 0)

  return (
    <div className="col" style={{ marginTop: 14 }}>
      <div className="hero" style={{ padding: 18 }}>
        <h2 style={{ fontSize: '1.35rem' }}>学习进度总览</h2>
        <p>
          薄弱知识点 <strong>{totalWeak}</strong> 个 · 覆盖 {entries.length} 个学科。
          掌握度由 AI 根据错题与对话持续更新。
        </p>
      </div>
      {!entries.length && (
        <Empty
          icon="🔭"
          title="还没有进度数据"
          desc="上传作业让 AI 识别你正在学什么，或录入错题开始积累"
          action={
            <Btn variant="filled" onClick={() => nav('/wrong/new')}>
              去录入
            </Btn>
          }
        />
      )}
      {entries.map(([subject, d]: any) => {
        const total = d.total || 1
        return (
          <CardView key={subject} variant="filled">
            <div className="row">
              <div className="title-strong">{subject}</div>
              <span className="spacer" />
              <Btn variant="text" sm onClick={() => nav('/mindmap')}>
                图谱 →
              </Btn>
            </div>
            <div className="row" style={{ gap: 8, margin: '10px 0', height: 10 }}>
              {(
                [
                  ['weak', 'var(--m3e-sys-color-error)'],
                  ['improving', 'var(--m3e-sys-color-tertiary)'],
                  ['mastered', 'var(--m3e-sys-color-primary)'],
                  ['unknown', 'var(--m3e-sys-color-outline)'],
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
              {(['weak', 'improving', 'mastered'] as const).flatMap((k) =>
                (d[k] || []).slice(0, 4).map((kp: string) => (
                  <Badge key={k + kp} tone={masteryTone(k)}>
                    <span className={`mastery-dot mastery-${k}`} />
                    {kp}
                  </Badge>
                )),
              )}
            </div>
            <div className="caption" style={{ marginTop: 8 }}>
              学习中 {d.learning || 0} · 已学完 {d.learned || 0} · 未接触 {d.not_started || 0}
            </div>
          </CardView>
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
    <div className="col" style={{ marginTop: 14 }}>
      <CardView variant="filled">
        <div className="title-strong">🧠 AI 第二大脑</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          学习档案记录你的薄弱点、常错类型与学习建议（不含原题），每次错题分析后 AI
          会自动增量更新，对话时 AI 会带着这些记忆了解你。
        </p>
      </CardView>
      {(data || []).map((p) => (
        <CardView key={p.subject} variant="filled">
          <div className="row">
            <div className="title-strong">{p.subject}</div>
            <span className="caption">{(p.updated_at || '').slice(0, 10)}</span>
            <span className="spacer" />
            <Btn variant="tonal" sm disabled={busy === p.subject} onClick={() => refreshAI(p.subject)}>
              {busy === p.subject ? 'AI 更新中…' : 'AI 更新'}
            </Btn>
            <Btn
              variant="text"
              sm
              onClick={() => {
                setEditSubject(p.subject)
                setEditText(p.content)
              }}
            >
              编辑
            </Btn>
          </div>
          <Markdown text={p.content} />
        </CardView>
      ))}
      {!data?.length && (
        <Empty
          icon="🧠"
          title="还没有学习档案"
          desc="录入几道错题后，AI 会自动为你建立档案"
          action={
            <Btn
              variant="filled"
              onClick={() => {
                setEditSubject('数学')
                setEditText('')
              }}
            >
              手动新建档案
            </Btn>
          }
        />
      )}
      <DialogBox open={!!editSubject} onClose={() => setEditSubject('')} title={`编辑 ${editSubject} 档案`}>
        <Field label="档案内容" value={editText} onChange={setEditText} multiline rows={8} />
        <div className="row" style={{ marginTop: 14 }}>
          <Btn variant="text" onClick={() => setEditSubject('')}>取消</Btn>
          <span className="spacer" />
          <Btn variant="filled" onClick={save}>保存</Btn>
        </div>
      </DialogBox>
    </div>
  )
}

function MethodsTab() {
  const subjects = useSubjects()
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
    <div className="col" style={{ marginTop: 14 }}>
      <CardView variant="filled">
        <div className="title-strong">🧭 答题方法库</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          AI 结合你的题目总结「具体方法 + 通用方法」（尤其政治、历史、地理等文科主观题），
          错题分析时也会自动积累。
        </p>
        <div style={{ marginTop: 10 }}>
          <Field label="粘贴一道题" value={ask} onChange={setAsk} multiline placeholder="让 AI 总结答题方法…" />
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <div style={{ minWidth: 140 }}>
            <SelectFieldMini value={askSubject} onChange={setAskSubject} />
          </div>
          <span className="spacer" />
          <Btn variant="filled" sm disabled={busy} onClick={summarize}>
            {busy ? 'AI 总结中…' : 'AI 总结方法'}
          </Btn>
        </div>
      </CardView>

      <ChipRow>
        {subjects.map((s) => (
          <ChipFilter key={s} label={s} selected={subject === s} onClick={() => setSubject(subject === s ? '' : s)} />
        ))}
      </ChipRow>

      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty icon="🧭" title="方法库还是空的" desc="分析文科错题或手动总结，方法会自动归档到这里" />
      )}
      {(data || []).map((m) => (
        <CardView key={m.id} variant="filled">
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            <Badge tone="primary">{m.subject}</Badge>
            {m.knowledge_point && <Badge>{m.knowledge_point}</Badge>}
            {m.question_type && <Badge>{m.question_type}</Badge>}
            <span className="spacer" />
            <IconBtn
              icon={<IconDelete size={17} />}
              label="删除"
              onClick={async () => {
                if (!confirm('删除这条方法？')) return
                await api.del(`/api/methods/${m.id}`)
                reload()
              }}
            />
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
        </CardView>
      ))}
    </div>
  )
}

function SelectFieldMini({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const subjects = useSubjects()
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        minHeight: 42,
        width: '100%',
        padding: '0 12px',
        borderRadius: 999,
        border: '1.5px solid var(--m3e-sys-color-outline-variant)',
        background: 'var(--m3e-sys-color-surface)',
        font: 'inherit',
      }}
    >
      {subjects.map((s) => (
        <option key={s}>{s}</option>
      ))}
    </select>
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
    <div className="col" style={{ marginTop: 14 }}>
      <CardView variant="filled">
        <div className="title-strong">🎯 刷题目标</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          不做题海战术 —— AI 根据你的弱点给出「专攻哪一类题」的目标方向、题量建议和验收标准。
        </p>
        <Btn variant="filled" block style={{ marginTop: 10 }} disabled={busy} onClick={generate}>
          {busy ? 'AI 规划中…' : '让 AI 帮我定目标'}
        </Btn>
      </CardView>

      <ChipRow>
        {[
          ['active', '进行中'],
          ['done', '已完成'],
          ['archived', '已归档'],
          ['', '全部'],
        ].map(([v, label]) => (
          <ChipFilter key={label} label={label} selected={status === v} onClick={() => setStatus(v)} />
        ))}
      </ChipRow>

      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty icon="🎯" title="还没有刷题目标" desc="点上方按钮，让 AI 按你的弱点规划刷题方向" />
      )}
      {(data || []).map((g) => (
        <CardView key={g.id} variant="filled">
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            <Badge tone="primary">{g.subject}</Badge>
            {g.question_type && <Badge>🎯 {g.question_type}</Badge>}
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
                <Btn
                  variant="tonal"
                  sm
                  onClick={async () => {
                    await api.put(`/api/goals/${g.id}`, { status: 'done' })
                    toast('已标记完成 🎉')
                    reload()
                  }}
                >
                  完成
                </Btn>
                <Btn
                  variant="text"
                  sm
                  onClick={async () => {
                    await api.put(`/api/goals/${g.id}`, { status: 'archived' })
                    reload()
                  }}
                >
                  归档
                </Btn>
              </>
            )}
            {g.status === 'done' && <Badge tone="mastered">已完成 🎉</Badge>}
          </div>
        </CardView>
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
    <div className="col" style={{ marginTop: 14 }}>
      <Btn variant="filled" disabled={busy} onClick={generate}>
        {busy ? 'AI 分析中…' : '生成学习报告'}
      </Btn>
      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty icon="📊" title="还没有学习报告" desc="点击上方按钮，AI 会分析你的错题与进度生成报告" />
      )}
      {(data || []).map((r) => (
        <CardView key={r.id} variant="filled">
          <div className="row">
            <div className="title-strong" style={{ flex: 1 }}>
              {r.title}
            </div>
            <span className="caption">{(r.created_at || '').slice(0, 10)}</span>
          </div>
          <Markdown text={openId === r.id ? r.content : r.content.slice(0, 160) + '…'} />
          <Btn variant="text" sm onClick={() => setOpenId(openId === r.id ? 0 : r.id)}>
            {openId === r.id ? '收起' : '展开全文'}
          </Btn>
        </CardView>
      ))}
    </div>
  )
}

function ChangesTab() {
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => changesApi.list(80), [])

  const undo = async (id: number) => {
    try {
      await changesApi.undo(id)
      toast('已撤销')
      reload()
    } catch (e: any) {
      toast(e.message || '撤销失败')
    }
  }

  return (
    <div className="col" style={{ marginTop: 14 }}>
      <CardView variant="filled">
        <div className="title-strong">🗂 AI 变更记录</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          AI 通过技能对你的图谱/档案/目标做过的每一次修改都记录在这里（含原因），可随时撤销。
        </p>
      </CardView>
      {loading && <Loading />}
      {!loading && !(data || []).length && (
        <Empty icon="🗂" title="还没有变更" desc="让 AI 整理弱点或总结知识点后，变更会出现在这里" />
      )}
      {(data || []).map((c: any) => (
        <CardView key={c.id} variant="filled"
                  style={{ borderLeft: `4px solid ${c.undone ? 'var(--m3e-sys-color-outline)' : 'var(--m3e-sys-color-primary)'}` }}>
          <div className="row" style={{ gap: 8 }}>
            <Badge tone={c.undone ? 'neutral' : 'primary'}>{c.action}</Badge>
            <span className="caption">{c.target_type} · {c.skill}</span>
            <span className="spacer" />
            <span className="caption">{(c.created_at || '').slice(0, 16).replace('T', ' ')}</span>
          </div>
          <div style={{ margin: '8px 0 4px', lineHeight: 1.5, textDecoration: c.undone ? 'line-through' : 'none' }}>
            {c.description}
          </div>
          {c.reason && <div className="caption">💡 {c.reason}</div>}
          {!c.undone && (
            <div className="row" style={{ marginTop: 8 }}>
              <span className="spacer" />
              <Btn variant="outlined" sm onClick={() => undo(c.id)}>撤销此变更</Btn>
            </div>
          )}
          {c.undone && <div className="caption" style={{ marginTop: 6 }}>已撤销</div>}
        </CardView>
      ))}
    </div>
  )
}


function BookmarksTab() {
  const nav = useNavigate()
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => libraryApi.bookmarks(), [])

  return (
    <div className="col" style={{ marginTop: 14 }}>
      <CardView variant="filled">
        <div className="title-strong">⭐ 书签</div>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          在图片查看器、错题详情、档案库中都可以加书签，这里统一查看。
        </p>
      </CardView>
      {loading && <Loading />}
      {!loading && !(data || []).length && (
        <Empty icon="⭐" title="还没有书签" desc="查看图片时点 ☆ 即可收藏" />
      )}
      {(data || []).map((b: any) => (
        <CardView key={b.id} variant="filled">
          <div className="row">
            <Badge tone="primary">{b.target_type === 'library_item' ? '档案' : b.target_type === 'wrong_question' ? '错题' : b.target_type === 'book_page' ? '书页' : '图片'}</Badge>
            <div className="title-strong text-ellipsis" style={{ flex: 1 }}>{b.label || '未命名书签'}</div>
            <span className="caption">{(b.created_at || '').slice(0, 10)}</span>
          </div>
          {b.note && <div className="caption" style={{ marginTop: 4 }}>{b.note}</div>}
          <div className="row" style={{ marginTop: 8, gap: 8 }}>
            <Btn variant="tonal" sm onClick={() => {
              if (b.target_type === 'wrong_question') nav('/wrong/' + b.target_id)
              else nav('/library')
            }}>
              前往
            </Btn>
            <Btn variant="text" sm onClick={async () => {
              await libraryApi.deleteBookmark(b.id)
              toast('已删除')
              reload()
            }}>
              删除
            </Btn>
          </div>
        </CardView>
      ))}
    </div>
  )
}
