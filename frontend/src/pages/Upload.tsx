import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, compressImage } from '../api'
import { Field, Markdown, TopBar } from '../components'
import { SUBJECTS } from '../constants'
import { useToast } from '../store'

type Mode = 'photo' | 'text' | 'batch' | 'scan'

export default function Upload() {
  const nav = useNavigate()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<Mode>('photo')
  const [subject, setSubject] = useState('数学')
  const [images, setImages] = useState<File[]>([])
  const [text, setText] = useState('')
  const [myQuestion, setMyQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [scanResult, setScanResult] = useState<any>(null)

  const pick = async (files: FileList | null) => {
    if (!files) return
    const arr = Array.from(files).slice(0, 6)
    const compressed = await Promise.all(arr.map((f) => compressImage(f)))
    setImages((prev) => [...prev, ...compressed].slice(0, 6))
  }

  const analyze = async () => {
    setBusy(true)
    setResults([])
    try {
      const image_ids = images.length ? await api.upload(images) : []
      const res = await api.post<{ items: any[] }>('/api/wrong-questions/analyze', {
        subject,
        mode: mode === 'batch' ? 'batch' : 'single',
        text,
        my_question: myQuestion,
        image_ids,
      })
      setResults(res.items)
      toast(`分析完成，共 ${res.items.length} 题`)
    } catch (e: any) {
      toast(e.message || '分析失败')
    } finally {
      setBusy(false)
    }
  }

  const scan = async () => {
    if (!images.length) return toast('请先选择作业照片')
    setBusy(true)
    try {
      const image_ids = await api.upload(images)
      const res = await api.post<any>('/api/knowledge/scan-homework', {
        subject,
        image_ids,
      })
      setScanResult(res)
      toast('已识别学习进度')
    } catch (e: any) {
      toast(e.message || '识别失败')
    } finally {
      setBusy(false)
    }
  }

  const MODES: { key: Mode; label: string; icon: string }[] = [
    { key: 'photo', label: '拍单题', icon: '📸' },
    { key: 'batch', label: '整页多题', icon: '📚' },
    { key: 'text', label: '手动输入', icon: '✍️' },
    { key: 'scan', label: '识别进度', icon: '🔭' },
  ]

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar title="录入错题 / 识别进度" back={() => nav(-1)} />

      <div className="md-tabs" style={{ margin: '12px 0' }}>
        {MODES.map((m) => (
          <button
            key={m.key}
            className={`md-tab ${mode === m.key ? 'active' : ''}`}
            onClick={() => {
              setMode(m.key)
              setResults([])
              setScanResult(null)
            }}
          >
            {m.icon} {m.label}
          </button>
        ))}
      </div>

      <div className="col">
        <Field label="学科">
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            {SUBJECTS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>

        {mode !== 'text' && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              capture="environment"
              multiple
              hidden
              onChange={(e) => pick(e.target.files)}
            />
            <button
              className="md-card md-card-outlined md-card-tappable col"
              style={{ alignItems: 'center', padding: 26, gap: 8 }}
              onClick={() => fileRef.current?.click()}
            >
              <div style={{ fontSize: 36 }}>{mode === 'scan' ? '🔭' : '📷'}</div>
              <div className="title-strong">
                {mode === 'scan' ? '拍照 / 上传作业' : '拍照或从相册选择题目图片'}
              </div>
              <div className="caption">支持多张，自动压缩上传 · JPG/PNG</div>
            </button>
            {images.length > 0 && (
              <div className="img-grid">
                {images.map((img, i) => (
                  <div className="img-cell" key={i}>
                    <img src={URL.createObjectURL(img)} alt="" />
                    <button
                      className="remove"
                      onClick={() => setImages(images.filter((_, j) => j !== i))}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {mode !== 'scan' && (
          <>
            <Field label={mode === 'text' ? '题目内容（可含你的做错过程）' : '补充说明（可选）'}>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="例如：这道二次函数题我第二步算错了…"
              />
            </Field>
            <Field label="我想问 AI（可选）">
              <textarea
                value={myQuestion}
                onChange={(e) => setMyQuestion(e.target.value)}
                placeholder="例如：为什么这里要配方？我一直不懂"
                style={{ minHeight: 76 }}
              />
            </Field>
          </>
        )}

        {mode === 'scan' && (
          <div className="md-card md-card-filled">
            <div className="title-strong">🔭 AI 识别我正在学什么</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              上传近期作业/试卷照片，AI 会识别你正在学习的内容并更新学习进度 ——
              即使课时顺序和教材不一样（比如化学先学了后面的单元）也能识别。
            </p>
          </div>
        )}

        {mode === 'scan' ? (
          <button className="md-btn md-btn-filled md-btn-block" disabled={busy} onClick={scan}>
            {busy ? 'AI 识别中…' : '识别学习进度'}
          </button>
        ) : (
          <button className="md-btn md-btn-filled md-btn-block" disabled={busy} onClick={analyze}>
            {busy ? 'AI 分析中…' : mode === 'batch' ? '批量识别并分析' : 'AI 分析这道错题'}
          </button>
        )}

        {busy && (
          <div className="md-progress">
            <div className="md-progress-bar" style={{ width: '45%' }} />
          </div>
        )}

        {scanResult && (
          <div className="md-card">
            <div className="title-strong">📖 识别结果</div>
            <p style={{ lineHeight: 1.6 }}>{scanResult.summary}</p>
            {(scanResult.learning_items || []).map((it: any, i: number) => (
              <div key={i} className="row" style={{ marginTop: 6 }}>
                <span className="badge badge-primary">{it.knowledge_point}</span>
                <span className="badge">{it.learning_state === 'learned' ? '已学完' : '学习中'}</span>
                <span className="caption clamp-2" style={{ flex: 1 }}>{it.evidence}</span>
              </div>
            ))}
            <button
              className="md-btn md-btn-tonal md-btn-block"
              style={{ marginTop: 12 }}
              onClick={() => nav('/mindmap')}
            >
              查看图谱更新
            </button>
          </div>
        )}

        {results.map((r, i) => (
          <div key={i} className="md-card md-card-elevated">
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              <span className="badge badge-primary">{r.subject}</span>
              {r.unit && <span className="badge">{r.unit}</span>}
              {(r.knowledge_points || []).slice(0, 3).map((k: string) => (
                <span key={k} className="badge">{k}</span>
              ))}
              <span className="spacer" />
              <span className="badge">{r.difficulty}</span>
            </div>
            {r.question_text && (
              <div className="title-strong clamp-3" style={{ margin: '10px 0' }}>
                {r.question_text}
              </div>
            )}
            {r.wrong_reason && (
              <div style={{ marginTop: 8 }}>
                <div className="caption">错因</div>
                <Markdown text={r.wrong_reason} />
              </div>
            )}
            {r.correct_solution && (
              <div style={{ marginTop: 8 }}>
                <div className="caption">正确解法</div>
                <Markdown text={r.correct_solution} />
              </div>
            )}
            <button
              className="md-btn md-btn-tonal md-btn-block"
              style={{ marginTop: 12 }}
              onClick={() => nav(`/wrong/${r.id}`)}
            >
              查看完整分析 / 继续追问
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
