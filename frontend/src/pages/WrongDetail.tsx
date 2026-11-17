import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, Loading, TopBar, Badge, IconBtn, useGoBack } from '../ui'
import { Markdown, MASTERY_LABEL, masteryTone, useAsync } from '../components'
import { ImageViewer } from '../viewer'
import { useToast } from '../store'
import { IconChat, IconDelete, IconCheck } from '../icons'

export default function WrongDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const goBack = useGoBack('/wrong')
  const toast = useToast()
  const [viewImg, setViewImg] = useState<string | null>(null)
  const { data: w, loading, setData } = useAsync(
    () => api.get<any>(`/api/wrong-questions/${id}`),
    [id],
  )

  if (loading || !w) return <Loading />

  const imgSrc = (img: string) => (img.startsWith('/') ? img : `/api/images/${img}`)

  const toggleReviewed = async () => {
    const res = await api.put<any>(`/api/wrong-questions/${id}`, {
      is_reviewed: !w.is_reviewed,
      mastery: !w.is_reviewed ? 'improving' : w.mastery,
    })
    setData(res)
    toast(!w.is_reviewed ? '已标记复习' : '已取消标记')
  }

  const remove = async () => {
    if (!confirm('确定删除这道错题吗？')) return
    await api.del(`/api/wrong-questions/${id}`)
    toast('已删除')
    nav('/wrong')
  }

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar
        title="错题详情"
        back={goBack}
        right={<IconBtn icon={<IconDelete size={20} />} onClick={remove} label="删除" />}
      />

      <div className="row" style={{ flexWrap: 'wrap', gap: 6, margin: '12px 0' }}>
        <Badge tone="primary">{w.subject}</Badge>
        {w.grade && <Badge>{w.grade}</Badge>}
        {w.unit && <Badge>{w.unit}</Badge>}
        <Badge>{w.difficulty}</Badge>
        <Badge tone={masteryTone(w.mastery)}>{MASTERY_LABEL[w.mastery] || w.mastery}</Badge>
      </div>

      {w.knowledge_points?.length > 0 && (
        <div className="row-wrap" style={{ marginBottom: 12 }}>
          {w.knowledge_points.map((k: string) => (
            <button
              key={k}
              className="badge badge-primary"
              style={{ border: 'none', cursor: 'pointer', minHeight: 32 }}
              onClick={() =>
                nav(`/chat/new?kp=${encodeURIComponent(k)}&subject=${encodeURIComponent(w.subject)}`)
              }
            >
              🏷 {k}
            </button>
          ))}
        </div>
      )}

      {w.images?.length > 0 && (
        <div className="img-grid" style={{ marginBottom: 12 }}>
          {w.images.map((img: string, i: number) => (
            <div className="img-cell" key={i} style={{ aspectRatio: '4/3' }} onClick={() => setViewImg(imgSrc(img))}>
              <img src={imgSrc(img)} alt="" />
            </div>
          ))}
        </div>
      )}

      {w.question_text && (
        <CardView variant="filled">
          <div className="caption">题目</div>
          <Markdown text={w.question_text} />
        </CardView>
      )}

      {w.my_question && (
        <CardView variant="filled">
          <div className="caption">我当时的问题</div>
          <div>{w.my_question}</div>
        </CardView>
      )}

      {w.wrong_reason && (
        <CardView variant="filled">
          <div className="caption">🔍 错因分析</div>
          <Markdown text={w.wrong_reason} />
        </CardView>
      )}

      {w.correct_solution && (
        <CardView variant="filled">
          <div className="caption">✅ 正确解法</div>
          <Markdown text={w.correct_solution} />
        </CardView>
      )}

      {w.key_points?.length > 0 && (
        <CardView variant="filled">
          <div className="caption">📌 要点</div>
          <ul style={{ margin: '6px 0', paddingLeft: 20 }}>
            {w.key_points.map((k: string, i: number) => (
              <li key={i}>{k}</li>
            ))}
          </ul>
        </CardView>
      )}

      {w.extensions && (
        <CardView variant="filled">
          <div className="caption">🔁 举一反三</div>
          <Markdown text={w.extensions} />
        </CardView>
      )}

      {(w.method_specific || w.method_general) && (
        <CardView variant="filled">
          <div className="caption">🧭 答题方法</div>
          {w.method_specific && (
            <div style={{ marginTop: 6 }}>
              <strong>具体方法：</strong>
              <Markdown text={w.method_specific} />
            </div>
          )}
          {w.method_general && (
            <div style={{ marginTop: 6 }}>
              <strong>通用方法：</strong>
              <Markdown text={w.method_general} />
            </div>
          )}
        </CardView>
      )}

      {w.learning_content && (
        <CardView variant="filled">
          <div className="caption">📖 AI 识别的学习内容</div>
          <div>{w.learning_content}</div>
        </CardView>
      )}

      <div className="col" style={{ marginTop: 16, gap: 10 }}>
        <Btn
          variant="filled"
          block
          leadingIcon={<IconChat size={18} />}
          onClick={() => nav(`/chat/new?wrong=${w.id}&subject=${encodeURIComponent(w.subject)}`)}
        >
          就这道题继续追问 AI
        </Btn>
        <Btn variant="tonal" block leadingIcon={<IconCheck size={18} />} onClick={toggleReviewed}>
          {w.is_reviewed ? '取消已复习' : '我已复习这道题'}
        </Btn>
      </div>

      {viewImg && (
        <ImageViewer
          src={viewImg}
          onClose={() => setViewImg(null)}
          onDownload={() => {
            const a = document.createElement('a')
            a.href = viewImg
            a.download = 'wrong-question.jpg'
            a.click()
          }}
          onBookmark={async () => {
            await api.post('/api/library/bookmarks', {
              target_type: 'wrong_question',
              target_id: Number(id),
              label: (w.question_text || '错题图片').slice(0, 30),
            })
            toast('已加书签')
          }}
        />
      )}
    </div>
  )
}
