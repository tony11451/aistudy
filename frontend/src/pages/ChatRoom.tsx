import { FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, compressImage, streamChat } from '../api'
import { Btn, CardView, ChipFilter, ChipRow, Loading, Sheet, TopBar, Badge, IconBtn } from '../ui'
import { Markdown } from '../components'
import { ImageViewer } from '../viewer'
import { useAuth, useToast } from '../store'
import {
  IconCamera,
  IconCheck,
  IconClose,
  IconCopy,
  IconRefresh,
  IconSend,
  IconSparkle,
  IconTarget,
  IconLightbulb,
  IconImage,
} from '../icons'

interface Msg {
  id?: number
  role: string
  content: string
  images?: number[]
  streaming?: boolean
}

interface NodeProposal {
  action: 'add' | 'update' | 'delete'
  node_id?: number
  subject: string
  parent_name: string
  name: string
  node_type: 'knowledge' | 'weakness'
  reason: string
  children?: { name: string; node_type: 'knowledge' | 'weakness' }[]
}

export default function ChatRoom() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const [conv, setConv] = useState<any>(null)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [images, setImages] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [initing, setIniting] = useState(!!(params.get('kp') || params.get('wrong')))
  const [aiReady, setAiReady] = useState(true)
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [showModel, setShowModel] = useState(false)
  const [proposals, setProposals] = useState<NodeProposal[] | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [summarizing, setSummarizing] = useState(false)
  const [viewImg, setViewImg] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api
      .get<any>('/api/settings')
      .then((s) => {
        setAiReady(!!s?.effective?.has_key && !!s?.effective?.chat_model)
        const list: string[] = s?.models || []
        setModels(list.filter(Boolean))
        const eff = s?.effective?.chat_model || ''
        setModel((s as any)?.conversation_model || eff)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const boot = async () => {
      try {
        if (id) {
          const res = await api.get<any>(`/api/chat/conversations/${id}`)
          setConv(res.conversation)
          setMessages(res.messages)
          if (res.conversation?.model_name) setModel(res.conversation.model_name)
          setIniting(false)
          return
        }
        const kp = params.get('kp')
        const wrong = params.get('wrong')
        const subject = params.get('subject') || ''
        const payload: any = {
          title: kp ? `深聊 · ${kp}` : wrong ? '错题追问' : '新对话',
          subject,
          grade: user?.grade || '',
        }
        if (kp) {
          payload.context_kind = 'knowledge'
          payload.context_ref = kp
        } else if (wrong) {
          const w = await api.get<any>(`/api/wrong-questions/${wrong}`)
          payload.title = `错题 · ${(w.question_text || '这道题').slice(0, 12)}`
          payload.subject = subject || w.subject
          payload.context_kind = 'wrong_question'
          payload.context_ref = String(wrong)
        }
        const c = await api.post<any>('/api/chat/conversations', payload)
        setConv(c)
        setIniting(false)
        nav(`/chat/${c.id}`, { replace: true })
      } catch (e: any) {
        toast(e.message || '创建对话失败')
        setIniting(false)
        nav('/chat')
      }
    }
    boot()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (e?: FormEvent | string, overrideModel?: string) => {
    if (typeof e === 'object' && e?.preventDefault) e.preventDefault()
    const override = typeof e === 'string' ? e : ''
    const content = (override || input).trim()
    if (!content && !images.length) return
    if (!conv || busy) return
    const files = images
    setInput('')
    setImages([])
    setBusy(true)
    let image_ids: number[] = []
    if (files.length) {
      try {
        image_ids = await api.upload(files)
      } catch (err: any) {
        toast(err.message || '图片上传失败')
        setBusy(false)
        return
      }
    }
    setMessages((m) => [
      ...m,
      { role: 'user', content, images: image_ids },
      { role: 'assistant', content: '', streaming: true },
    ])
    const handlers = {
      onDelta: (t: string) =>
        setMessages((m) => {
          const copy = [...m]
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = { ...last, content: last.content + t }
          return copy
        }),
      onDone: () => {
        setMessages((m) => {
          const copy = [...m]
          copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false }
          return copy
        })
        setBusy(false)
      },
      onError: (msg: string) => {
        toast(msg)
        setMessages((m) => {
          const copy = [...m]
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = {
            ...last,
            streaming: false,
            content: last.content || `⚠️ ${msg}`,
          }
          return copy
        })
        setBusy(false)
      },
    }
    try {
      await streamChat(conv.id, { content, image_ids, model: overrideModel || model }, handlers)
    } catch (err: any) {
      handlers.onError(err?.message || '网络异常，请重试')
    }
  }

  const regenerate = async (index: number) => {
    if (busy) return
    const before = messages.slice(0, index)
    const userMsg = [...before].reverse().find((m) => m.role === 'user')
    if (!userMsg) return
    setMessages(before.slice(0, before.lastIndexOf(userMsg)))
    setBusy(true)
    setMessages((m) => [...m, { role: 'assistant', content: '', streaming: true }])
    const onError = (msg: string) => {
      toast(msg)
      setBusy(false)
    }
    try {
      await streamChat(conv.id, { content: userMsg.content, image_ids: userMsg.images || [], model }, {
        onDelta: (t) =>
          setMessages((m) => {
            const copy = [...m]
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, content: last.content + t }
            return copy
          }),
        onDone: () => {
          setMessages((m) => {
            const copy = [...m]
            copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false }
            return copy
          })
          setBusy(false)
        },
        onError,
      })
    } catch (err: any) {
      onError(err?.message || '网络异常，请重试')
    }
  }

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast('已复制')
    } catch {
      toast('复制失败')
    }
  }

  const summarizeToNodes = async () => {
    setSummarizing(true)
    try {
      const res = await api.post<{ proposals: NodeProposal[] }>(
        `/api/chat/conversations/${conv.id}/summarize`,
        {},
      )
      const list = res.proposals || []
      if (!list.length) {
        toast('本次对话暂无可沉淀的知识点')
      } else {
        setProposals(list)
        setSelected(new Set(list.map((_, i) => i)))
      }
    } catch (e: any) {
      toast(e.message || '总结失败')
    } finally {
      setSummarizing(false)
    }
  }

  const applyProposals = async () => {
    const chosen = (proposals || []).filter((_, i) => selected.has(i))
    try {
      await api.post('/api/knowledge/nodes/apply', { proposals: chosen })
      toast(`已添加 ${chosen.length} 个知识点到图谱`)
      setProposals(null)
    } catch (e: any) {
      toast(e.message || '保存失败')
    }
  }

  const quickAsks = [
    '帮我分析我的主要弱点',
    '给我制定本周刷题计划',
    '这个知识点的典型题型有哪些？',
    '我总是在考试时紧张，怎么办？',
  ]

  return (
    <div
      style={{
        height: '100dvh',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--m3e-sys-color-surface)',
      }}
    >
      <TopBar
        title={conv?.title || (initing ? '创建对话…' : 'AI 对话')}
        back={() => nav('/chat')}
        right={
          <div className="row" style={{ gap: 6 }}>
            {conv && (
              <Badge tone="primary">
                {conv.context_kind === 'knowledge' ? `🧠 ${conv.context_ref}` : conv.subject || '综合'}
              </Badge>
            )}
            {models.length > 1 && (
              <Btn variant="text" sm onClick={() => setShowModel(true)}>
                {model ? model.slice(0, 10) : '模型'}
              </Btn>
            )}
          </div>
        }
      />

      {/* 顶部常用操作条 */}
      {messages.filter((m) => m.role === 'assistant' && m.content).length > 0 && (
        <div className="row" style={{ gap: 8, padding: '8px 12px', overflowX: 'auto', flexWrap: 'nowrap' }}>
          <Btn variant="tonal" sm onClick={summarizeToNodes} disabled={summarizing} leadingIcon={<IconSparkle size={15} />}>
            {summarizing ? '总结中…' : '总结成知识点'}
          </Btn>
          <Btn
            variant="outlined"
            sm
            leadingIcon={<IconTarget size={15} />}
            onClick={async () => {
              await api.post('/api/goals/generate', { subject: conv?.subject || '' })
              toast('已生成刷题目标，去「我的」查看')
            }}
          >
            生成刷题目标
          </Btn>
          <Btn
            variant="outlined"
            sm
            leadingIcon={<IconLightbulb size={15} />}
            onClick={() => send('请总结这轮对话涉及的答题方法，区分具体方法和通用方法')}
          >
            总结答题方法
          </Btn>
        </div>
      )}

      <div className="col" style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 20px', gap: 12 }}>
        {!aiReady && !initing && (
          <CardView variant="elevated" style={{ background: 'var(--m3e-sys-color-tertiary-container)' }}>
            <div className="title-strong">⚠️ AI 接口未配置</div>
            <p style={{ margin: '6px 0 10px', lineHeight: 1.5 }}>
              还没有填写 API Key / 模型，AI 无法回答问题。请先到设置里配置。
            </p>
            <Btn variant="filled" sm onClick={() => nav('/settings')}>
              去配置 API
            </Btn>
          </CardView>
        )}
        {initing && <Loading text="AI 正在准备…" />}
        {messages.length === 0 && !initing && (
          <div className="col" style={{ gap: 10, marginTop: 20 }}>
            <div className="hero" style={{ padding: 18 }}>
              <h2 style={{ fontSize: '1.35rem' }}>嗨，我是你的学习导师 👋</h2>
              <p style={{ marginTop: 6 }}>
                {conv?.context_kind === 'knowledge'
                  ? `我们就「${conv.context_ref}」这个知识点展开聊聊吧，可以直接问我概念、题型和易错点。`
                  : '我知道你的学习进度和弱点，可以问我任何学习问题。'}
              </p>
            </div>
            <div className="caption">试试这些（点击直接提问）：</div>
            <div className="col" style={{ gap: 8 }}>
              {quickAsks.map((q) => (
                <CardView key={q} variant="outlined" onClick={() => !busy && send(q)}>
                  {q}
                </CardView>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'bubble bubble-user' : 'bubble bubble-ai'}>
            {(m.images || []).length > 0 && (
              <div className="img-grid" style={{ gridTemplateColumns: 'repeat(3,80px)', marginBottom: 8 }}>
                {(m.images || []).map((iid, j) => {
                  const src = `/api/images/u${user?.id}_${iid}.jpg`
                  return (
                    <div className="img-cell" key={j} onClick={() => setViewImg(src)}>
                      <img src={src} alt="" />
                    </div>
                  )
                })}
              </div>
            )}
            {m.role === 'assistant' ? (
              m.content ? (
                <Markdown text={m.content} />
              ) : (
                <span className="muted">思考中…</span>
              )
            ) : (
              m.content
            )}
            {m.streaming && m.content && <span className="stream-caret" />}
            {m.role === 'assistant' && !m.streaming && m.content && (
              <div className="bubble-actions">
                <button className="bubble-action-btn" onClick={() => copyText(m.content)}>
                  <IconCopy size={13} /> 复制
                </button>
                <button className="bubble-action-btn" onClick={() => regenerate(i)} disabled={busy}>
                  <IconRefresh size={13} /> 重新生成
                </button>
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={send}
        style={{
          padding: '10px 12px calc(12px + env(safe-area-inset-bottom, 0px))',
          background: 'var(--m3e-sys-color-surface-container)',
          borderTop: '1px solid var(--m3e-sys-color-outline-variant)',
        }}
      >
        {images.length > 0 && (
          <div className="img-grid" style={{ marginBottom: 8, gridTemplateColumns: 'repeat(3,80px)' }}>
            {images.map((img, i) => (
              <div className="img-cell" key={i}>
                <img src={URL.createObjectURL(img)} alt="" />
                <button
                  type="button"
                  className="remove"
                  onClick={() => setImages(images.filter((_, j) => j !== i))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="row" style={{ gap: 8 }}>
          <IconBtn icon={<IconCamera size={20} />} label="拍照提问" onClick={() => fileRef.current?.click()} />
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            multiple
            hidden
            onChange={async (e) => {
              if (!e.target.files) return
              const arr = await Promise.all(
                Array.from(e.target.files).slice(0, 3).map((f) => compressImage(f)),
              )
              setImages((prev) => [...prev, ...arr].slice(0, 3))
            }}
          />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && window.innerWidth > 640) {
                e.preventDefault()
                send()
              }
            }}
            placeholder="问学习问题…（支持 Markdown 与 $公式$）"
            rows={1}
            style={{
              flex: 1,
              minHeight: 44,
              maxHeight: 120,
              padding: '11px 16px',
              borderRadius: 999,
              border: '1.5px solid var(--m3e-sys-color-outline-variant)',
              background: 'var(--m3e-sys-color-surface)',
              outline: 'none',
              resize: 'none',
              font: 'inherit',
            }}
          />
          <Btn variant="filled" type="submit" disabled={busy || (!input.trim() && !images.length)}>
            <IconSend size={18} />
          </Btn>
        </div>
      </form>

      {/* 模型切换 */}
      <Sheet open={showModel} onClose={() => setShowModel(false)} title="选择模型（本会话）">
        <ChipRow>
          {models.map((mname) => (
            <ChipFilter
              key={mname}
              label={mname}
              selected={model === mname}
              onClick={() => {
                setModel(mname)
                setShowModel(false)
                api.put(`/api/chat/conversations/${conv.id}`, { model_name: mname }).catch(() => {})
                toast(`已切换到 ${mname}`)
              }}
            />
          ))}
        </ChipRow>
        <p className="caption" style={{ marginTop: 8 }}>
          仅影响当前对话；全局默认模型在「设置 → 模型管理」中配置。
        </p>
      </Sheet>

      {/* 总结入库确认 */}
      <Sheet open={!!proposals} onClose={() => setProposals(null)} title="沉淀到知识图谱">
        <p className="caption" style={{ marginBottom: 10 }}>
          AI 从本次对话总结出以下知识点/弱点，勾选后加入对应学科图谱：
        </p>
        <div className="col">
          {(proposals || []).map((p, i) => (
            <CardView key={i} variant={selected.has(i) ? 'elevated' : 'outlined'} onClick={() => {
              const next = new Set(selected)
              next.has(i) ? next.delete(i) : next.add(i)
              setSelected(next)
            }}>
              <div className="row" style={{ gap: 8 }}>
                {selected.has(i) ? <IconCheck size={18} /> : <span style={{ width: 18 }} />}
                <Badge tone="primary">{p.subject}</Badge>
                <Badge tone={p.node_type === 'weakness' ? 'weak' : 'neutral'}>
                  {p.node_type === 'weakness' ? '弱点' : '知识点'}
                </Badge>
                <span className="spacer" />
                <span className="caption">{p.action === 'update' ? '更新' : p.action === 'delete' ? '删除' : '新增'}</span>
              </div>
              <div className="title-strong" style={{ margin: '8px 0 2px' }}>
                {p.parent_name ? `${p.parent_name} → ` : ''}
                {p.name}
              </div>
              {p.children && p.children.length > 0 && (
                <div className="caption">
                  二级：{p.children.map((c) => c.name).join('、')}
                </div>
              )}
              <div className="caption" style={{ marginTop: 4 }}>{p.reason}</div>
            </CardView>
          ))}
        </div>
        <div className="row" style={{ marginTop: 14, gap: 10 }}>
          <Btn variant="text" onClick={() => setProposals(null)}>
            <IconClose size={16} /> 取消
          </Btn>
          <span className="spacer" />
          <Btn variant="filled" onClick={applyProposals}>
            <IconCheck size={16} /> 添加选中（{selected.size}）
          </Btn>
        </div>
      </Sheet>

      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}
    </div>
  )
}
