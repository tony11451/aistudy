import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, compressImage } from '../api'
import { Btn, CardView, Field, SelectField, TopBar, Loading, Badge, useGoBack } from '../ui'
import { Markdown } from '../components'
import { CropModal } from '../crop'
import { ImageViewer } from '../viewer'
import { SUBJECTS } from '../constants'
import { useToast } from '../store'
import { IconCamera, IconImage, IconCrop, IconTarget, IconSparkle } from '../icons'

type Mode = 'photo' | 'text' | 'batch' | 'scan'

export default function Upload() {
  const nav = useNavigate()
  const goBack = useGoBack('/wrong')
  const toast = useToast()
  const camRef = useRef<HTMLInputElement>(null)
  const albumRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<Mode>('photo')
  const [subject, setSubject] = useState('数学')
  const [images, setImages] = useState<File[]>([])
  const [cropFile, setCropFile] = useState<File | null>(null)
  const [viewImg, setViewImg] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [myQuestion, setMyQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [scanResult, setScanResult] = useState<any>(null)

  const afterPick = async (files: FileList | null, croppable: boolean) => {
    if (!files?.length) return
    const f = files[0]
    if (croppable && mode !== 'scan') {
      setCropFile(f)
      return
    }
    const arr = await Promise.all(Array.from(files).slice(0, 6).map((x) => compressImage(x)))
    setImages((prev) => [...prev, ...arr].slice(0, 6))
  }

  const analyze = async () => {
    setBusy(true)
    setResults([])
    try {
      setStage('上传图片…')
      const image_ids = images.length ? await api.upload(images) : []
      setStage('AI 识别与分析中…')
      const res = await api.post<{ items: any[] }>('/api/wrong-questions/analyze', {
        subject,
        mode: mode === 'batch' ? 'batch' : 'single',
        text,
        my_question: myQuestion,
        image_ids,
      })
      setStage('完成')
      setResults(res.items)
      toast(`分析完成，共 ${res.items.length} 题`)
    } catch (e: any) {
      toast(e.message || '分析失败')
    } finally {
      setBusy(false)
      setStage('')
    }
  }

  const scan = async () => {
    if (!images.length) return toast('请先选择作业照片')
    setBusy(true)
    try {
      setStage('AI 识别学习内容…')
      const image_ids = await api.upload(images)
      const res = await api.post<any>('/api/knowledge/scan-homework', { subject, image_ids })
      setScanResult(res)
      toast('已识别学习进度')
    } catch (e: any) {
      toast(e.message || '识别失败')
    } finally {
      setBusy(false)
      setStage('')
    }
  }

  const MODES: { key: Mode; label: string; icon: React.ReactNode }[] = [
    { key: 'photo', label: '拍单题', icon: <IconCamera size={15} /> },
    { key: 'batch', label: '整页多题', icon: <IconImage size={15} /> },
    { key: 'text', label: '手动输入', icon: <IconSparkle size={15} /> },
    { key: 'scan', label: '识别进度', icon: <IconTarget size={15} /> },
  ]

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar title="录入错题 / 识别进度" back={goBack} />

      <div className="row" style={{ gap: 8, margin: '12px 0', flexWrap: 'wrap' }}>
        {MODES.map((m) => (
          <Btn
            key={m.key}
            variant={mode === m.key ? 'filled' : 'outlined'}
            sm
            leadingIcon={m.icon}
            onClick={() => {
              setMode(m.key)
              setResults([])
              setScanResult(null)
            }}
          >
            {m.label}
          </Btn>
        ))}
      </div>

      <div className="col">
        <SelectField label="学科" value={subject} options={SUBJECTS} onChange={setSubject} />

        {mode !== 'text' && (
          <>
            <input ref={camRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => afterPick(e.target.files, true)} />
            <input ref={albumRef} type="file" accept="image/*" multiple hidden onChange={(e) => afterPick(e.target.files, false)} />
            <div className="row" style={{ gap: 10 }}>
              <Btn
                variant="filled"
                block
                leadingIcon={<IconCamera size={18} />}
                onClick={() => camRef.current?.click()}
              >
                拍照
              </Btn>
              <Btn
                variant="tonal"
                block
                leadingIcon={<IconImage size={18} />}
                onClick={() => albumRef.current?.click()}
              >
                相册 / 文件
              </Btn>
            </div>
            {images.length > 0 && (
              <>
                <div className="img-grid">
                  {images.map((img, i) => (
                    <div className="img-cell" key={i} onClick={() => setViewImg(URL.createObjectURL(img))}>
                      <img src={URL.createObjectURL(img)} alt="" />
                      <button
                        className="remove"
                        onClick={(e) => {
                          e.stopPropagation()
                          setImages(images.filter((_, j) => j !== i))
                        }}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
                <div className="caption">点击图片可放大查看 · 再次拍照可继续添加</div>
              </>
            )}
          </>
        )}

        {mode !== 'scan' && (
          <>
            <Field
              label={mode === 'text' ? '题目内容（可含你的做错过程）' : '补充说明（可选）'}
              value={text}
              onChange={setText}
              multiline
              placeholder="例如：这道二次函数题我第二步算错了…"
            />
            <Field
              label="我想问 AI（可选）"
              value={myQuestion}
              onChange={setMyQuestion}
              multiline
              rows={2}
              placeholder="例如：为什么这里要配方？我一直不懂"
            />
          </>
        )}

        {mode === 'scan' && (
          <CardView variant="filled">
            <div className="title-strong">🔭 AI 识别我正在学什么</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              上传近期作业/试卷照片，AI 会识别你正在学习的内容并更新学习进度 ——
              即使课时顺序和教材不一样（比如化学先学了后面的单元）也能识别。
            </p>
          </CardView>
        )}

        {mode === 'scan' ? (
          <Btn variant="filled" block disabled={busy} onClick={scan}>
            {busy ? stage || 'AI 识别中…' : '识别学习进度'}
          </Btn>
        ) : (
          <Btn variant="filled" block disabled={busy} onClick={analyze}>
            {busy ? stage || 'AI 分析中…' : mode === 'batch' ? '批量识别并分析' : 'AI 分析这道错题'}
          </Btn>
        )}

        {busy && (
          <div className="row" style={{ justifyContent: 'center', padding: 10 }}>
            <Loading text={stage || '处理中…'} />
          </div>
        )}

        {scanResult && (
          <CardView variant="filled">
            <div className="title-strong">📖 识别结果</div>
            <p style={{ lineHeight: 1.6 }}>{scanResult.summary}</p>
            {(scanResult.learning_items || []).map((it: any, i: number) => (
              <div key={i} className="row" style={{ marginTop: 6 }}>
                <Badge tone="primary">{it.knowledge_point}</Badge>
                <Badge>{it.learning_state === 'learned' ? '已学完' : '学习中'}</Badge>
                <span className="caption clamp-2" style={{ flex: 1 }}>{it.evidence}</span>
              </div>
            ))}
            <Btn variant="tonal" block style={{ marginTop: 12 }} onClick={() => nav('/mindmap')}>
              查看图谱更新
            </Btn>
          </CardView>
        )}

        {results.map((r, i) => (
          <CardView key={i} variant="elevated">
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              <Badge tone="primary">{r.subject}</Badge>
              {r.unit && <Badge>{r.unit}</Badge>}
              {(r.knowledge_points || []).slice(0, 3).map((k: string) => (
                <Badge key={k}>{k}</Badge>
              ))}
              <span className="spacer" />
              <Badge>{r.difficulty}</Badge>
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
            <Btn variant="tonal" block style={{ marginTop: 12 }} onClick={() => nav(`/wrong/${r.id}`)}>
              查看完整分析 / 继续追问
            </Btn>
          </CardView>
        ))}
      </div>

      {cropFile && (
        <CropModal
          file={cropFile}
          onCancel={() => setCropFile(null)}
          onConfirm={async (f) => {
            setCropFile(null)
            const compressed = await compressImage(f)
            setImages((prev) => [...prev, compressed].slice(0, 6))
          }}
        />
      )}
      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}
    </div>
  )
}
