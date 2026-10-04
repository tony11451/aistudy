import { ReactNode, useEffect, useState } from 'react'

/** 极简 Markdown 渲染（无第三方依赖） */
export function Markdown({ text }: { text: string }) {
  const html = renderMarkdown(text || '')
  return <div className="md-content" dangerouslySetInnerHTML={{ __html: html }} />
}

function escapeHtml(s: string) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderMarkdown(src: string): string {
  const blocks: string[] = []
  // 先抽出代码块
  let text = src.replace(/```([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<pre><code>${escapeHtml(code.replace(/^\w*\n/, ''))}</code></pre>`)
    return `\u0000BLOCK${blocks.length - 1}\u0000`
  })
  text = escapeHtml(text)

  const lines = text.split('\n')
  const out: string[] = []
  let inList: 'ul' | 'ol' | null = null
  let inTable = false

  const closeList = () => {
    if (inList) {
      out.push(inList === 'ul' ? '</ul>' : '</ol>')
      inList = null
    }
  }
  const closeTable = () => {
    if (inTable) {
      out.push('</tbody></table>')
      inTable = false
    }
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (!line.trim()) {
      closeList()
      closeTable()
      continue
    }
    const h = /^(#{1,4})\s+(.*)/.exec(line)
    if (h) {
      closeList()
      closeTable()
      const lv = Math.min(h[1].length + 1, 4)
      out.push(`<h${lv}>${inline(h[2])}</h${lv}>`)
      continue
    }
    const ul = /^[-*]\s+(.*)/.exec(line)
    if (ul) {
      closeTable()
      if (inList !== 'ul') {
        closeList()
        out.push('<ul>')
        inList = 'ul'
      }
      out.push(`<li>${inline(ul[1])}</li>`)
      continue
    }
    const ol = /^\d+[.)]\s+(.*)/.exec(line)
    if (ol) {
      closeTable()
      if (inList !== 'ol') {
        closeList()
        out.push('<ol>')
        inList = 'ol'
      }
      out.push(`<li>${inline(ol[1])}</li>`)
      continue
    }
    if (/^\|.*\|/.test(line)) {
      closeList()
      const cells = line
        .slice(1, -1)
        .split('|')
        .map((c) => c.trim())
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) continue
      if (!inTable) {
        out.push('<table><tbody>')
        inTable = true
      }
      out.push(`<tr>${cells.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`)
      continue
    }
    const quote = /^&gt;\s?(.*)/.exec(line)
    if (quote) {
      closeList()
      closeTable()
      out.push(`<blockquote>${inline(quote[1])}</blockquote>`)
      continue
    }
    closeList()
    closeTable()
    out.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  closeTable()
  return out.join('\n').replace(/\u0000BLOCK(\d+)\u0000/g, (_, i) => blocks[Number(i)])
}

function inline(s: string): string {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
}

export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="col" style={{ alignItems: 'center', padding: '40px 0', gap: 14 }}>
      <div className="md-spinner" />
      <span className="muted">{text}</span>
    </div>
  )
}

export function Empty({ icon = '🌙', title, desc, action }: {
  icon?: string
  title: string
  desc?: string
  action?: ReactNode
}) {
  return (
    <div className="col" style={{ alignItems: 'center', padding: '48px 20px', gap: 10 }}>
      <div style={{ fontSize: 44 }}>{icon}</div>
      <div className="title-strong">{title}</div>
      {desc && <div className="muted" style={{ textAlign: 'center' }}>{desc}</div>}
      {action}
    </div>
  )
}

export function Sheet({ open, onClose, children, title }: {
  open: boolean
  onClose: () => void
  children: ReactNode
  title?: string
}) {
  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])
  if (!open) return null
  return (
    <div className="md-overlay" onClick={onClose}>
      <div className="md-sheet" onClick={(e) => e.stopPropagation()}>
        <div
          style={{
            width: 36,
            height: 4,
            borderRadius: 2,
            background: 'var(--md-outline-variant)',
            margin: '4px auto 14px',
          }}
        />
        {title && <div className="title-strong" style={{ marginBottom: 12 }}>{title}</div>}
        {children}
      </div>
    </div>
  )
}

export function Dialog({ open, onClose, title, children }: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  if (!open) return null
  return (
    <div className="md-overlay" style={{ alignItems: 'center' }} onClick={onClose}>
      <div className="md-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="title-strong" style={{ marginBottom: 12 }}>{title}</div>
        {children}
      </div>
    </div>
  )
}

export function Chips<T extends string>({ options, value, onChange }: {
  options: readonly T[]
  value: T | ''
  onChange: (v: T | '') => void
}) {
  return (
    <div className="md-chip-row">
      {options.map((o) => (
        <button
          key={o}
          className={`md-chip ${value === o ? 'active' : ''}`}
          onClick={() => onChange(value === o ? '' : o)}
        >
          {o}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="md-field">
      <span className="md-field-label">{label}</span>
      {children}
    </label>
  )
}

export function TopBar({ title, back, right }: {
  title: string
  back?: () => void
  right?: ReactNode
}) {
  return (
    <div className="md-topbar">
      {back && (
        <button className="md-iconbtn" onClick={back} aria-label="返回">
          ←
        </button>
      )}
      <div className="md-topbar-title">{title}</div>
      {right}
    </div>
  )
}

export function useAsync<T>(fn: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const reload = async () => {
    setLoading(true)
    setError('')
    try {
      setData(await fn())
    } catch (e: any) {
      setError(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, loading, error, reload, setData }
}

export const MASTERY_LABEL: Record<string, string> = {
  weak: '薄弱',
  improving: '进步中',
  mastered: '已掌握',
  unknown: '未评估',
}

export const STATE_LABEL: Record<string, string> = {
  not_started: '未接触',
  learning: '学习中',
  learned: '已学完',
}
