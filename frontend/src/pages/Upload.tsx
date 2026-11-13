import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, compressImage } from '../api'
import { Btn, CardView, Field, SelectField, TopBar, Loading, Badge, useGoBack } from '../ui'
import { Markdown } from '../components'
import { CropModal } from '../crop'
import { ImageViewer } from '../viewer'
import { useToast, useSubjects } from '../store'
import { IconCamera, IconImage, IconCrop, IconTarget, IconSparkle } from '../icons'

type Mode = 'photo' | 'text' | 'batch'

export default function Upload() {
  const nav = useNavigate()
  const goBack = useGoBack('/wrong')
  const toast = useToast()
  const subjects = useSubjects()
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
  const [detected, setDetected] = useState<any[]>([])
  const [picks, setPicks] = useState<Record<number, { on: boolean; hint: string }>>({})

  const afterPick = async (files: FileList | null, croppable: boolean) => {
    if (!files?.length) return
    const f = files[0]
    if (croppable) {
      setCropFile(f)
      return
    }
    const arr = await Promise.all(Array.from(files).slice(0, 12).map((x) => compressImage(x)))
    setImages((prev) => [...prev, ...arr].slice(0, 12))
  }


  const detectQuestions = async () => {
    if (!images.length) return toast('请先拍照/选图')
    setBusy(true)
    setStage('AI 识别题目清单…')
    try {
      const image_ids = await api.upload(images)
      const res = await api.post<{ questions: any[] }>('/api/wrong-questions/detect-questions', {
        subject: subject === '自动识别' ? '' : subject,
        image_ids,
      })
      const qs = res.questions || []
      setDetected(qs)
      setPicks(Object.fromEntries(qs.map((q: any, i: number) => [i, { on: false, hint: '' }])))
      if (!qs.length) toast('没有识别出题目，请换更清晰的照片')
    } catch (e: any) {
      toast(e.message || '识别失败')
    } finally {
      setBusy(false)
      setStage('')
    }
  }

  const analyzeSelected = async () => {
    const chosen = detected
      .map((q, i) => ({ q, i, pick: picks[i] }))
      .filter((x) => x.pick?.on && x.q.question_text)
    if (!chosen.length) return toast('请至少勾选一道题')
    setBusy(true)
    setResults([])
    try {
      const image_ids = await api.upload(images)
      const out: any[] = []
      for (const c of chosen) {
        setStage(`分析第 ${c.i + 1} 题…`)
        const res = await api.post<{ item: any }>('/api/wrong-questions/analyze-selected', {
          question_text: c.q.question_text,
          wrong_hint: c.pick.hint,
          subject: subject === '自动识别' ? '' : subject,
          image_ids,
        })
        out.push(res.item)
      }
      setResults(out)
      toast(`分析完成，共 ${out.length} 题`)
    } catch (e: any) {
      toast(e.message || '分析失败')
    } finally {
      setBusy(false)
      setStage('')
    }
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

const MODES: { key: Mode; label: string; icon: React.ReactNode }[] = [
    { key: 'photo', label: '拍单题', icon: <IconCamera size={15} /> },
    { key: 'batch', label: '整页多题', icon: <IconImage size={15} /> },
    { key: 'text', label: '手动输入', icon: <IconSparkle size={15} /> },
  ]

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar title="录入错题" back={goBack} />

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
                          }}
          >
            {m.label}
          </Btn>
        ))}
      </div>

      <div className="col">
        <SelectField label="学科" value={subject} options={['自动识别', ...subjects]} onChange={setSubject} />

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

        {mode === 'batch' ? (
          <>
            <Btn variant="filled" block disabled={busy} onClick={detectQuestions}>
              {busy ? stage || '处理中…' : '① 识别这页的题目清单'}
            </Btn>
            {detected.length > 0 && (
              <div className="col">
                <div className="caption">② 勾选做错的题，并简单说说大致错因：</div>
                {detected.map((q: any, i: number) => (
                  <CardView key={i} variant={picks[i]?.on ? 'elevated' : 'outlined'}>
                    <div className="row" style={{ gap: 8 }}>
                      <input
                        type="checkbox"
                        checked={!!picks[i]?.on}
                        onChange={(e) =>
                          setPicks({ ...picks, [i]: { ...picks[i], on: e.target.checked, hint: picks[i]?.hint || '' } })
                        }
                        style={{ width: 20, height: 20 }}
                      />
                      <div style={{ flex: 1, lineHeight: 1.5 }}>
                        <b>#{q.index || i + 1}</b> {q.question_text}
                        {q.knowledge_point && <div className="caption">涉及：{q.knowledge_point}</div>}
                      </div>
                    </div>
                    {picks[i]?.on && (
                      <input
                        value={picks[i]?.hint || ''}
                        onChange={(e) =>
                          setPicks({ ...picks, [i]: { ...picks[i], hint: e.target.value } })
                        }
                        placeholder="大致错因（可选）：如‘第二步算错了’"
                        style={{
                          width: '100%', marginTop: 8, minHeight: 40, padding: '8px 12px',
                          borderRadius: 12, border: '1.5px solid var(--m3e-sys-color-outline-variant)',
                          background: 'var(--m3e-sys-color-surface)', font: 'inherit',
                        }}
                      />
                    )}
                  </CardView>
                ))}
                <Btn variant="filled" block disabled={busy} onClick={analyzeSelected}>
                  {busy ? stage || '分析中…' : '③ 分析我选的题'}
                </Btn>
              </div>
            )}
          </>
        ) : (
          <Btn variant="filled" block disabled={busy} onClick={analyze}>
            {busy ? stage || 'AI 分析中…' : 'AI 分析这道错题'}
          </Btn>
        )}

        {busy && (
          <div className="row" style={{ justifyContent: 'center', padding: 10 }}>
            <Loading text={stage || '处理中…'} />
          </div>
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
