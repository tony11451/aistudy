import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Chips, Empty, Loading, MASTERY_LABEL, useAsync } from '../components'
import { SUBJECTS } from '../constants'

export default function WrongList() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [subject, setSubject] = useState(params.get('subject') || '')
  const [keyword, setKeyword] = useState(params.get('keyword') || '')
  const [reviewed, setReviewed] = useState('')
  const [input, setInput] = useState(params.get('keyword') || '')

  const query = [
    subject && `subject=${encodeURIComponent(subject)}`,
    keyword && `keyword=${encodeURIComponent(keyword)}`,
    reviewed && `reviewed=${reviewed}`,
    'limit=100',
  ]
    .filter(Boolean)
    .join('&')

  const { data, loading, reload } = useAsync(
    () => api.get<{ total: number; items: any[] }>(`/api/wrong-questions?${query}`),
    [query],
  )

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="md-topbar-title" style={{ fontSize: '1.3rem' }}>错题本</div>
        <button className="md-btn md-btn-tonal md-btn-sm" onClick={() => nav('/wrong/new')}>
          ＋ 录入
        </button>
      </div>

      <form
        className="row"
        style={{ marginBottom: 10 }}
        onSubmit={(e) => {
          e.preventDefault()
          setKeyword(input.trim())
        }}
      >
        <input
          style={{
            flex: 1,
            minHeight: 44,
            padding: '0 16px',
            borderRadius: 'var(--md-shape-full)',
            border: '1.5px solid var(--md-outline-variant)',
            background: 'var(--md-surface-container)',
            outline: 'none',
          }}
          placeholder="搜索题干 / 错因 / 知识点"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="md-btn md-btn-filled md-btn-sm" type="submit">
          搜索
        </button>
      </form>

      <Chips options={SUBJECTS} value={subject as any} onChange={(v) => setSubject(v)} />
      <div className="md-chip-row" style={{ marginTop: 8 }}>
        {[
          ['', '全部'],
          ['0', '待复习'],
          ['1', '已复习'],
        ].map(([v, label]) => (
          <button
            key={v}
            className={`md-chip ${reviewed === v ? 'active' : ''}`}
            onClick={() => setReviewed(v)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="caption" style={{ margin: '12px 2px' }}>
        共 {data?.total ?? 0} 道
      </div>

      {loading && <Loading />}
      {!loading && !data?.items?.length && (
        <Empty
          icon="📝"
          title="错题本空空如也"
          desc="拍照上传第一道错题，AI 会帮你解析错因并记住你的弱点"
          action={
            <button className="md-btn md-btn-filled" onClick={() => nav('/wrong/new')}>
              去录入错题
            </button>
          }
        />
      )}

      <div className="col">
        {(data?.items || []).map((w: any) => (
          <div key={w.id} className="md-card md-card-tappable" onClick={() => nav(`/wrong/${w.id}`)}>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              <span className="badge badge-primary">{w.subject}</span>
              {w.unit && <span className="badge">{w.unit}</span>}
              {(w.knowledge_points || []).slice(0, 2).map((k: string) => (
                <span key={k} className="badge">{k}</span>
              ))}
              <span className="spacer" />
              {w.is_reviewed && <span className="badge badge-mastered">已复习</span>}
              <span className={`badge badge-${w.mastery}`}>
                {MASTERY_LABEL[w.mastery] || w.mastery}
              </span>
            </div>
            <div className="clamp-2" style={{ marginTop: 8 }}>
              {w.question_text || '（图片题，点击查看）'}
            </div>
            {w.wrong_reason && (
              <div className="caption clamp-2" style={{ marginTop: 6 }}>
                错因：{w.wrong_reason}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
