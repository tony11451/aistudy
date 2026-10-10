/** 图片查看器：双指捏合缩放、双击放大/还原、拖动平移 */
import { useEffect, useRef, useState } from 'react'
import { IconClose, IconZoomIn } from './icons'

interface Props {
  src: string
  onClose: () => void
}

export function ImageViewer({ src, onClose }: Props) {
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const state = useRef({
    pointers: new Map<number, { x: number; y: number }>(),
    lastDist: 0,
    lastScale: 1,
    panStart: { x: 0, y: 0 },
    offStart: { x: 0, y: 0 },
    lastTap: 0,
  })

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  const s = state.current

  const onPointerDown = (e: React.PointerEvent) => {
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    s.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (s.pointers.size === 2) {
      const [a, b] = [...s.pointers.values()]
      s.lastDist = Math.hypot(a.x - b.x, a.y - b.y)
      s.lastScale = scale
    } else if (s.pointers.size === 1) {
      s.panStart = { x: e.clientX, y: e.clientY }
      s.offStart = { ...offset }
      const now = Date.now()
      if (now - s.lastTap < 300) {
        setScale(scale > 1.2 ? 1 : 2.5)
        setOffset({ x: 0, y: 0 })
      }
      s.lastTap = now
    }
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!s.pointers.has(e.pointerId)) return
    s.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (s.pointers.size === 2) {
      const [a, b] = [...s.pointers.values()]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      if (s.lastDist > 0) {
        const next = Math.min(6, Math.max(1, s.lastScale * (dist / s.lastDist)))
        setScale(next)
      }
    } else if (s.pointers.size === 1 && scale > 1.05) {
      setOffset({
        x: s.offStart.x + (e.clientX - s.panStart.x),
        y: s.offStart.y + (e.clientY - s.panStart.y),
      })
    }
  }

  const onPointerUp = (e: React.PointerEvent) => {
    s.pointers.delete(e.pointerId)
    if (s.pointers.size < 2) s.lastDist = 0
  }

  return (
    <div className="viewer-overlay" onClick={onClose}>
      <button className="viewer-close bubble-action-btn" onClick={onClose}>
        <IconClose size={16} /> 关闭
      </button>
      <img
        className="viewer-img"
        src={src}
        alt="查看"
        draggable={false}
        style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={(e) => e.stopPropagation()}
      />
      <div
        style={{
          position: 'absolute',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          color: 'rgba(255,255,255,0.85)',
          fontSize: 13,
          display: 'flex',
          gap: 12,
          alignItems: 'center',
        }}
      >
        <IconZoomIn size={15} />
        双指缩放 · 双击放大 · 拖动平移（{Math.round(scale * 100)}%）
      </div>
    </div>
  )
}
