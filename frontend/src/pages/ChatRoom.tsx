import { FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, compressImage, providersApi, changesApi, libraryApi, streamChat } from '../api'
import { Btn, CardView, ChipFilter, ChipRow, Field, Loading, Sheet, TopBar, Badge, IconBtn } from '../ui'
import { Markdown, useAsync } from '../components'
import { ImageViewer } from '../viewer'
import { useAuth, useToast, notifyChatReady, clearChatReady } from '../store'
import {
  IconCamera,
  IconCheck,
  IconClose,
  IconCopy,
  IconImage,
  IconRefresh,
  IconSend,
  IconSparkle,
  IconTarget,
  IconLightbulb,
} from '../icons'

interface Msg {
  id?: number
  role: string
  content: string
  images?: number[]
  streaming?: boolean
  meta?: { skills?: any[]; change_ids?: number[]; changes?: any[] }
}

interface ChangeCard {
  change_id?: number
  description: string
  reason?: string
  action?: string
  undone?: boolean
}

const SKILL_BUTTONS = [
  {
    key: 'organize',
    icon: <IconSparkle size={15} />,
    label: '整理弱点',
    prompt:
      '请帮我整理知识图谱中的弱点：先用 read_mindmap 读取图谱，然后用 reorganize_weaknesses 精简——合并重复的、把拿不准的降级为疑似、删除确实无关的，并说明每一步理由。',
  },
  {
    key: 'reeval',
    icon: <IconTarget size={15} />,
    label: '按错题重评',
    prompt:
      '请根据我的历史错题重新评估弱点：先用 read_wrong_questions 看最近的错题，再用 re_evaluate 或 update_node 更新相关节点的置信度和掌握度，说明依据。',
  },
  {
    key: 'summarize',
    icon: <IconCheck size={15} />,
    label: '总结成知识点',
    prompt:
      '请把本次对话的内容沉淀为知识图谱节点：用 create_node 创建知识点（大方向命名，必要时带二级子方向），确实体现薄弱的创建为 weakness，并说明每个节点的依据。',
  },
  {
    key: 'goal',
    icon: <IconTarget size={15} />,
    label: '生成刷题目标',
    prompt:
      '请根据我的弱点用 create_goal 制定 2-3 个刷题目标（专攻题型、做法、验收标准），并解释为什么这样定。',
  },
  {
    key: 'method',
    icon: <IconLightbulb size={15} />,
    label: '总结答题方法',
    prompt:
      '请总结这轮对话涉及的答题方法，区分「具体方法」和「通用方法」，并用 save_method 保存到方法库。',
  },
]

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
  const [liveSkills, setLiveSkills] = useState<any[]>([])
  const [liveChanges, setLiveChanges] = useState<ChangeCard[]>([])
  const [modelRef, setModelRef] = useState('')
  const [providers, setProviders] = useState<any[]>([])
  const [showModel, setShowModel] = useState(false)
  const [viewImg, setViewImg] = useState<string | null>(null)
  const [refs, setRefs] = useState<any[]>([])
  const [showRefs, setShowRefs] = useState(false)
  const [refQuery, setRefQuery] = useState('')
  const [summaries, setSummaries] = useState<any[]>([])
  const [showSummaries, setShowSummaries] = useState(false)
  const [sumBusy, setSumBusy] = useState(false)
  const sentAutoRef = useRef(false)
  const pendingPromptRef = useRef('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const albumRef = useRef<HTMLInputElement>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    clearChatReady()
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    Promise.all([api.get<any>('/api/settings'), providersApi.list().catch(() => null)])
      .then(([s, p]) => {
        setAiReady(!!s?.effective?.has_key && !!s?.effective?.chat_model)
        if (p?.providers) setProviders(p.providers)
        setModelRef((s as any)?.current_model_ref || p?.current_model_ref || '')
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const boot = async () => {
      try {
        if (id && id !== 'new') {
          const res = await api.get<any>(`/api/chat/conversations/${id}`)
          setConv(res.conversation)
          setMessages(res.messages)
          if (res.conversation?.model_name) setModelRef(res.conversation.model_name)
          setIniting(false)
          return
        }
        const kp = params.get('kp')
        const wrong = params.get('wrong')
        const ctxPage = params.get('ctx')
        const teacherSubject = params.get('teacher')
        const autoPrompt = params.get('prompt') || ''
        const subject = params.get('subject') || ''
        if (teacherSubject) {
          // 老师常驻流（v6：不单开对话）
          const t = await api.post<any>('/api/chat/teacher-thread', { subject: teacherSubject })
          pendingPromptRef.current = autoPrompt
          nav(`/chat/${t.id}`, { replace: true })
          return
        }
        const payload: any = {
          title: kp ? `深聊 · ${kp}` : wrong ? '错题追问' : ctxPage ? `AI · ${ctxPage}` : '新对话',
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
        } else if (ctxPage) {
          payload.context_kind = 'page'
          payload.context_ref = ctxPage
        }
        if (autoPrompt) pendingPromptRef.current = autoPrompt
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

  // 自动首问（全局浮球/预填提示词场景）
  useEffect(() => {
    if (conv && pendingPromptRef.current && !sentAutoRef.current && !busy) {
      sentAutoRef.current = true
      const p = pendingPromptRef.current
      pendingPromptRef.current = ''
      send(p)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv, busy])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, liveSkills, liveChanges])

  const send = async (e?: FormEvent | string) => {
    if (typeof e === 'object' && e?.preventDefault) e.preventDefault()
    const override = typeof e === 'string' ? e : ''
    let content = (override || input).trim()
    // @引用：把所选错题/档案内容随消息带给 AI（需求 4）
    const usedRefs = refs
    if (usedRefs.length) {
      const refText = usedRefs
        .map((r: any) => `- 【${r.kindLabel}】${r.title}${r.text ? '：' + r.text.slice(0, 150) : ''}`)
        .join('\n')
      content = `${content || '请结合参考内容分析'}\n\n[参考内容]\n${refText}`
      setRefs([])
    }
    if (!content && !images.length) return
    if (!conv || busy) return
    const files = images
    setInput('')
    setImages([])
    setBusy(true)
    setLiveSkills([])
    setLiveChanges([])
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
    const finish = () => {
      if (!mountedRef.current) {
        notifyChatReady()
        return
      }
      setMessages((m) => {
        const copy = [...m]
        copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false }
        return copy
      })
      setBusy(false)
    }
    const onError = (msg: string) => {
      if (!mountedRef.current) {
        notifyChatReady()
        return
      }
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
    }
    try {
      await streamChat(conv.id, { content, image_ids, model: modelRef }, {
        onDelta: (t) =>
          setMessages((m) => {
            const copy = [...m]
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, content: last.content + t }
            return copy
          }),
        onSkill: (s) =>
          setLiveSkills((prev) => {
            const idx = prev.findIndex((x) => x.name === s.name && x.status === 'start')
            if (s.status === 'done' || s.status === 'error') {
              if (idx >= 0) {
                const copy = [...prev]
                copy[idx] = { ...copy[idx], ...s }
                return copy
              }
            }
            return [...prev, s]
          }),
        onChange: (c) => setLiveChanges((prev) => [...prev, c]),
        onDone: finish,
        onError,
      })
    } catch (err: any) {
      onError(err?.message || '网络异常，请重试')
    }
  }

  const regenerate = async (index: number) => {
    if (busy) return
    const before = messages.slice(0, index)
    const userMsg = [...before].reverse().find((m) => m.role === 'user')
    if (!userMsg) return
    setMessages(before.slice(0, before.lastIndexOf(userMsg)))
    setBusy(true)
    setLiveSkills([])
    setLiveChanges([])
    setMessages((m) => [...m, { role: 'assistant', content: '', streaming: true }])
    const onError = (msg: string) => {
      if (!mountedRef.current) {
        notifyChatReady()
        return
      }
      toast(msg)
      setBusy(false)
    }
    try {
      await streamChat(conv.id, { content: userMsg.content, image_ids: userMsg.images || [], model: modelRef }, {
        onDelta: (t) =>
          setMessages((m) => {
            const copy = [...m]
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, content: last.content + t }
            return copy
          }),
        onDone: () => {
          if (!mountedRef.current) {
            notifyChatReady()
            return
          }
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

  const undoChange = async (changeId?: number) => {
    if (!changeId) return
    try {
      await changesApi.undo(changeId)
      toast('已撤销该变更')
      setLiveChanges((prev) =>
        prev.map((c) => (c.change_id === changeId ? { ...c, undone: true } : c)),
      )
    } catch (e: any) {
      toast(e.message || '撤销失败')
    }
  }

  const modelNameOf = (ref: string) => {
    const [pid, model] = ref.split('::')
    const p = providers.find((x) => String(x.id) === pid)
    return model ? `${p?.name || '?'} · ${model}` : ref
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
          <div className="row" style={{ gap: 2 }}>
            <Btn variant="text" sm onClick={() => {
              setShowSummaries(true)
              api.get<any>(`/api/chat/conversations/${conv?.id}/summaries`)
                .then(setSummaries)
                .catch(() => setSummaries([]))
            }}>
              摘要
            </Btn>
            <Btn variant="text" sm onClick={() => setShowModel(true)}>
              {modelRef ? modelNameOf(modelRef).slice(0, 12) : '模型'}
            </Btn>
          </div>
        }
      />

      {/* 技能按钮（预置指令 → AI 自由调用技能） */}
      <div className="row" style={{ gap: 8, padding: '8px 12px', overflowX: 'auto', flexWrap: 'nowrap' }}>
        {SKILL_BUTTONS.map((b) => (
          <Btn key={b.key} variant="tonal" sm leadingIcon={b.icon} disabled={busy || !conv}
               onClick={() => send(b.prompt)}>
            {b.label}
          </Btn>
        ))}
      </div>

      <div className="col" style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 20px', gap: 12 }}>
        {!aiReady && !initing && (
          <CardView variant="elevated" style={{ background: 'var(--m3e-sys-color-tertiary-container)' }}>
            <div className="title-strong">⚠️ AI 接口未配置</div>
            <p style={{ margin: '6px 0 10px', lineHeight: 1.5 }}>
              还没有可用模型，请先到设置里添加供应商与模型。
            </p>
            <Btn variant="filled" sm onClick={() => nav('/settings')}>去配置</Btn>
          </CardView>
        )}
        {initing && <Loading text="AI 正在准备…" />}
        {messages.length === 0 && !initing && (
          <div className="col" style={{ gap: 10, marginTop: 20 }}>
            <div className="hero" style={{ padding: 18 }}>
              <h2 style={{ fontSize: '1.35rem' }}>嗨，我是你的学习导师 👋</h2>
              <p style={{ marginTop: 6 }}>
                我能读取你的图谱、错题和档案来回答问题，也能帮你整理弱点、重评掌握度——
                所有修改都会显示变更卡，可随时撤销。
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
            {/* 历史消息里的技能执行记录（需求 3） */}
            {m.role === 'assistant' && !m.streaming && (m.meta?.skills || []).length > 0 && (
              <div className="col" style={{ gap: 4, marginTop: 8 }}>
                {(m.meta?.skills || []).map((s: any, j: number) => (
                  <div key={j} className="badge" style={{ minHeight: 30 }}>
                    {s.status === 'start' ? '🔧' : s.status === 'error' ? '⚠️' : '✓'}
                    <span>{s.summary || `${s.name} ${s.status}`}</span>
                  </div>
                ))}
              </div>
            )}
            {/* 历史消息里的变更卡（需求 3/4） */}
            {m.role === 'assistant' && !m.streaming && (m.meta?.changes || []).length > 0 && (
              <div className="col" style={{ gap: 8, marginTop: 8 }}>
                {(m.meta?.changes || []).map((c: any, j: number) => (
                  <CardView key={j} variant="elevated"
                            style={{ borderLeft: '4px solid var(--m3e-sys-color-primary)' }}>
                    <div className="row" style={{ gap: 8 }}>
                      <Badge tone="primary">AI 变更</Badge>
                      <span className="caption">{c.action}</span>
                      <span className="spacer" />
                      {c.change_id ? (
                        <button className="bubble-action-btn" onClick={() => undoChange(c.change_id)}>
                          撤销
                        </button>
                      ) : null}
                    </div>
                    <div style={{ marginTop: 6, lineHeight: 1.5 }}>{c.description}</div>
                    {c.reason && <div className="caption" style={{ marginTop: 4 }}>💡 {c.reason}</div>}
                  </CardView>
                ))}
              </div>
            )}
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

        {/* 实时技能执行条 */}
        {liveSkills.length > 0 && (
          <div className="col" style={{ gap: 6 }}>
            {liveSkills.map((s, i) => (
              <div key={i} className="badge" style={{ minHeight: 34 }}>
                {s.status === 'start' ? '🔧' : s.status === 'error' ? '⚠️' : '✓'}
                <span>
                  {s.status === 'start' ? `执行 ${s.name}…` : s.summary || `${s.name} ${s.status}`}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* 变更卡（AI 改了什么，可撤销） */}
        {liveChanges.length > 0 && (
          <div className="col" style={{ gap: 8 }}>
            {liveChanges.map((c, i) => (
              <CardView key={i} variant="elevated"
                        style={{ borderLeft: '4px solid var(--m3e-sys-color-primary)' }}>
                <div className="row" style={{ gap: 8 }}>
                  <Badge tone="primary">AI 变更</Badge>
                  <span className="caption">{c.action}</span>
                  <span className="spacer" />
                  {!c.undone && c.change_id ? (
                    <button className="bubble-action-btn" onClick={() => undoChange(c.change_id)}>
                      撤销
                    </button>
                  ) : (
                    <span className="caption">{c.undone ? '已撤销' : ''}</span>
                  )}
                </div>
                <div style={{ marginTop: 6, lineHeight: 1.5 }}>{c.description}</div>
                {c.reason && <div className="caption" style={{ marginTop: 4 }}>💡 {c.reason}</div>}
              </CardView>
            ))}
          </div>
        )}
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
        {refs.length > 0 && (
          <div className="row-wrap" style={{ marginBottom: 8 }}>
            {refs.map((r: any) => (
              <span key={r.kind + r.id} className="badge badge-primary" style={{ minHeight: 32 }}>
                📎 {r.kindLabel} · {r.title.slice(0, 10)}
                <button
                  style={{ border: 'none', background: 'none', color: 'inherit', marginLeft: 4, cursor: 'pointer' }}
                  onClick={() => setRefs((prev) => prev.filter((x) => !(x.kind === r.kind && x.id === r.id)))}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
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
          <IconBtn icon={<IconImage size={20} />} label="引用错题/档案" onClick={() => setShowRefs(true)} />
          <IconBtn icon={<IconCamera size={20} />} label="拍照提问" onClick={() => fileRef.current?.click()} />
          <IconBtn icon={<IconImage size={20} />} label="相册选图" onClick={() => albumRef.current?.click()} />
          <input
            ref={albumRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={async (e) => {
              if (!e.target.files) return
              const arr = await Promise.all(
                Array.from(e.target.files).slice(0, 9).map((f) => compressImage(f)),
              )
              setImages((prev) => [...prev, ...arr].slice(0, 9))
              e.target.value = ''
            }}
          />
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
                Array.from(e.target.files).slice(0, 9).map((f) => compressImage(f)),
              )
              setImages((prev) => [...prev, ...arr].slice(0, 9))
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
            placeholder="问学习问题…（AI 可读取图谱/错题）"
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

      {/* 模型切换（按供应商分组） */}
      <Sheet open={showModel} onClose={() => setShowModel(false)} title="选择模型">
        {providers.map((p) => (
          <div key={p.id} style={{ marginBottom: 10 }}>
            <div className="caption" style={{ margin: '4px 2px' }}>{p.name}</div>
            <ChipRow>
              {(p.model_names || (p.models || []).map((x: any) => x.name || x)).map((mname: string) => {
                const ref = `${p.id}::${mname}`
                return (
                  <ChipFilter
                    key={ref}
                    label={mname}
                    selected={modelRef === ref}
                    onClick={() => {
                      setModelRef(ref)
                      setShowModel(false)
                      if (conv) api.put(`/api/chat/conversations/${conv.id}`, { model_name: ref }).catch(() => {})
                      toast(`已切换到 ${p.name} · ${mname}`)
                    }}
                  />
                )
              })}
            </ChipRow>
          </div>
        ))}
        <p className="caption" style={{ marginTop: 8 }}>
          仅影响当前对话；全局默认模型在「设置 → 供应商」中修改。
        </p>
      </Sheet>

      {/* @引用：错题 / 档案库（需求 4） */}
      <Sheet open={showRefs} onClose={() => setShowRefs(false)} title="引用错题或档案内容">
        <div className="col">
          <Field label="搜索" value={refQuery} onChange={setRefQuery} placeholder="关键词" />
          <RefPicker
            query={refQuery}
            selected={refs}
            onToggle={(item: any) =>
              setRefs((prev) =>
                prev.some((r) => r.kind === item.kind && r.id === item.id)
                  ? prev.filter((r) => !(r.kind === item.kind && r.id === item.id))
                  : [...prev, item],
              )
            }
          />
          <Btn variant="filled" block onClick={() => setShowRefs(false)}>
            <IconCheck size={16} /> 加入引用（{refs.length}）
          </Btn>
        </div>
      </Sheet>

      {/* 对话摘要（需求 15：独立 Agent，结果不进消息流） */}
      <Sheet open={showSummaries} onClose={() => setShowSummaries(false)} title="对话摘要">
        <div className="col">
          <Btn variant="tonal" block disabled={sumBusy} onClick={async () => {
            setSumBusy(true)
            try {
              const s = await api.post<any>(`/api/chat/conversations/${conv?.id}/summary`, {})
              setSummaries((prev) => [s, ...prev])
              toast('摘要已生成')
            } catch (e: any) {
              toast(e.message || '生成失败')
            } finally {
              setSumBusy(false)
            }
          }}>
            {sumBusy ? 'AI 总结中…' : '生成本次对话摘要'}
          </Btn>
          {(summaries || []).map((s: any) => (
            <CardView key={s.id} variant="filled">
              <div className="caption">{(s.created_at || '').slice(0, 16).replace('T', ' ')}</div>
              <Markdown text={s.content} />
            </CardView>
          ))}
          {!summaries?.length && (
            <div className="caption">还没有摘要。让 AI 把这段对话的要点沉淀下来，方便以后回顾。</div>
          )}
        </div>
      </Sheet>

      {viewImg && (
        <ImageViewer
          src={viewImg}
          onClose={() => setViewImg(null)}
          onDownload={() => {
            const a = document.createElement('a')
            a.href = viewImg
            a.download = 'chat-image.jpg'
            a.click()
          }}
          onBookmark={async () => {
            await libraryApi.addBookmark({ target_type: 'image', target_id: 0, label: '聊天图片' })
            toast('已加书签')
          }}
        />
      )}
    </div>
  )
}


/** 引用选择器：历史错题 + 档案库内容（需求 4） */
function RefPicker({ query, selected, onToggle }: {
  query: string
  selected: any[]
  onToggle: (item: any) => void
}) {
  const wq = useAsync(
    () => api.get<any>('/api/wrong-questions?limit=20' + (query ? '&keyword=' + encodeURIComponent(query) : '')),
    [query],
  )
  const lib = useAsync(
    () => libraryApi.search({ q: query, limit: 20 }),
    [query],
  )
  const isSel = (kind: string, id: number) => selected.some((r) => r.kind === kind && r.id === id)
  return (
    <div className="col" style={{ maxHeight: '46vh', overflowY: 'auto' }}>
      <div className="caption">历史错题</div>
      {(wq.data?.items || []).map((w: any) => (
        <CardView key={'w' + w.id} variant={isSel('wrong', w.id) ? 'elevated' : 'outlined'}
                  onClick={() =>
                    onToggle({
                      kind: 'wrong',
                      kindLabel: '错题',
                      id: w.id,
                      title: (w.question_text || '错题 ' + w.id).slice(0, 20),
                      text: '错因：' + (w.wrong_reason || '').slice(0, 100),
                    })
                  }>
          <div className="text-ellipsis" style={{ fontWeight: 600 }}>{w.question_text || '错题 #' + w.id}</div>
          <div className="caption">{w.subject} · {(w.knowledge_points || []).join('、')}</div>
        </CardView>
      ))}
      <div className="caption">档案库</div>
      {(lib.data?.items || []).map((it: any) => (
        <CardView key={'l' + it.id} variant={isSel('lib', it.id) ? 'elevated' : 'outlined'}
                  onClick={() =>
                    onToggle({
                      kind: 'lib',
                      kindLabel: it.kind === 'attachment' ? '附件' : it.kind === 'text' ? '资料' : '图片',
                      id: it.id,
                      title: it.title,
                      text: (it.ocr_preview || it.content_preview || '').slice(0, 100),
                    })
                  }>
          <div className="text-ellipsis" style={{ fontWeight: 600 }}>{it.title}</div>
          <div className="caption">{it.subject} · {it.kind}</div>
        </CardView>
      ))}
    </div>
  )
}
