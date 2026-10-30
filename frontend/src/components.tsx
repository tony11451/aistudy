import { useEffect, useState, ReactNode } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

/** Markdown + LaTeX 数学公式渲染（$..$ 行内 / $$..$$ 块级） */
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

function renderTex(src: string): string {
  // 块级公式 $$...$$
  src = src.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
    try {
      return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false })
    } catch {
      return `<code>${escapeHtml(tex)}</code>`
    }
  })
  // 行内公式 $...$
  src = src.replace(/(^|[^\\$])\$([^$\n]+?)\$/g, (m, pre, tex) => {
    try {
      return pre + katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false })
    } catch {
      return m
    }
  })
  return src
}

function renderMarkdown(src: string): string {
  const blocks: string[] = []
  let text = src.replace(/```([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<pre><code>${escapeHtml(code.replace(/^\w*\n/, ''))}</code></pre>`)
    return `\u0000BLOCK${blocks.length - 1}\u0000`
  })
  text = escapeHtml(text)
  text = renderTex(text)

  const lines = text.split('\n')
  const out: string[] = []
  let inList: 'ul' | 'ol' | null = null
  let inTable = false
  let inBlock = false

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
  const closeBlock = () => {
    if (inBlock) {
      out.push('</div>')
      inBlock = false
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
      const level = h[1].length
      if (level === 2) {
        // ## 板块标题 → 独立卡片容器（需求 14：AI 自由定板块结构）
        closeBlock()
        out.push(`<div class="md-block"><div class="md-block-title">${inline(h[2])}</div>`)
        inBlock = true
        continue
      }
      const lv = Math.min(level + 1, 4)
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
  closeBlock()
  return out.join('\n').replace(/\u0000BLOCK(\d+)\u0000/g, (_, i) => blocks[Number(i)])
}

function inline(s: string): string {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
}

/** 异步数据加载 Hook */
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

export const CONFIDENCE_LABEL: Record<string, string> = {
  suspected: '疑似',
  confirmed: '已确认',
}

export function masteryTone(m?: string): 'weak' | 'improving' | 'mastered' | 'neutral' {
  if (m === 'weak') return 'weak'
  if (m === 'improving') return 'improving'
  if (m === 'mastered') return 'mastered'
  return 'neutral'
}

export type { ReactNode }
