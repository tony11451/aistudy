import { FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, compressImage, streamChat } from '../api'
import { Loading, Markdown, TopBar } from '../components'
import { SUBJECTS } from '../constants'
import { useAuth, useToast } from '../store'

interface Msg {
  id?: number
  role: string
  content: string
  images?: number[]
  streaming?: boolean
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
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api
      .get<any>('/api/settings')
      .then((s) => setAiReady(!!s?.effective?.has_key && !!s?.effective?.chat_model))
      .catch(() => {})
  }, [])

  useEffect(() => {
    const boot = async () => {
      try {
        if (id) {
          const res = await api.get<any>(`/api/chat/conversations/${id}`)
          setConv(res.conversation)
          setMessages(res.messages)
          setIniting(false)
          return
        }
        const kp = params.get('kp')
        const wrong = params.get('wrong')
        const subject = params.get('subject') || ''
        if (kp) {
          const c = await api.post<any>('/api/chat/conversations', {
            title: `深聊 · ${kp}`,
            subject,
            grade: user?.grade || '',
            context_kind: 'knowledge',
            context_ref: kp,
          })
          setConv(c)
          setIniting(false)
          nav(`/chat/${c.id}`, { replace: true })
        } else if (wrong) {
          const w = await api.get<any>(`/api/wrong-questions/${wrong}`)
          const c = await api.post<any>('/api/chat/conversations', {
            title: `错题 · ${(w.question_text || '这道题').slice(0, 12)}`,
            subject: subject || w.subject,
            grade: user?.grade || '',
            context_kind: 'wrong_question',
            context_ref: String(wrong),
          })
          setConv(c)
          setIniting(false)
          nav(`/chat/${c.id}`, { replace: true })
        } else {
          const c = await api.post<any>('/api/chat/conversations', {
            title: '新对话',
            grade: user?.grade || '',
          })
          setConv(c)
          setIniting(false)
          nav(`/chat/${c.id}`, { replace: true })
        }
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

  const send = async (e?: FormEvent | string) => {
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
    await streamChat(conv.id, { content, image_ids }, {
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
      onError: (msg) => {
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
    })
  }

  const pickImages = async (files: FileList | null) => {
    if (!files) return
    const arr = await Promise.all(Array.from(files).slice(0, 3).map((f) => compressImage(f)))
    setImages((prev) => [...prev, ...arr].slice(0, 3))
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
        background: 'var(--md-surface)',
      }}
    >
      <TopBar
        title={conv?.title || (initing ? '创建对话…' : 'AI 对话')}
        back={() => nav('/chat')}
        right={
          conv && (
            <span className="badge badge-primary" style={{ marginRight: 8 }}>
              {conv.context_kind === 'knowledge'
                ? `🧠 ${conv.context_ref}`
                : conv.subject || '综合'}
            </span>
          )
        }
      />

      <div className="col" style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 20px', gap: 12 }}>
        {!aiReady && !initing && (
          <div
            className="md-card"
            style={{ background: 'var(--md-warning-container)', color: 'var(--md-warning)' }}
          >
            <div className="title-strong">⚠️ AI 接口未配置</div>
            <p style={{ margin: '6px 0 10px', lineHeight: 1.5 }}>
              还没有填写 API Key / 模型，AI 无法回答问题。请先到设置里配置。
            </p>
            <button
              className="md-btn md-btn-filled md-btn-sm"
              onClick={() => nav('/settings')}
            >
              去配置 API
            </button>
          </div>
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
                <button
                  key={q}
                  className="md-card md-card-outlined md-card-tappable"
                  style={{ textAlign: 'left' }}
                  disabled={busy}
                  onClick={() => send(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'bubble bubble-user' : 'bubble bubble-ai'}>
            {m.role === 'assistant' ? (
              m.content ? (
                <Markdown text={m.content} />
              ) : (
                <span className="muted">思考中…</span>
              )
            ) : (
              m.content
            )}
            {m.streaming && m.content && (
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 14,
                  background: 'var(--md-primary)',
                  marginLeft: 3,
                  animation: 'blink 1s infinite',
                }}
              />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={send}
        style={{
          padding: '10px 12px calc(12px + env(safe-area-inset-bottom, 0px))',
          background: 'var(--md-surface-container)',
          borderTop: '1px solid var(--md-outline-variant)',
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
          <button
            type="button"
            className="md-iconbtn"
            onClick={() => fileRef.current?.click()}
            title="发送图片"
          >
            📷
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            multiple
            hidden
            onChange={(e) => pickImages(e.target.files)}
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
            placeholder="问学习问题…"
            rows={1}
            style={{
              flex: 1,
              minHeight: 44,
              maxHeight: 120,
              padding: '11px 16px',
              borderRadius: 'var(--md-shape-full)',
              border: '1.5px solid var(--md-outline-variant)',
              background: 'var(--md-surface)',
              outline: 'none',
              resize: 'none',
            }}
          />
          <button
            type="submit"
            className="md-btn md-btn-filled"
            style={{ minWidth: 46, padding: '0 16px' }}
            disabled={busy || (!input.trim() && !images.length)}
          >
            {busy ? '···' : '➤'}
          </button>
        </div>
      </form>
      <style>{`@keyframes blink { 50% { opacity: 0 } }`}</style>
    </div>
  )
}
