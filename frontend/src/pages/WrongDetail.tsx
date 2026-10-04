import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Loading, Markdown, MASTERY_LABEL, TopBar, useAsync } from '../components'
import { useToast } from '../store'

export default function WrongDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const { data: w, loading, reload, setData } = useAsync(
    () => api.get<any>(`/api/wrong-questions/${id}`),
    [id],
  )

  if (loading || !w) return <Loading />

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
        back={() => nav(-1)}
        right={
          <button className="md-iconbtn" onClick={remove} title="删除">
            🗑
          </button>
        }
      />

      <div className="row" style={{ flexWrap: 'wrap', gap: 6, margin: '12px 0' }}>
        <span className="badge badge-primary">{w.subject}</span>
        {w.grade && <span className="badge">{w.grade}</span>}
        {w.unit && <span className="badge">{w.unit}</span>}
        <span className="badge">{w.difficulty}</span>
        <span className={`badge badge-${w.mastery}`}>{MASTERY_LABEL[w.mastery] || w.mastery}</span>
      </div>

      {w.knowledge_points?.length > 0 && (
        <div className="row-wrap" style={{ marginBottom: 12 }}>
          {w.knowledge_points.map((k: string) => (
            <button
              key={k}
              className="md-chip"
              onClick={() => nav(`/chat?kp=${encodeURIComponent(k)}&subject=${encodeURIComponent(w.subject)}`)}
            >
              🏷 {k}
            </button>
          ))}
        </div>
      )}

      {w.images?.length > 0 && (
        <div className="img-grid" style={{ marginBottom: 12 }}>
          {w.images.map((img: string, i: number) => (
            <div className="img-cell" key={i} style={{ aspectRatio: '4/3' }}>
              <img src={img.startsWith('/') ? img : `/api/images/${img}`} alt="" />
            </div>
          ))}
        </div>
      )}

      {w.question_text && (
        <div className="md-card md-card-filled">
          <div className="caption">题目</div>
          <Markdown text={w.question_text} />
        </div>
      )}

      {w.my_question && (
        <div className="md-card" style={{ marginTop: 10 }}>
          <div className="caption">我当时的问题</div>
          <div>{w.my_question}</div>
        </div>
      )}

      {w.wrong_reason && (
        <div className="md-card" style={{ marginTop: 10 }}>
          <div className="caption">🔍 错因分析</div>
          <Markdown text={w.wrong_reason} />
        </div>
      )}

      {w.correct_solution && (
        <div className="md-card" style={{ marginTop: 10 }}>
          <div className="caption">✅ 正确解法</div>
          <Markdown text={w.correct_solution} />
        </div>
      )}

      {w.key_points?.length > 0 && (
        <div className="md-card" style={{ marginTop: 10 }}>
          <div className="caption">📌 要点</div>
          <ul style={{ margin: '6px 0', paddingLeft: 20 }}>
            {w.key_points.map((k: string, i: number) => (
              <li key={i}>{k}</li>
            ))}
          </ul>
        </div>
      )}

      {w.extensions && (
        <div className="md-card" style={{ marginTop: 10 }}>
          <div className="caption">🔁 举一反三</div>
          <Markdown text={w.extensions} />
        </div>
      )}

      {(w.method_specific || w.method_general) && (
        <div className="md-card" style={{ marginTop: 10 }}>
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
        </div>
      )}

      {w.learning_content && (
        <div className="md-card" style={{ marginTop: 10 }}>
          <div className="caption">📖 AI 识别的学习内容</div>
          <div>{w.learning_content}</div>
        </div>
      )}

      <div className="col" style={{ marginTop: 16, gap: 10 }}>
        <button
          className="md-btn md-btn-filled md-btn-block"
          onClick={() => nav(`/chat?wrong=${w.id}&subject=${encodeURIComponent(w.subject)}`)}
        >
          💬 就这道题继续追问 AI
        </button>
        <button className="md-btn md-btn-tonal md-btn-block" onClick={toggleReviewed}>
          {w.is_reviewed ? '↩ 取消已复习' : '✓ 我已复习这道题'}
        </button>
      </div>
    </div>
  )
}
