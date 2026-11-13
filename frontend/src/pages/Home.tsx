import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, Loading, Badge } from '../ui'
import { MASTERY_LABEL, masteryTone, useAsync } from '../components'
import { useAuth } from '../store'
import { IconMap, IconCamera, IconSearch } from '../icons'

export default function Home() {
  const nav = useNavigate()
  const { user } = useAuth()
  const { data, loading } = useAsync(async () => {
    const [stats, progress, goals] = await Promise.all([
      api.get<{ total: number; items: any[] }>('/api/wrong-questions?limit=5'),
      api.get<Record<string, any>>('/api/knowledge/progress'),
      api.get<any[]>('/api/goals?status=active'),
    ])
    return { stats, progress, goals }
  }, [])

  if (loading) return <Loading />

  const allWeak = Object.entries(data?.progress || {}).flatMap(([subject, d]: any) =>
    (d.weak || []).map((kp: string) => ({ subject, kp })),
  )
  const hour = new Date().getHours()
  const greet = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="spacer" />
        <button
          className="bubble-action-btn"
          style={{ minHeight: 38 }}
          onClick={() => nav('/search')}
        >
          <IconSearch size={15} /> 全局搜索
        </button>
      </div>
      <div className="hero">
        <h2>
          {greet}，{user?.display_name || '同学'}
        </h2>
        <p>
          今天也来消灭几个薄弱点吧 —— 当前薄弱知识点{' '}
          <strong>{allWeak.length}</strong> 个，进行中的刷题目标{' '}
          <strong>{data?.goals?.length || 0}</strong> 个
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
            看弱点图谱
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

      {allWeak.length > 0 && (
        <>
          <div className="section-title">优先攻克</div>
          <div className="row-wrap">
            {allWeak.slice(0, 6).map((w) => (
              <button
                key={w.subject + w.kp}
                className="badge badge-weak"
                style={{ border: 'none', cursor: 'pointer', minHeight: 34 }}
                onClick={() =>
                  nav(`/chat?kp=${encodeURIComponent(w.kp)}&subject=${encodeURIComponent(w.subject)}`)
                }
              >
                <span className="mastery-dot mastery-weak" />
                {w.subject} · {w.kp}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="row" style={{ marginTop: 6 }}>
        <div className="section-title" style={{ flex: 1 }}>
          最近错题
        </div>
        <Btn variant="text" sm onClick={() => nav('/wrong')}>
          全部 →
        </Btn>
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
        {!data?.stats?.items?.length && (
          <CardView variant="outlined">
            <div className="muted" style={{ textAlign: 'center' }}>
              还没有错题，点击下方「错题」开始拍照上传吧
            </div>
          </CardView>
        )}
      </div>
    </div>
  )
}
