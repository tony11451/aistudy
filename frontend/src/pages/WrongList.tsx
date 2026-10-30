import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, ChipFilter, ChipRow, Empty, Field, Loading, Badge } from '../ui'
import { MASTERY_LABEL, masteryTone, useAsync } from '../components'
import { IconPlus, IconSearch } from '../icons'
import { useSubjects } from '../store'

export default function WrongList() {
  const subjects = useSubjects()
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

  const { data, loading } = useAsync(
    () => api.get<{ total: number; items: any[] }>(`/api/wrong-questions?${query}`),
    [query],
  )

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="topbar-title" style={{ fontSize: '1.35rem' }}>错题本</div>
        <Btn variant="tonal" sm onClick={() => nav('/wrong/new')} leadingIcon={<IconPlus size={16} />}>
          录入
        </Btn>
      </div>

      <form
        className="row"
        style={{ marginBottom: 10 }}
        onSubmit={(e) => {
          e.preventDefault()
          setKeyword(input.trim())
        }}
      >
        <div style={{ flex: 1 }}>
          <Field label="" value={input} onChange={setInput} placeholder="搜索题干 / 错因 / 知识点" />
        </div>
        <Btn variant="filled" sm type="submit" leadingIcon={<IconSearch size={16} />}>
          搜索
        </Btn>
      </form>

      <ChipRow>
        {subjects.map((s) => (
          <ChipFilter key={s} label={s} selected={subject === s} onClick={() => setSubject(subject === s ? '' : s)} />
        ))}
      </ChipRow>
      <ChipRow>
        {[
          ['', '全部'],
          ['0', '待复习'],
          ['1', '已复习'],
        ].map(([v, label]) => (
          <ChipFilter key={label} label={label} selected={reviewed === v} onClick={() => setReviewed(v)} />
        ))}
      </ChipRow>

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
            <Btn variant="filled" onClick={() => nav('/wrong/new')}>
              去录入错题
            </Btn>
          }
        />
      )}

      <div className="col">
        {(data?.items || []).map((w: any) => (
          <CardView key={w.id} variant="filled" onClick={() => nav(`/wrong/${w.id}`)}>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              <Badge tone="primary">{w.subject}</Badge>
              {w.unit && <Badge>{w.unit}</Badge>}
              {(w.knowledge_points || []).slice(0, 2).map((k: string) => (
                <Badge key={k}>{k}</Badge>
              ))}
              <span className="spacer" />
              {w.is_reviewed && <Badge tone="mastered">已复习</Badge>}
              <Badge tone={masteryTone(w.mastery)}>{MASTERY_LABEL[w.mastery] || w.mastery}</Badge>
            </div>
            <div className="clamp-2" style={{ marginTop: 8 }}>
              {w.question_text || '（图片题，点击查看）'}
            </div>
            {w.wrong_reason && (
              <div className="caption clamp-2" style={{ marginTop: 6 }}>
                错因：{w.wrong_reason}
              </div>
            )}
          </CardView>
        ))}
      </div>
    </div>
  )
}
