import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, ChipFilter, ChipRow, Empty, Field, Loading, TopBar, Badge } from '../ui'
import { Markdown, useAsync } from '../components'
import { useSubjects, useToast } from '../store'
import { IconSearch, IconSparkle } from '../icons'

type Hit = { id: number; type: string; title: string; subject?: string; kind?: string; extra?: string; date?: string }

export default function Search() {
  const nav = useNavigate()
  const toast = useToast()
  const subjects = useSubjects()
  const [params] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const [query, setQuery] = useState(params.get('q') || '')
  const [subject, setSubject] = useState('')
  const [source, setSource] = useState('')
  const [aiMode, setAiMode] = useState(false)
  const [aiBusy, setAiBusy] = useState(false)
  const [aiAnswer, setAiAnswer] = useState('')

  const { data, loading } = useAsync(
    () => (query ? api.get<any>(`/api/search?q=${encodeURIComponent(query)}&subject=${subject}&source=${source}`) : Promise.resolve(null)),
    [query, subject, source],
  )

  const runAiSearch = async () => {
    if (!q.trim()) return toast('请输入搜索内容')
    setAiBusy(true)
    setAiAnswer('')
    try {
      const res = await api.post<any>('/api/search/ai', { q, subject, source })
      setAiAnswer(res.answer)
      setAiMode(true)
    } catch (e: any) {
      toast(e.message || 'AI 搜索失败')
    } finally {
      setAiBusy(false)
    }
  }

  const groups: [string, Hit[]][] = [
    ['错题', data?.wrong_questions || []],
    ['档案库', data?.library || []],
    ['图谱节点', data?.nodes || []],
    ['对话', data?.conversations || []],
  ]
  const total = groups.reduce((n, [, arr]) => n + arr.length, 0)

  const goto = (h: Hit) => {
    if (h.type === 'wrong_question') nav(`/wrong/${h.id}`)
    else if (h.type === 'library') nav('/library')
    else if (h.type === 'node') nav('/mindmap')
    else if (h.type === 'conversation') nav(`/chat/${h.id}`)
  }

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar title="全局搜索" back={() => nav(-1)} />

      <form
        className="row"
        style={{ margin: '12px 0' }}
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(q.trim())
          setAiMode(false)
        }}
      >
        <div style={{ flex: 1 }}>
          <Field label="" value={q} onChange={setQ} placeholder="搜索题目 / 知识点 / 资料 / 对话" />
        </div>
        <Btn variant="filled" sm type="submit" leadingIcon={<IconSearch size={16} />}>
          搜索
        </Btn>
      </form>

      <ChipRow>
        <ChipFilter label="全部学科" selected={!subject} onClick={() => setSubject('')} />
        {subjects.map((s) => (
          <ChipFilter key={s} label={s} selected={subject === s} onClick={() => setSubject(s)} />
        ))}
      </ChipRow>
      <ChipRow>
        {[
          ['', '全部来源'],
          ['wrong_question', '错题'],
          ['image', '图片'],
          ['text', '文字'],
          ['attachment', '附件'],
          ['review', '复习资料'],
        ].map(([v, label]) => (
          <ChipFilter key={label} label={label} selected={source === v} onClick={() => setSource(v)} />
        ))}
      </ChipRow>

      <Btn variant="tonal" block style={{ margin: '10px 0' }} disabled={aiBusy} onClick={runAiSearch}
           leadingIcon={<IconSparkle size={16} />}>
        {aiBusy ? 'AI 全局检索中…' : 'AI 高级搜索（查找以前是否出现过）'}
      </Btn>

      {aiMode && aiAnswer && (
        <CardView variant="elevated" style={{ marginBottom: 12 }}>
          <div className="caption">AI 检索结论</div>
          <Markdown text={aiAnswer} />
        </CardView>
      )}

      {loading && <Loading />}
      {!loading && query && total === 0 && !aiMode && (
        <Empty
          icon="🔍"
          title="没有找到相关内容"
          desc="换个关键词，或试试 AI 高级搜索"
          action={<Btn variant="tonal" onClick={runAiSearch}>AI 高级搜索</Btn>}
        />
      )}

      {!aiMode &&
        groups.map(([label, hits]) =>
          hits.length ? (
            <div key={label}>
              <div className="section-title" style={{ fontSize: '1.05rem' }}>
                {label}（{hits.length}）
              </div>
              <div className="col">
                {hits.map((h) => (
                  <CardView key={h.type + h.id} variant="filled" onClick={() => goto(h)}>
                    <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                      {h.subject && <Badge tone="primary">{h.subject}</Badge>}
                      {h.kind && <Badge>{h.kind}</Badge>}
                      <span className="spacer" />
                      {h.date && <span className="caption">{h.date.slice(0, 10)}</span>}
                    </div>
                    <div className="text-ellipsis" style={{ fontWeight: 600, margin: '6px 0' }}>
                      {h.title}
                    </div>
                    {h.extra && <div className="caption clamp-2">{h.extra}</div>}
                  </CardView>
                ))}
              </div>
            </div>
          ) : null,
        )}
    </div>
  )
}
