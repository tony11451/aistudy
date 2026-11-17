import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, ChipFilter, ChipRow, Empty, Loading, Sheet, Badge, IconBtn } from '../ui'
import { MASTERY_LABEL, masteryTone, useAsync } from '../components'
import { useAuth, useToast } from '../store'
import { IconMap, IconCamera, IconSearch, IconSettings, IconChat, IconTarget, IconSparkle } from '../icons'

const ALL_WIDGETS = [
  { key: 'weak', label: '薄弱点' },
  { key: 'recent', label: '最近错题' },
  { key: 'goals', label: '刷题目标' },
  { key: 'brief', label: '昨晚简报' },
  { key: 'pending', label: '待审核变更' },
  { key: 'teachers', label: '各科老师' },
]

const DEFAULT_WIDGETS = ['weak', 'recent', 'goals', 'brief', 'pending', 'teachers']

export default function Home() {
  const nav = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const [showWidgets, setShowWidgets] = useState(false)
  const [sel, setSel] = useState<string[]>(user?.widgets?.length ? user.widgets : DEFAULT_WIDGETS)

  const { data, loading } = useAsync(async () => {
    const [stats, progress, goals, reports, changes, teachers] = await Promise.all([
      api.get<{ total: number; items: any[] }>('/api/wrong-questions?limit=5'),
      api.get<Record<string, any>>('/api/knowledge/progress'),
      api.get<any[]>('/api/goals?status=active'),
      api.get<any[]>('/api/reports'),
      api.get<any[]>('/api/changes?status=pending&limit=10'),
      api.get<any>('/api/chat/teachers'),
    ])
    return { stats, progress, goals, reports, changes, teachers }
  }, [])

  if (loading) return <Loading />

  const enabled = (k: string) => sel.includes(k)
  const allWeak = Object.entries(data?.progress || {}).flatMap(([subject, d]: any) =>
    (d.weak || []).map((kp: string) => ({ subject, kp })),
  )
  const hour = new Date().getHours()
  const greet = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'
  const brief = (data?.reports || []).find((r: any) => r.kind === 'nightly')
  const pending = (data?.changes || []).filter((c: any) => c.status === 'pending')
  const teachers = data?.teachers || {}

  const saveWidgets = async () => {
    await api.put('/api/auth/widgets', { widgets: sel })
    toast('小组件已保存')
    setShowWidgets(false)
  }

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="spacer" />
        <button className="bubble-action-btn" style={{ minHeight: 38 }} onClick={() => nav('/search')}>
          <IconSearch size={15} /> 全局搜索
        </button>
        <IconBtn icon={<IconSettings size={18} />} label="小组件设置" onClick={() => setShowWidgets(true)} />
      </div>

      <div className="hero">
        <h2>
          {greet}，{user?.display_name || '同学'}
        </h2>
        <p>
          当前薄弱知识点 <strong>{allWeak.length}</strong> 个 · 进行中目标{' '}
          <strong>{data?.goals?.length || 0}</strong> 个
          {pending.length > 0 && <> · <strong>{pending.length}</strong> 条夜间整理待审核</>}
        </p>
        <div className="row" style={{ marginTop: 16, gap: 10, flexWrap: 'wrap' }}>
          <Btn variant="filled" onClick={() => nav('/wrong/new')} leadingIcon={<IconCamera size={18} />}>
            拍错题
          </Btn>
          <Btn
            variant="tonal"
            onClick={() => nav('/mindmap')}
            leadingIcon={<IconMap size={18} />}
            style={{ background: 'rgba(255,255,255,0.22)', color: '#fff' }}
          >
            弱点图谱
          </Btn>
        </div>
      </div>

      <div className="row" style={{ marginTop: 16, gap: 10 }}>
        <div className="stat-card">
          <div className="stat-num">{data?.stats?.total ?? 0}</div>
          <div className="caption">累计错题</div>
        </div>
        <div className="stat-card">
          <div className="stat-num">{allWeak.length}</div>
          <div className="caption">薄弱知识点</div>
        </div>
        <div className="stat-card">
          <div className="stat-num">{data?.goals?.length ?? 0}</div>
          <div className="caption">刷题目标</div>
        </div>
      </div>

      {/* ===== 小组件（可开关/排序由 sel 顺序决定） ===== */}
      {sel.map((key) => {
        if (key === 'weak' && allWeak.length > 0)
          return (
            <div key={key}>
              <div className="section-title">优先攻克</div>
              <div className="row-wrap">
                {allWeak.slice(0, 6).map((w) => (
                  <button
                    key={w.subject + w.kp}
                    className="badge badge-weak"
                    style={{ border: 'none', cursor: 'pointer', minHeight: 34 }}
                    onClick={() =>
                      nav(`/chat/new?teacher=${encodeURIComponent(w.subject)}`)
                    }
                  >
                    <span className="mastery-dot mastery-weak" />
                    {w.subject} · {w.kp}
                  </button>
                ))}
              </div>
            </div>
          )
        if (key === 'recent')
          return (
            <div key={key}>
              <div className="row" style={{ marginTop: 6 }}>
                <div className="section-title" style={{ flex: 1 }}>最近错题</div>
                <Btn variant="text" sm onClick={() => nav('/wrong')}>全部 →</Btn>
              </div>
              <div className="col">
                {(data?.stats?.items || []).map((w: any) => (
                  <CardView key={w.id} variant="filled" onClick={() => nav(`/wrong/${w.id}`)}>
                    <div className="row">
                      <Badge tone="primary">{w.subject}</Badge>
                      {w.knowledge_points?.[0] && <Badge>{w.knowledge_points[0]}</Badge>}
                      <span className="spacer" />
                      <Badge tone={masteryTone(w.mastery)}>{MASTERY_LABEL[w.mastery] || w.mastery}</Badge>
                    </div>
                    <div className="clamp-2" style={{ marginTop: 8 }}>
                      {w.question_text || '（图片题）'}
                    </div>
                  </CardView>
                ))}
              </div>
            </div>
          )
        if (key === 'goals' && (data?.goals || []).length > 0)
          return (
            <div key={key}>
              <div className="row">
                <div className="section-title" style={{ flex: 1 }}>🎯 刷题目标</div>
                <Btn variant="text" sm onClick={() => nav('/mine')}>更多 →</Btn>
              </div>
              {(data?.goals || []).slice(0, 2).map((g: any) => (
                <CardView key={g.id} variant="filled">
                  <div className="title-strong">{g.title}</div>
                  <div className="caption clamp-2">{g.description}</div>
                </CardView>
              ))}
            </div>
          )
        if (key === 'brief' && brief)
          return (
            <CardView key={key} variant="elevated">
              <div className="row">
                <IconSparkle size={16} />
                <div className="title-strong" style={{ flex: 1 }}>{brief.title}</div>
              </div>
              <div className="caption clamp-3" style={{ marginTop: 6 }}>{brief.content}</div>
            </CardView>
          )
        if (key === 'pending' && pending.length > 0)
          return (
            <CardView key={key} variant="elevated" style={{ cursor: 'pointer' }}
                      onClick={() => nav('/mine')}>
              <div className="row">
                <Badge tone="improving">待审核</Badge>
                <div className="title-strong" style={{ flex: 1 }}>
                  夜间整理了 {pending.length} 条变更
                </div>
                <Btn variant="tonal" sm>去审核</Btn>
              </div>
            </CardView>
          )
        if (key === 'teachers')
          return (
            <div key={key}>
              <div className="row">
                <div className="section-title" style={{ flex: 1 }}>各科老师</div>
                {teachers.coordinator && (
                  <Btn variant="text" sm leadingIcon={<IconChat size={14} />}
                       onClick={() => nav(`/chat/${teachers.coordinator.id}`)}>
                    班主任
                  </Btn>
                )}
              </div>
              <div className="row-wrap">
                {(teachers.teachers || []).map((t: any) => (
                  <button
                    key={t.id}
                    className="badge badge-primary"
                    style={{ border: 'none', cursor: 'pointer', minHeight: 36 }}
                    onClick={() => nav(`/chat/${t.id}`)}
                  >
                    <IconChat size={13} /> {t.context_ref || t.title}
                  </button>
                ))}
                {!(teachers.teachers || []).length && (
                  <span className="caption">
                    拍错题或提问后，各科老师会在这里出现
                  </span>
                )}
              </div>
            </div>
          )
        return null
      })}

      {/* 小组件配置 */}
      <Sheet open={showWidgets} onClose={() => setShowWidgets(false)} title="首页小组件">
        <div className="col">
          <div className="caption">选择要显示的卡片（按选择顺序排列）：</div>
          <ChipRow>
            {ALL_WIDGETS.map((w) => (
              <ChipFilter
                key={w.key}
                label={sel.includes(w.key) ? `✓ ${w.label}` : w.label}
                selected={sel.includes(w.key)}
                onClick={() =>
                  setSel(sel.includes(w.key) ? sel.filter((x) => x !== w.key) : [...sel, w.key])
                }
              />
            ))}
          </ChipRow>
          <Btn variant="filled" block onClick={saveWidgets}>
            保存
          </Btn>
        </div>
      </Sheet>
    </div>
  )
}
